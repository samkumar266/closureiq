"""Deterministic ClosureIQ policy engine."""

from .evaluate import evaluate
from .engine import policy_thresholds
from .models import (
    EvaluationContext,
    FacilityPolicy,
    InputEvidence,
    Recommendation,
    WhatIfResult,
)
from .whatif import run_what_if
from .types import Employee, Facility, Policy, SourceHealth

__all__ = [
    "EvaluationContext",
    "Employee",
    "Facility",
    "FacilityPolicy",
    "InputEvidence",
    "Policy",
    "Recommendation",
    "WhatIfResult",
    "SourceHealth",
    "evaluate",
    "policy_thresholds",
    "run_what_if",
]
