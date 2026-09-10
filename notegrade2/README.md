# NoteGrade AI — ADK Edition

AI-assisted answer-sheet evaluator, built as an actual **Google ADK agent** —
not just a raw Gemini API call. Same agent runs two ways:

1. **`adk run` / `adk web`** — for teaching your professor: "this is the
   agent, this is its instruction, this is its structured output contract."
2. **FastAPI backend** — for the real product: file upload, PDF report.

## Project structure

```
notegrade2/
├── notegrade_agent/        ← THE agent (this is what you demo/teach)
│   ├── __init__.py         ← exposes root_agent (ADK requirement)
│   ├── agent.py            ← model, instruction, output_schema
│   └── .env                ← GOOGLE_API_KEY
├── backend/
│   ├── main.py             ← FastAPI wrapper, runs the SAME agent via Runner
│   ├── pdf_report.py        ← HTML -> PDF report generator
│   └── requirements.txt
└── frontend/
    └── index.html           ← no-build-step demo UI
```

## Why this is a "real" ADK agent, not a wrapper pretending to be one

- `root_agent = Agent(...)` in `notegrade_agent/agent.py` is the single
  source of truth — model, instruction, and structured output contract.
- `output_schema=EvaluationResult` (a Pydantic model) is ADK's native
  structured-output mechanism — ADK enforces the schema at the API level,
  we never hand-parse loose JSON.
- The FastAPI backend does NOT call Gemini directly. It calls
  `google.adk.runners.Runner` on the exact same `root_agent` object that
  `adk run`/`adk web` use. One agent, two front doors.

## Setup

```bash
cd notegrade2
pip install -r backend/requirements.txt --break-system-packages

# Set your key in notegrade_agent/.env (already scaffolded):
echo 'GOOGLE_API_KEY="your_key_from_aistudio.google.com/apikey"' > notegrade_agent/.env
# Also export it for the backend process:
export GOOGLE_API_KEY="your_key_here"
```

WeasyPrint (PDF generation) needs system libs on Linux:
```bash
sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev
```

## Run it two ways

### A) Teaching demo — pure ADK, no backend needed
```bash
cd notegrade2
adk web --port 8000       # browser chat UI, run from the PARENT of notegrade_agent/
# or
adk run notegrade_agent   # CLI chat
```
Select `notegrade_evaluator` in the ADK web UI, attach an image of a
handwritten answer, type the question/marks/rubric in your message, and
show the professor the structured JSON come back. This is the "here's the
agent" moment.

### B) Real product — FastAPI + frontend
```bash
cd notegrade2/backend
uvicorn main:app --reload --port 8000
```
Then open `frontend/index.html` in a browser (it calls `localhost:8000`).
This gives proper file-upload forms + one-click PDF report download —
things the ADK dev UI isn't meant to provide (it says so itself: "ADK Web
is not meant for use in production deployments").

## Model choice

- `gemini-3.6-flash` — "balancing speed and multimodal capabilities across
  general agentic and everyday tasks," Stable release. Matches this task's
  shape (multimodal reasoning + strict structured output) without paying
  for 3.8/3.7 Flash's long-horizon-agentic-coding overhead.
- Not using a Preview model (e.g. `gemini-3-flash-preview`) on purpose —
  preview models can be deprecated with only 2 weeks' notice, too risky
  for a deliverable you're presenting.

## API (backend)

- `POST /evaluate` — multipart form: `subject`, `question`, `max_marks`,
  `rubric_text`, `files[]` → JSON evaluation (runs the ADK agent).
- `POST /evaluate/pdf` — same inputs → downloadable PDF report.
- `GET /health` — confirms agent + API key are loaded.

## Guardrails already in place

- Marks are clamped server-side in `main.py` — the displayed score can
  never exceed `max_marks`, regardless of model output.
- The agent's `output_schema` structurally prevents free-text/rambling
  output — malformed JSON isn't a failure mode we have to defend against.

## Next steps (in order, after today)

1. Add a professor override/edit step before finalizing marks — the
   original plan flagged this: AI grading needs a human QC layer, don't
   ship AI-only final marks.
2. Rubric templates (save/reuse per subject/question).
3. Swap `InMemorySessionService` for a persistent one if you need
   evaluation history across restarts.
4. Move to Cloud Run once you need real concurrency; load-test before
   promising any specific requests/minute number.