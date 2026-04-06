import json
import base64
import io
import os
import random
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


load_dotenv(Path(__file__).with_name(".env"))

MODEL = "meta-llama/Llama-3.1-8B-Instruct"


def _get_client() -> OpenAI:
    base_url = os.getenv("OPENAI_API_BASE")
    api_key = os.getenv("OPENAI_API_KEY")
    if not base_url or not api_key:
        raise LLMError(
            "OPENAI_API_BASE and OPENAI_API_KEY must be set in the .env file."
        )
    
    import httpx
    # Bypass SSL verification to avoid macOS Python certificate issues missing the GT intermediate CA
    http_client = httpx.Client(verify=False)
    
    return OpenAI(base_url=base_url, api_key=api_key, http_client=http_client)
OUTPUT_PATH = Path(__file__).with_name("gap_analysis_output.json")

FIELD_SCHEMA = {
    "target_role": {"label": "Target role / job title", "priority": "critical"},
    "transition_type": {
        "label": "Type of transition",
        "priority": "critical",
    },
    "job_responsibilities": {
        "label": "Responsibilities of target job",
        "priority": "critical",
    },
    "job_requirements": {
        "label": "Requirements/qualifications for target job (return as JSON array of strings)",
        "priority": "critical",
    },
    "education_background": {"label": "Education background", "priority": "critical"},
    "work_background": {"label": "Work history and experience", "priority": "critical"},
    "target_field_experience": {
        "label": "Previous experience in target field",
        "priority": "critical",
    },
    "known_gaps": {
        "label": "Gaps the user already knows about",
        "priority": "critical",
    },
    "skills": {"label": "Current skills (return as JSON array of strings)", "priority": "helpful"},
    "projects": {"label": "Projects worked on (return as JSON array of strings)", "priority": "helpful"},
    "learning_style": {
        "label": "How they learn best (self-paced / hands-on)",
        "priority": "helpful",
    },
    "hours_per_week": {
        "label": "Hours available to dedicate per week",
        "priority": "helpful",
    },
    "childcare_constraints": {
        "label": "Childcare or caregiving constraints",
        "priority": "helpful",
    },
    "healthcare_constraints": {"label": "Healthcare needs", "priority": "helpful"},
    "housing_constraints": {
        "label": "Housing situation/constraints",
        "priority": "helpful",
    },
    "learning_budget": {"label": "Learning/training budget", "priority": "helpful"},
    "pcs_expected": {
        "label": "Expecting a PCS move? If so, when?",
        "priority": "helpful",
    },
}

FOLLOW_UP_TEMPLATES = {
    "target_role": "What career are you working toward?",
    "transition_type": "What kind of career change are you making?",
    "job_responsibilities": "What kind of work do you want to do?",
    "job_requirements": "What requirements or credentials do you still need?",
    "education_background": "What education or training do you already have?",
    "work_background": "What work experience do you already have?",
    "target_field_experience": "How much experience do you have in this field?",
    "known_gaps": "What gaps or barriers are you aware of?",
    "skills": "What skills do you already feel strong in?",
    "projects": "Have you worked on any relevant projects?",
    "learning_style": "How do you learn best?",
    "hours_per_week": "How much time can you give each week?",
    "childcare_constraints": "Any childcare or caregiving limits right now?",
    "healthcare_constraints": "Any healthcare needs affecting your plan?",
    "housing_constraints": "Any housing issues affecting your plan?",
    "learning_budget": "Do you have a budget for training or courses?",
    "pcs_expected": "Do you expect a PCS move soon?",
}


class LLMError(RuntimeError):
    pass


# Keep old name as alias so external code that still references it doesn't break.
OllamaError = LLMError


def build_intake_source(story: str = "", resume_text: str = "") -> str:
    story = (story or "").strip()
    resume_text = (resume_text or "").strip()

    sections = []
    if story:
        sections.append(f"User story:\n{story}")
    if resume_text:
        sections.append(f"Resume text:\n{resume_text}")
    return "\n\n".join(sections)


def _strip_rtf(text: str) -> str:
    return (
        str(text)
        .replace("\\par", "\n")
        .replace("\\pard", "\n")
        .replace("\r\n", "\n")
    )


def _normalize_resume_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def extract_resume_text_from_upload(resume_file: dict) -> str:
    if not isinstance(resume_file, dict):
        return ""

    file_name = str(resume_file.get("name") or "").strip()
    content_base64 = str(resume_file.get("contentBase64") or "").strip()
    mime_type = str(resume_file.get("type") or "").strip().lower()
    extension = Path(file_name).suffix.lower()

    if not file_name or not content_base64:
        return ""

    try:
        file_bytes = base64.b64decode(content_base64, validate=True)
    except Exception as exc:
        raise ValueError("The uploaded resume file could not be decoded.") from exc

    if extension == ".pdf" or mime_type == "application/pdf":
        if PdfReader is None:
            raise ValueError(
                "PDF resume support requires the `pypdf` package. Install the updated backend requirements."
            )

        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:
            raise ValueError("The uploaded PDF could not be read.") from exc

        normalized = _normalize_resume_text(text)
        if not normalized:
            raise ValueError("The uploaded PDF did not contain readable text.")
        return normalized

    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1", errors="ignore")

    if extension == ".rtf":
        text = _strip_rtf(text)

    return _normalize_resume_text(text)


def check_ollama():
    """Legacy entry-point – now validates LiteLLM env vars instead of pinging Ollama."""
    base_url = os.getenv("OPENAI_API_BASE")
    api_key = os.getenv("OPENAI_API_KEY")
    if not base_url or not api_key:
        raise LLMError(
            "OPENAI_API_BASE and OPENAI_API_KEY must be set in the .env file."
        )


def call_ollama(prompt: str, system: str = "") -> str:
    """Send a prompt to the LiteLLM / OpenAI-compatible endpoint and return the text reply."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.1,
        )
        return (response.choices[0].message.content or "").strip()
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"LiteLLM request failed: {exc}") from exc


def _clean_json_response(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def extract_fields(user_text: str) -> dict:
    field_list = "\n".join(f'  "{k}": "{v["label"]}"' for k, v in FIELD_SCHEMA.items())
    system = (
        "You are a structured data extractor for a military spouse career support program. "
        "Your job is to read free-form text and extract specific fields. "
        "Return ONLY a valid JSON object with the requested keys. "
        "Each populated value must be useful for downstream planning. "
        "Use enough detail to preserve meaning, usually a phrase or 1-2 short sentences. "
        "Do not copy huge chunks of the source text, but do not over-compress either. "
        "If a field is not mentioned or cannot be reasonably inferred, set it to null. "
        "Use resume section headings and labels as evidence when present. "
        "Be generous with inference but do not fabricate specific details."
    )
    prompt = f"""Extract the following fields from the user's text. Return only a JSON object.

Fields to extract:
{field_list}

User's text:
\"\"\"{user_text}\"\"\"

Return a JSON object with exactly these keys. Use null for any field not found.
Prefer clear, planning-ready values. Examples:
- target_role: "Special needs caregiver"
- job_responsibilities: "Support children and adults with special needs; provide care and daily assistance."
- job_requirements: ["Early childhood development background", "CPR certified", "Relevant degree"]
- education_background: "Early Childhood Development studies in Little Rock."
- skills: ["Budgeting", "Logistics", "Scheduling"]
- projects: ["Led community bake sale raising $2000", "Organized PCS move"]
If a resume includes headings like Desired Work, Requirements, Education, Skills, or Experience, map them into the matching fields."""
    raw = _clean_json_response(call_ollama(prompt, system))
    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError:
        extracted = {}

    normalized = {key: normalize_field_value(key, extracted.get(key)) for key in FIELD_SCHEMA}
    return _apply_field_fallbacks(normalized)


def find_missing_fields(extracted: dict) -> list[str]:
    missing = [key for key in FIELD_SCHEMA if _is_missing_for_follow_up(key, extracted)]
    missing.sort(key=lambda key: 0 if FIELD_SCHEMA[key]["priority"] == "critical" else 1)
    return missing


def generate_prompts(user_text: str, missing_fields: list[str]) -> dict:
    if not missing_fields:
        return {}

    return {key: FOLLOW_UP_TEMPLATES.get(key, FIELD_SCHEMA[key]["label"]) for key in missing_fields}


def generate_sample_story() -> str:
    length_choice = random.choice(
        [
            "Write exactly 2 short, simple sentences. Keep each sentence under 18 words.",
            "Write 3 short sentences. Keep the details light.",
            "Write 4 short sentences. Keep the details practical, not dense.",
        ]
    )
    system = (
        "You write realistic first-person intake stories for a military spouse career support program. "
        "Return only a single short paragraph in plain text. "
        "The story should sound natural, simple, and human. "
        "Include what the person hopes to work toward, what experience or skills they already have, "
        "and any challenges they are facing right now. "
        "The story should mention housing, healthcare, or transportation needs, and can mention more than one. "
        "Keep the writing straightforward. Avoid extra backstory, long explanations, and stacked details. "
        "Do not use bullet points, labels, or markdown."
    )
    prompt = (
        "Generate one realistic sample intake story from a military spouse seeking career support. "
        "Vary the career path and situation from common examples. "
        f"{length_choice}"
    )
    return call_ollama(prompt, system).strip()


def generate_sample_answers(user_text: str, missing_fields: list[dict]) -> dict:
    if not missing_fields:
        return {}

    fields_needed = "\n".join(
        f'  "{field["key"]}": "{field["label"]}" -> {field["question"]}'
        for field in missing_fields
    )
    system = (
        "You generate realistic sample follow-up answers for a military spouse career intake. "
        "Return ONLY a valid JSON object mapping field keys to short first-person answers. "
        "Keep answers practical, specific, and consistent with the original story. "
        "Do not use markdown or explanations."
    )
    prompt = f"""A user shared this intake story:
\"\"\"{user_text}\"\"\"

Generate realistic sample answers for these follow-up items:
{fields_needed}

Return a JSON object like:
{{ "field_key": "sample answer", ... }}"""
    raw = _clean_json_response(call_ollama(prompt, system))
    try:
        answers = json.loads(raw)
    except json.JSONDecodeError:
        answers = {}

    return {
        field["key"]: str(answers.get(field["key"], "")).strip()
        for field in missing_fields
        if str(answers.get(field["key"], "")).strip()
    }


def _shorten_text(value: str, max_len: int = 180) -> str:
    value = re.sub(r"\s+", " ", value).strip(" ,.;:")
    if len(value) <= max_len:
        return value
    shortened = value[:max_len].rsplit(" ", 1)[0].strip(" ,.;:")
    return f"{shortened}..."


def _clean_text_value(text: str, max_len: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip(" ,.;:")
    text = re.sub(
        r"^(i am|i'm|i have|i need|my|our|we have|we need)\s+",
        "",
        text,
        flags=re.I,
    )
    return _shorten_text(text[:1].upper() + text[1:] if text else text, max_len)


def _apply_field_fallbacks(extracted: dict) -> dict:
    normalized = dict(extracted)

    if not normalized.get("target_role") and normalized.get("job_responsibilities"):
        normalized["target_role"] = normalized["job_responsibilities"]

    if not normalized.get("job_responsibilities") and normalized.get("target_role"):
        normalized["job_responsibilities"] = normalized["target_role"]

    if not normalized.get("target_field_experience") and normalized.get("work_background"):
        normalized["target_field_experience"] = normalized["work_background"]

    return normalized


def _has_substantive_value(value) -> bool:
    if value in (None, "", "null"):
        return False
    return len(str(value).strip()) >= 4


def _is_missing_for_follow_up(key: str, extracted: dict) -> bool:
    if _has_substantive_value(extracted.get(key)):
        return False

    fallback_groups = {
        "target_role": ("job_responsibilities",),
        "job_responsibilities": ("target_role",),
        "target_field_experience": ("work_background",),
    }

    return not any(_has_substantive_value(extracted.get(other)) for other in fallback_groups.get(key, ()))


def normalize_field_value(key: str, value):
    if value in (None, "", "null", []):
        return None

    if isinstance(value, list):
        cleaned = [normalize_field_value(key, v) for v in value if v]
        return [c for c in cleaned if c]

    if key == "hours_per_week":
        match = re.search(r"\b(\d{1,2})\b", str(value))
        return int(match.group(1)) if match else _shorten_text(str(value), 40)

    if key in {"learning_budget"}:
        match = re.search(r"\$?\s*([0-9]{2,5})", str(value))
        if match:
            return f"${match.group(1)}"

    text = str(value).strip()
    if key == "target_role":
        text = re.sub(
            r"^(i want to be|i want|working toward|hoping for|looking for|interested in)\s+",
            "",
            text,
            flags=re.I,
        )
        return _clean_text_value(text, 120)

    if key in {
        "transition_type",
        "job_responsibilities",
        "job_requirements",
        "education_background",
        "work_background",
        "target_field_experience",
        "known_gaps",
        "skills",
        "projects",
        "learning_style",
        "childcare_constraints",
        "healthcare_constraints",
        "housing_constraints",
        "pcs_expected",
    }:
        return _clean_text_value(text, 180)

    return _clean_text_value(text, 140)


def merge_and_finalize(extracted: dict, user_answers: dict) -> dict:
    final = {key: extracted.get(key) for key in FIELD_SCHEMA}
    for key, value in user_answers.items():
        if key in FIELD_SCHEMA and value not in (None, ""):
            final[key] = normalize_field_value(key, value)
    return final


def save_output(final: dict) -> str:
    OUTPUT_PATH.write_text(json.dumps(final, indent=2))
    return str(OUTPUT_PATH)


def normalize_single_answer_via_llm(key: str, raw_answer: str, context: str) -> any:
    if not str(raw_answer).strip():
        return ""

    field_info = FIELD_SCHEMA.get(key, {})
    label = field_info.get("label", key)

    system = (
        "You are a professional editor for a military spouse career intake process. "
        "A user has provided a raw answer for a specific field. Your task is to clean, "
        "format, and professionalize this answer based on their context. "
        "If the field label implies a list (e.g. skills, projects, specific requirements), "
        "return a JSON array of strings. Otherwise, return a single concise string. "
        "Return ONLY valid JSON (either a string or an array of strings). "
        "Do not include any other text or markdown block markers."
    )

    prompt = f"""Context from their profile:
{context}

Field: {label}
Raw Answer is:
{raw_answer}

Return ONLY the cleaned JSON value (string or array of strings, properly quoted)."""

    raw = _clean_json_response(call_ollama(prompt, system))
    try:
        parsed = json.loads(raw)
        return parsed
    except json.JSONDecodeError:
        return str(raw).strip('" ')

def describe_missing_fields(user_text: str, extracted: dict) -> list[dict]:
    missing = find_missing_fields(extracted)
    prompts = generate_prompts(user_text, missing)
    return [
        {
            "key": key,
            "label": FIELD_SCHEMA[key]["label"],
            "priority": FIELD_SCHEMA[key]["priority"],
            "question": prompts.get(key, FIELD_SCHEMA[key]["label"]),
        }
        for key in missing
    ]
