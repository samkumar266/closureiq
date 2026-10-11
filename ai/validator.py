"""Public answer-validation contract for the guarded agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    """The fail-closed validation outcome."""

    valid: bool
    reason: str | None = None


def validate(
    answer: str,
    tool_results: list[dict[str, Any]],
    *,
    timezone: str = "America/Chicago",
) -> ValidationResult:
    """Validate an answer against only the current turn's tool results."""
    from .chat import validate_answer

    valid = validate_answer(answer, tool_results, timezone=timezone)
    return ValidationResult(valid=valid, reason=None if valid else "claim could not be verified")
