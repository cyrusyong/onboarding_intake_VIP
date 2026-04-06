# CareerCorps Intake Frontend

This frontend is wired to the local Python LLM API in [`../LLM/server.py`](../LLM/server.py).

## What It Does

- Collects a free-form intake story
- Lets the user upload a resume (`.pdf`, `.txt`, `.md`, `.rtf`) to enrich extraction
- Sends it to the backend for field extraction
- Renders follow-up questions for missing fields
- Finalizes and displays the JSON payload written by the LLM service

## Run the Backend

From the repo root:

```bash
cd LLM
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 server.py
```

Prerequisites:

- Ollama running locally on `http://localhost:11434`
- The `llama3.1:8b` model available locally

Example:

```bash
ollama serve
ollama pull llama3.1:8b
```

## Run the Frontend

In a second terminal:

```bash
cd careercorps-ui
npm install
npm run dev
```

The Vite app defaults to `http://127.0.0.1:8000` for the API.

If you need a different backend URL, create `.env.local` in `careercorps-ui`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Production Build

```bash
cd careercorps-ui
npm run build
```
