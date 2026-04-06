import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
)


HOST = "127.0.0.1"
PORT = 8000


class IntakeHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8"))

    def do_OPTIONS(self):
        self._send_json(204, {})

    def do_GET(self):
        if self.path != "/health":
            self._send_json(404, {"error": "Not found"})
            return

        try:
            check_ollama()
            ollama_status = "ok"
        except OllamaError as exc:
            ollama_status = str(exc)

        self._send_json(
            200,
            {
                "status": "ok",
                "ollama": ollama_status,
            },
        )

    def do_POST(self):
        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON body"})
            return

        if self.path == "/api/intake/start":
            self._handle_start(payload)
            return
        if self.path == "/api/intake/sample":
            self._handle_sample()
            return
        if self.path == "/api/intake/sample-answers":
            self._handle_sample_answers(payload)
            return
        if self.path == "/api/intake/complete":
            self._handle_complete(payload)
            return
        if self.path == "/api/intake/normalize-answer":
            self._handle_normalize_answer(payload)
            return

        self._send_json(404, {"error": "Not found"})

    def _handle_start(self, payload: dict):
        story = (payload.get("story") or "").strip()
        resume_text = (payload.get("resumeText") or "").strip()
        resume_file = payload.get("resumeFile")

        try:
            uploaded_resume_text = extract_resume_text_from_upload(resume_file)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        source_text = build_intake_source(story, resume_text or uploaded_resume_text)

        if not source_text:
            self._send_json(400, {"error": "Add a story or upload a resume."})
            return

        try:
            check_ollama()
            extracted = extract_fields(source_text)
            missing_fields = describe_missing_fields(source_text, extracted)
        except OllamaError as exc:
            self._send_json(502, {"error": str(exc)})
            return

        self._send_json(
            200,
            {
                "story": story,
                "resumeText": resume_text or uploaded_resume_text,
                "sourceText": source_text,
                "extracted": extracted,
                "missingFields": missing_fields,
            },
        )

    def _handle_complete(self, payload: dict):
        extracted = payload.get("extracted")
        answers = payload.get("answers") or {}

        if not isinstance(extracted, dict):
            self._send_json(400, {"error": "An extracted payload is required."})
            return
        if not isinstance(answers, dict):
            self._send_json(400, {"error": "Answers must be an object."})
            return

        final = merge_and_finalize(extracted, answers)
        output_path = save_output(final)
        self._send_json(
            200,
            {
                "final": final,
                "outputPath": output_path,
            },
        )

    def _handle_sample(self):
        try:
            check_ollama()
            story = generate_sample_story()
        except OllamaError as exc:
            self._send_json(502, {"error": str(exc)})
            return

        self._send_json(200, {"story": story})

    def _handle_sample_answers(self, payload: dict):
        story = (payload.get("story") or "").strip()
        source_text = (payload.get("sourceText") or story).strip()
        missing_fields = payload.get("missingFields") or []

        if not source_text:
            self._send_json(400, {"error": "Story or source text is required."})
            return
        if not isinstance(missing_fields, list):
            self._send_json(400, {"error": "missingFields must be a list."})
            return

        try:
            check_ollama()
            answers = generate_sample_answers(source_text, missing_fields)
        except OllamaError as exc:
            self._send_json(502, {"error": str(exc)})
            return

        self._send_json(200, {"answers": answers})

    def _handle_normalize_answer(self, payload: dict):
        key = payload.get("key")
        value = payload.get("value")
        context = payload.get("context", "")

        if not key or value is None:
            self._send_json(400, {"error": "Key and value are required."})
            return

        try:
            check_ollama()
            normalized = normalize_single_answer_via_llm(key, value, context)
        except OllamaError as exc:
            self._send_json(502, {"error": str(exc)})
            return

        self._send_json(200, {"normalized": normalized})


def run():
    server = ThreadingHTTPServer((HOST, PORT), IntakeHandler)
    print(f"LLM API listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
