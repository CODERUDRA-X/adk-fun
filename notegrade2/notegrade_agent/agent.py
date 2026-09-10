"""
NoteGrade AI — ADK Agent Definition
=====================================
This is THE agent. Everything else (FastAPI backend, PDF report) is
plumbing around it. This file is also directly runnable via:

    adk run notegrade_agent          # CLI chat with the agent
    adk web                          # browser UI (run from parent dir)

...which is what makes it teachable: "this is the agent, this is its
model, this is its instruction, this is its output contract" — no hidden
machinery.

Structured output: instead of hoping the model returns clean JSON, we
give ADK a Pydantic schema via `output_schema`. ADK enforces this at the
API level (response_schema under the hood), so malformed output is a
non-issue by construction — not something we have to defensively parse.

Note: setting `output_schema` on an LlmAgent means it operates purely
as a single-shot structured responder (no tool calls from this agent).
That's intentional here — evaluation is one reasoning pass, not a
multi-step tool-using task. If you later add tools (e.g. a Google
Sheets tool to log grades), move output parsing to an explicit
`output_key` + separate formatting step per ADK's multi-agent pattern.
"""

from typing import List

from google.adk.agents import Agent
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Structured output contract — the model MUST return exactly this shape.
# This replaces free-text "I think the student deserves 7 marks..." output.
# ---------------------------------------------------------------------------
class CriterionScore(BaseModel):
    name: str = Field(description="Name of the rubric criterion, e.g. 'Definition'")
    score: float = Field(description="Marks awarded for this criterion")
    max_score: float = Field(description="Maximum marks possible for this criterion")
    feedback: str = Field(description="Short feedback specific to this criterion")


class EvaluationResult(BaseModel):
    marks_obtained: float = Field(description="Total marks awarded, must not exceed maximum_marks")
    maximum_marks: float = Field(description="Maximum marks possible for this submission")
    criteria: List[CriterionScore] = Field(description="Per-criterion score breakdown; scores must sum to marks_obtained")
    strengths: List[str] = Field(description="What the student did well")
    weaknesses: List[str] = Field(description="Where the answer fell short")
    overall_feedback: str = Field(description="A short paragraph summarizing the evaluation")
    suggestions: List[str] = Field(description="Concrete suggestions for the student to improve")


AGENT_INSTRUCTION = """You are "NoteGrade AI", an academic evaluator agent.

You will be given, in the user turn:
- Subject, Question, Maximum marks, and a Rubric (criteria + marks allocation)
- The student's submitted answer as image(s), a PDF, and/or typed text

Evaluate the submission on:
- correctness
- completeness
- conceptual understanding
- relevance to the question
- presentation / clarity

Rules:
- Do NOT award marks above the maximum for any criterion or the total.
- Do NOT invent information that is not present in the submission.
- If handwriting is unclear or illegible in places, say so explicitly in
  weaknesses rather than guessing what it might say.
- The sum of all criteria scores MUST equal marks_obtained.
- If no explicit rubric is given, create reasonable criteria yourself that
  sum to maximum_marks.
- Be a fair but honest evaluator — this feedback is used for real academic
  purposes, not just encouragement.
- Output ONLY the structured evaluation fields. No extra commentary,
  no markdown, no preamble.
"""


# ---------------------------------------------------------------------------
# The agent. This is the ONLY required element of an ADK agent project —
# root_agent is what `adk run` / `adk web` look for.
# ---------------------------------------------------------------------------
root_agent = Agent(
    model="gemini-3.6-flash",
    name="notegrade_evaluator",
    description=(
        "Evaluates a student's submitted answer (image/PDF/text) against a "
        "question, maximum marks, and rubric, returning a structured score "
        "breakdown and feedback."
    ),
    instruction=AGENT_INSTRUCTION,
    output_schema=EvaluationResult,
)