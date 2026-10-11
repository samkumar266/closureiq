"""ClosureIQ explanation agent built with Strands Agents SDK."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from strands import Agent, tool

from .model import get_model

SYSTEM_PROMPT = """You explain an existing ClosureIQ weather evaluation.
Use get_evaluation to retrieve the evaluation before answering.
Explain the recorded posture, evidence, crossed thresholds, confidence, and rationale.
The deterministic policy engine made the decision: do not invent, alter, or recommend a
different posture. If asked for a what-if or a different decision, explain that this
agent can only explain the recorded evaluation. Distinguish recorded facts from
uncertainty and preserve the evaluation's local times."""

_MOCK_PATH = Path(__file__).resolve().parents[1] / "mocks" / "delayed_arrival.json"


@tool
def get_evaluation(evaluation_id: str) -> dict[str, Any]:
    """Return the recorded delayed-arrival evaluation for the requested evaluation ID."""
    if not evaluation_id.strip():
        raise ValueError("evaluation_id must not be empty")
    try:
        with _MOCK_PATH.open(encoding="utf-8") as evaluation_file:
            evaluation = json.load(evaluation_file)
    except FileNotFoundError as exc:
        raise RuntimeError(f"mock evaluation file was not found: {_MOCK_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"mock evaluation file is malformed: {_MOCK_PATH}") from exc

    if not isinstance(evaluation, dict):
        raise RuntimeError("mock evaluation must contain a JSON object")
    if evaluation.get("evaluation_id") != evaluation_id:
        raise ValueError(f"evaluation {evaluation_id!r} was not found")
    return evaluation


def build_agent() -> Agent:
    """Build the explanation-only ClosureIQ agent."""
    return Agent(model=get_model(), tools=[get_evaluation], system_prompt=SYSTEM_PROMPT)
