from flask import Flask, request, render_template_string
from openai import OpenAI
import json
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

# Bypass SSL verification to avoid macOS Python certificate issues missing the GT intermediate CA
http_client = httpx.Client(verify=False)

client = OpenAI(
    base_url=os.getenv("OPENAI_API_BASE"),
    api_key=os.getenv("OPENAI_API_KEY"),
    http_client=http_client
)
app = Flask(__name__)

ONBOARDING_FILE = "onboarding_sample.json"
CROWDSOURCED_FILE = "crowdsourced_cases.json"

PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>CareerCorps Gap Analysis</title>
  <style>
    body { font-family: system-ui, -apple-system, Arial; margin: 24px; max-width: 980px; }
    textarea { width: 100%; height: 140px; padding: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .row { display: grid; grid-template-columns: 1fr; gap: 14px; }
    button { padding: 10px 14px; font-size: 14px; cursor: pointer; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 14px; margin-top: 16px; }
    .h { font-weight: 700; margin-bottom: 6px; }
    .muted { color: #666; font-size: 13px; }
    ul { margin: 8px 0 0 18px; }
    pre { background: #f6f6f6; padding: 12px; overflow-x: auto; border-radius: 10px; white-space: pre-wrap; }
    .error { color: #b00020; font-weight: 600; }
  </style>
</head>
<body>
  <h1>Gap Analysis (Prototype)</h1>

  <div class="card">
    <div class="h">Loaded Onboarding File</div>
    <div class="muted">{{ onboarding_file }}</div>
    <pre>{{ onboarding_json }}</pre>
  </div>

  <div class="card">
    <div class="h">Loaded Crowdsourced Cases File</div>
    <div class="muted">{{ crowdsourced_file }}</div>
    <pre>{{ crowdsourced_preview }}</pre>
  </div>

  <form method="POST" class="row">
    <div>
      <div class="h">Mentor Feedback (optional)</div>
      <textarea name="mentor_feedback">{{ mentor_feedback }}</textarea>
    </div>

    <div>
      <button type="submit">Generate Gap Analysis</button>
    </div>
  </form>

  {% if error %}
    <div class="card error">Error: {{ error }}</div>
  {% endif %}

  {% if result %}
    <div class="card">
      <div class="h">Derived Requirements</div>
      <ul>
        {% for req in result.requirements %}
          <li><b>{{ req.id }}</b>: {{ req.text }} <span class="muted">({{ req.kind }})</span></li>
        {% endfor %}
      </ul>
    </div>

    <div class="card">
      <div class="h">Gaps</div>

      <div class="h" style="margin-top:10px;">Known Gaps <span class="muted">(user reported)</span></div>
      <ul>
        {% for g in result.known_gaps %}
          <li><b>{{ g.title }}</b> <span class="muted">({{ g.kind }})</span></li>
        {% endfor %}
      </ul>

      <div class="h" style="margin-top:10px;">Unknown / Unrealized Gaps <span class="muted">(missing but not mentioned)</span></div>
      <ul>
        {% for g in result.unknown_gaps %}
          <li><b>{{ g.title }}</b> <span class="muted">({{ g.kind }})</span></li>
        {% endfor %}
      </ul>

      <div class="h" style="margin-top:10px;">Perceived / False Gaps <span class="muted">(not actually required)</span></div>
      <ul>
        {% for g in result.perceived_gaps %}
          <li><b>{{ g.title }}</b></li>
        {% endfor %}
      </ul>
    </div>

    <div class="card">
      <div class="h">Next Steps</div>
      <ul>
        {% for step in result.next_steps %}
          <li><b>{{ step.action }}</b> : {{ step.timeframe }}</li>
        {% endfor %}
      </ul>
    </div>

    <div class="card">
      <div class="h">What Others Have Done in Similar Fields</div>
      {% for item in result.what_others_have_done %}
        <div style="margin-bottom: 14px;">
          <div><b>Pattern:</b> {{ item.pattern }}</div>
          <div><b>How people succeeded:</b> <span class="muted">{{ item.how_they_succeeded }}</span></div>
          <div><b>Why it may matter here:</b> {{ item.relevance_to_user }}</div>
        </div>
      {% endfor %}
    </div>

    <details class="card">
      <summary class="h">Raw JSON Output</summary>
      <pre>{{ raw_json }}</pre>
    </details>
  {% endif %}
</body>
</html>
"""

def load_json_file(filename: str) -> dict:
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_json(data: dict) -> dict:
    cleaned = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in ["", "null"]:
            continue
        cleaned[key] = value
    return cleaned


def format_onboarding_json(data: dict) -> str:
    return f"""
Target Role:
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
- Learning style: {data.get("learning_style", "Not provided")}
""".strip()


def format_crowdsourced_cases(data: dict) -> str:
    lines = ["Crowdsourced Career Trajectories:"]
    for case in data.get("cases", []):
        lines.append(f"\nCase {case.get('case_id')} - {case.get('profession')}")
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
    return "\n".join(lines)


def run_gap_analysis(onboarding_data: dict, crowdsourced_data: dict, mentor_feedback: str) -> dict:
    formatted_profile = format_onboarding_json(onboarding_data)
    formatted_crowdsourced = format_crowdsourced_cases(crowdsourced_data)

    prompt = f"""
You are helping with a career gap analysis with a goal.

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
}}
"""

    resp = client.chat.completions.create(
        model="meta-llama/Llama-3.1-8B-Instruct",
        messages=[
            {"role": "system", "content": "Output ONLY valid JSON. Be realistic and concise."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    text = resp.choices[0].message.content.strip()
    return json.loads(text)


@app.route("/", methods=["GET", "POST"])
def home():
    mentor_feedback = ""
    result = None
    raw_json = ""
    error = ""

    onboarding_json = ""
    crowdsourced_preview = ""

    try:
        onboarding_data = load_json_file(ONBOARDING_FILE)
        crowdsourced_data = load_json_file(CROWDSOURCED_FILE)

        onboarding_json = json.dumps(onboarding_data, indent=2)
        preview_cases = {"cases": crowdsourced_data.get("cases", [])[:3]}
        crowdsourced_preview = json.dumps(preview_cases, indent=2)

        cleaned_onboarding = clean_json(onboarding_data)

    except Exception as e:
        cleaned_onboarding = {}
        crowdsourced_data = {}
        error = f"Could not load input files: {str(e)}"

    if request.method == "POST" and not error:
        mentor_feedback = request.form.get("mentor_feedback", "").strip()

        try:
            result = run_gap_analysis(cleaned_onboarding, crowdsourced_data, mentor_feedback)

            result.setdefault("requirements", [])
            result.setdefault("known_gaps", [])
            result.setdefault("unknown_gaps", [])
            result.setdefault("perceived_gaps", [])
            result.setdefault("next_steps", [])
            result.setdefault("what_others_have_done", [])

            raw_json = json.dumps(result, indent=2)

        except Exception as e:
            error = str(e)

    return render_template_string(
        PAGE,
        onboarding_file=ONBOARDING_FILE,
        crowdsourced_file=CROWDSOURCED_FILE,
        onboarding_json=onboarding_json,
        crowdsourced_preview=crowdsourced_preview,
        mentor_feedback=mentor_feedback,
        result=result,
        raw_json=raw_json,
        error=error,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
