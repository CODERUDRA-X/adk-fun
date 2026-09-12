"""
NoteGrade AI — Backend
=======================
This does NOT reimplement evaluation logic — it runs the actual ADK agent
(notegrade_agent.root_agent) via ADK's Runner, the same way `adk web` does
internally. This file exists only to add what ADK's dev UI doesn't give you
for a real product: a file-upload HTTP API and PDF report generation.

Flow: HTTP request -> build multimodal Content -> ADK Runner runs the agent
-> structured EvaluationResult comes back -> JSON response / PDF report.

Run:
    pip install -r requirements.txt --break-system-packages
    export GOOGLE_API_KEY=your_key_here
    uvicorn main:app --reload --port 8001
    (Note: 8001, not 8000 — `adk web`/`adk run` for the agent demo uses 8000;
    running both on the same port causes a socket conflict.)
"""

import os
import sys
import json
import uuid
import mimetypes
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

# Make the sibling notegrade_agent package importable regardless of CWD
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# Auto-load the SAME .env the agent uses (notegrade_agent/.env), so you only
# ever have to set GOOGLE_API_KEY in ONE place, whether you run this via
# uvicorn or via `adk web`/`adk run`. Safe no-op if the file is missing.
load_dotenv(os.path.join(_PROJECT_ROOT, "notegrade_agent", ".env"))

from notegrade_agent.agent import root_agent, EvaluationResult  # noqa: E402

from pdf_report import generate_pdf_report

APP_NAME = "notegrade"

app = FastAPI(title="NoteGrade AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.environ.get("GOOGLE_API_KEY"):
    print("WARNING: GOOGLE_API_KEY not set. Set it before evaluating.")

# One process-wide session service + runner for the agent. Sessions are
# created per-request below (each evaluation is a stateless, single-turn
# interaction — no need to persist chat history across evaluations).
session_service = InMemorySessionService()
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)


def build_user_prompt(subject: str, question: str, max_marks: float, rubric_text: str) -> str:
    return f"""Subject: {subject or "N/A"}
Question: {question or "N/A"}
Maximum marks: {max_marks}

Rubric (criteria and marks allocation):
{rubric_text or "No explicit rubric given — create reasonable criteria that sum to the maximum marks."}

Evaluate the attached student submission."""


def file_to_part(file_bytes: bytes, filename: str) -> types.Part:
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"
    return types.Part.from_bytes(data=file_bytes, mime_type=mime_type)


async def run_agent(prompt_text: str, file_parts: List[types.Part]) -> dict:
    """Runs the ADK agent for one evaluation and returns the parsed structured result."""
    user_id = "notegrade-user"
    session_id = f"eval-{uuid.uuid4().hex}"

    await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )

    parts = [types.Part.from_text(text=prompt_text)] + file_parts
    new_message = types.Content(role="user", parts=parts)

    final_text = None
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=new_message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text

    if final_text is None:
        raise HTTPException(status_code=502, detail="Agent produced no final response.")

    try:
        return json.loads(final_text)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=502, detail="Agent did not return valid structured JSON.")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": root_agent.name,
        "model": root_agent.model,
        "api_key_set": bool(os.environ.get("GOOGLE_API_KEY")),
    }


@app.post("/evaluate")
async def evaluate(
    subject: str = Form(""),
    question: str = Form(""),
    max_marks: float = Form(...),
    rubric_text: str = Form(""),
    files: List[UploadFile] = File(...),
):
    if not os.environ.get("GOOGLE_API_KEY"):
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not configured on server.")
    if not files:
        raise HTTPException(status_code=400, detail="At least one file (image/PDF) is required.")

    prompt_text = build_user_prompt(subject, question, max_marks, rubric_text)

    file_parts = []
    for f in files:
        content = await f.read()
        if content:
            file_parts.append(file_to_part(content, f.filename))

    if not file_parts:
        raise HTTPException(status_code=400, detail="Uploaded files were empty.")

    result = await run_agent(prompt_text, file_parts)

    # Safety clamp: never let displayed marks exceed maximum, regardless of model output
    result["maximum_marks"] = max_marks
    if result.get("marks_obtained", 0) > max_marks:
        result["marks_obtained"] = max_marks

    return JSONResponse(content={
        "subject": subject,
        "question": question,
        "evaluation": result,
    })


@app.post("/report/pdf")
async def get_pdf_report(payload: dict):
    """
    Renders a PDF from an ALREADY-COMPUTED evaluation (the exact JSON
    returned by /evaluate). Does NOT call the agent again — this is
    deliberate: re-running the agent for the PDF was causing two problems:
      1. A second Gemini call can return a slightly different score than
         what's already on screen (LLM output isn't perfectly deterministic
         across calls) — confusing "why do the numbers not match" bugs.
      2. Re-sending the full images/PDF for a second full agent run made
         this the slowest, heaviest request in the app — the one most
         likely to hit a flaky connection (which browsers then mislabel
         as a CORS error, even though CORS is configured correctly).

    Expected body: {"subject": str, "question": str, "evaluation": {...}}
    i.e. exactly the JSON /evaluate already returned to the frontend.
    """
    subject = payload.get("subject", "")
    question = payload.get("question", "")
    evaluation = payload.get("evaluation")

    if not evaluation:
        raise HTTPException(status_code=400, detail="Missing 'evaluation' in request body.")

    pdf_path = generate_pdf_report(
        subject=subject,
        question=question,
        evaluation=evaluation,
    )
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename="NoteGrade_Evaluation.pdf",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)