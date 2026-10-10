"""Pure what-if evaluation over immutable evidence snapshots."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from typing import Any

from .evaluate import evaluate
from .models import EvaluationContext, FacilityPolicy, InputEvidence, Recommendation
from .types import WhatIfResult

_CHANGED_FIELDS = (
    "posture",
    "raw_posture",
    "held_by_hysteresis",
    "confidence",
    "decision_deadline",
    "parameters",
)


def run_what_if(
    base: Recommendation,
    evidence: list[InputEvidence],
    overrides: dict[str, Any],
    *,
    facility: FacilityPolicy,
    now: datetime | None = None,
    previous: EvaluationContext | None = None,
    data_mode: str | None = None,
    what_if_id: str = "wif_0001",
) -> WhatIfResult:
    """Evaluate validated overrides without mutating any caller-owned values."""
    if not base.evaluation_id:
        raise ValueError("base evaluation must have an evaluation_id")
    modified = _apply_overrides(evidence, overrides)
    recommendation = evaluate(
        what_if_id,
        facility,
        modified,
        now or base.evaluated_at,
        previous=previous,
        data_mode=data_mode or base.data_mode,
        hypothetical=True,
    )
    changed = _changed_fields(base, recommendation)
    return WhatIfResult(
        **recommendation.model_dump(),
        based_on=base.evaluation_id,
        changed_fields=changed,
    )


def _apply_overrides(
    evidence: list[InputEvidence],
    overrides: dict[str, Any],
) -> list[InputEvidence]:
    result = deepcopy(evidence)
    for key, value in overrides.items():
        matches = [index for index, item in enumerate(result) if item.id == key]
        if len(matches) != 1:
            raise ValueError(f"unknown what-if input id: {key}")
        index = matches[0]
        if value is None:
            result.pop(index)
            continue
        item = result[index]
        result[index] = item.model_copy(
            update={"value": _validated_value(value, item)}
        )
    return result


def _validated_value(value: Any, item: InputEvidence) -> Any:
    """Validate and copy a scalar or merge a dictionary-valued input."""
    current = item.value
    if isinstance(current, dict):
        if not isinstance(value, dict):
            raise ValueError(f"{item.id} requires a dictionary override")
        merged = dict(current)
        merged.update(deepcopy(value))
        return merged
    if isinstance(value, dict):
        raise ValueError(f"{item.id} requires a scalar override")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"{item.id} has an invalid override value")
    return value


def _changed_fields(
    base: Recommendation, hypothetical: Recommendation
) -> list[str]:
    changed: list[str] = []
    for field in _CHANGED_FIELDS:
        if _comparable(getattr(base, field)) != _comparable(
            getattr(hypothetical, field)
        ):
            changed.append(field)
    return changed


def _comparable(value: Any) -> Any:
    """Compare values using the same JSON representation exposed by the API."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _comparable(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_comparable(item) for item in value]
    try:
        return json.loads(json.dumps(value, sort_keys=True))
    except (TypeError, ValueError):
        return str(value)
