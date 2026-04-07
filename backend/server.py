import json
import os
from flask import Flask, request, jsonify
from flask_cors import CORS

from onboarding_service import (
    OllamaError,
    build_intake_source,
    check_ollama,
    describe_missing_fields,
    extract_resume_text_from_upload,
    extract_fields,
    generate_sample_answers,
    generate_sample_story,
    merge_and_finalize,
    normalize_single_answer_via_llm,
    save_output,
    _get_client,
    MODEL
)

app = Flask(__name__)
CORS(app)

PORT = 8000

@app.route("/health", methods=["GET"])
def health():
    try:
        check_ollama()
        ollama_status = "ok"
    except OllamaError as exc:
        ollama_status = str(exc)

    return jsonify({
        "status": "ok",
        "ollama": ollama_status,
    }), 200

@app.route("/api/intake/start", methods=["POST"])
def intake_start():
    payload = request.get_json(silent=True) or {}
    story = (payload.get("story") or "").strip()
    resume_text = (payload.get("resumeText") or "").strip()
    resume_file = payload.get("resumeFile")

    try:
        uploaded_resume_text = extract_resume_text_from_upload(resume_file)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    source_text = build_intake_source(story, resume_text or uploaded_resume_text)

    if not source_text:
        return jsonify({"error": "Add a story or upload a resume."}), 400

    try:
        check_ollama()
        extracted = extract_fields(source_text)
        missing_fields = describe_missing_fields(source_text, extracted)
    except OllamaError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({
        "story": story,
        "resumeText": resume_text or uploaded_resume_text,
        "sourceText": source_text,
        "extracted": extracted,
        "missingFields": missing_fields,
    })

@app.route("/api/intake/complete", methods=["POST"])
def intake_complete():
    payload = request.get_json(silent=True) or {}
    extracted = payload.get("extracted")
    answers = payload.get("answers") or {}

    if not isinstance(extracted, dict):
        return jsonify({"error": "An extracted payload is required."}), 400
    if not isinstance(answers, dict):
        return jsonify({"error": "Answers must be an object."}), 400

    final = merge_and_finalize(extracted, answers)
    output_path = save_output(final)
    return jsonify({
        "final": final,
        "outputPath": output_path,
    })

@app.route("/api/intake/sample", methods=["POST"])
def intake_sample():
    try:
        check_ollama()
        story = generate_sample_story()
    except OllamaError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"story": story})

@app.route("/api/intake/sample-answers", methods=["POST"])
def intake_sample_answers():
    payload = request.get_json(silent=True) or {}
    story = (payload.get("story") or "").strip()
    source_text = (payload.get("sourceText") or story).strip()
    missing_fields = payload.get("missingFields") or []

    if not source_text:
        return jsonify({"error": "Story or source text is required."}), 400
    if not isinstance(missing_fields, list):
        return jsonify({"error": "missingFields must be a list."}), 400

    try:
        check_ollama()
        answers = generate_sample_answers(source_text, missing_fields)
    except OllamaError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"answers": answers})

@app.route("/api/intake/normalize-answer", methods=["POST"])
def intake_normalize_answer():
    payload = request.get_json(silent=True) or {}
    key = payload.get("key")
    value = payload.get("value")
    context = payload.get("context", "")

    if not key or value is None:
        return jsonify({"error": "Key and value are required."}), 400

    try:
        check_ollama()
        normalized = normalize_single_answer_via_llm(key, value, context)
    except OllamaError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify({"normalized": normalized})

def format_onboarding_json(data: dict) -> str:
    return f"""Target Role:
- {data.get("target_role", "Not provided")}

Transition Information:
- Transition Type: {data.get("transition_type", "Not provided")}
- Target Field Experience: {data.get("target_field_experience", "Not provided")}

Goal Details:
- Job Responsibilities: {data.get("job_responsibilities", "Not provided")}
- Job Requirements: {data.get("job_requirements", "Not provided")}

Background:
- Education: {data.get("education_background", "Not provided")}
- Work Background: {data.get("work_background", "Not provided")}

Existing Skills and Evidence:
- Skills: {data.get("skills", "Not provided")}
- Projects: {data.get("projects", "Not provided")}

Known Gaps:
- {data.get("known_gaps", "Not provided")}

Constraints:
- Hours per week available: {data.get("hours_per_week", "Not provided")}
- Childcare constraints: {data.get("childcare_constraints", "Not provided")}
- Healthcare constraints: {data.get("healthcare_constraints", "Not provided")}
- Housing constraints: {data.get("housing_constraints", "Not provided")}
- Learning budget: {data.get("learning_budget", "Not provided")}
- PCS expected: {data.get("pcs_expected", "Not provided")}

Preferences:
- Learning style: {data.get("learning_style", "Not provided")}""".strip()

def format_crowdsourced_cases(data: dict) -> str:
    lines = ["Crowdsourced Career Trajectories:"]
    for case in data.get("cases", []):
        lines.append(f"\\nCase {case.get('case_id')} - {case.get('profession')}")
        exp = case.get("experience", {})
        skills = case.get("skills", {})
        psych = case.get("psychological", {})
        licensing = case.get("licensing", {})

        lines.append(f"- PCS moves: {exp.get('pcs_moves', 'N/A')}")
        lines.append(f"- Promotions: {exp.get('promotions', 'N/A')}")
        if exp.get("job_level_path"):
            lines.append(f"- Job level path: {', '.join(exp.get('job_level_path'))}")
        if exp.get("time_unemployed_after_moves_months"):
            lines.append(f"- Unemployment after moves (months): {exp.get('time_unemployed_after_moves_months')}")
        if licensing.get("time_to_relicensure_months"):
            lines.append(f"- Relicensure time (months): {licensing.get('time_to_relicensure_months')}")
        if licensing.get("income_lost_usd") is not None:
            lines.append(f"- Income lost (USD): {licensing.get('income_lost_usd')}")
        if licensing.get("income_lost_per_move_usd") is not None:
            lines.append(f"- Income lost per move (USD): {licensing.get('income_lost_per_move_usd')}")
        if skills.get("courses"):
            lines.append(f"- Courses taken: {skills.get('courses')}")
        if skills.get("certifications"):
            lines.append(f"- Certifications: {skills.get('certifications')}")
        if skills.get("pivot_description"):
            lines.append(f"- Pivot: {skills.get('pivot_description')}")
        if skills.get("skills_before") is not None and skills.get("skills_after") is not None:
            lines.append(f"- Skills before/after: {skills.get('skills_before')} to {skills.get('skills_after')}")
        lines.append(f"- Satisfaction: {psych.get('career_satisfaction', 'N/A')}")
        lines.append(f"- Identity loss: {psych.get('identity_loss', 'N/A')}")
    return "\\n".join(lines)

@app.route("/api/gap-analysis/generate", methods=["POST"])
def gap_analysis_generate():
    payload = request.get_json(silent=True) or {}
    onboarding_data = payload.get("onboarding_data", {})
    mentor_feedback = payload.get("mentor_feedback", "").strip()

    try:
        with open("crowdsourced_cases.json", "r", encoding="utf-8") as f:
            crowdsourced_data = json.load(f)
    except Exception as e:
        return jsonify({"error": f"Failed to load crowdsourced cases: {str(e)}"}), 500

    formatted_profile = format_onboarding_json(onboarding_data)
    formatted_crowdsourced = format_crowdsourced_cases(crowdsourced_data)

    prompt = f"""You are helping with a career gap analysis with a goal.

Inputs:
1) Structured onboarding profile:
{formatted_profile}

2) Mentor feedback (optional):
{mentor_feedback}

Tasks:

A) Infer EXACTLY 4-5 realistic role requirements for the target role.
   Each requirement must be common for entry-to-mid level roles.
   Tag each as one of:
   - skill
   - experience
   - credential
   - artifact

B) Compare the user's background, skills, projects, and constraints against these requirements.

C) Identify gaps categorized as:
   - known_gaps: explicitly stated or directly observable from user input
   - unknown_gaps: required for the role but not mentioned or recognized by the user
   - perceived_gaps: concerns that are NOT actually required for this role

   Each gap must:
   - map to a requirement
   - include a severity level (High / Medium / Low)

D) Produce 3-5 next steps.

Each step must:
- directly address a gap
- be specific and actionable
- be feasible within the user’s constraints (time, childcare, etc.)

Important rules:
- Infer requirements conservatively.
- Do not include advanced or uncommon requirements.
- Do not generate vague recommendations.
- Respect user constraints strictly.

Output ONLY valid JSON with EXACT format:

{{
  "requirements": [
    {{"id":"R1","text":"...","kind":"skill|experience|credential|artifact"}}
  ],
  "known_gaps": [
    {{"title":"...","kind":"skill|experience|credential|artifact"}}
  ],
  "unknown_gaps": [
    {{"title":"...","kind":"skill|experience|credential|artifact"}}
  ],
  "perceived_gaps": [
    {{"title":"..."}}
  ],
  "next_steps": [
    {{"action":"...","timeframe":"..."}}
  ],
  "what_others_have_done": [
    {{
      "pattern": "...",
      "how_they_succeeded": "...",
      "relevance_to_user": "..."
    }}
  ]
}}"""

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Output ONLY valid JSON. Be realistic and concise."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        text = resp.choices[0].message.content.strip()
        from onboarding_service import _clean_json_response
        cleaned_text = _clean_json_response(text)
        parsed = json.loads(cleaned_text)
        return jsonify(parsed)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)
