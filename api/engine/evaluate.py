"""Public evaluator with a temporary legacy compatibility adapter."""

from __future__ import annotations

from datetime import datetime
from typing import overload

from .engine import evaluate as _legacy_evaluate
from .models import EvaluationContext, FacilityPolicy, InputEvidence, Recommendation
from .types import Confidence, Employee, Facility, MissingEvidence, Policy, SourceHealth
from .rationale import build_rationale


@overload
def evaluate(
    evidence: list[InputEvidence],
    source_health: list[SourceHealth],
    facility: Facility,
    roster: list[Employee],
    policy: Policy,
    now: datetime,
    *,
    evaluation_id: str,
    data_mode: str,
    previous: Recommendation | None = None,
) -> Recommendation:
    ...


@overload
def evaluate(
    evaluation_id: str,
    facility: FacilityPolicy,
    inputs: list[InputEvidence],
    now: datetime,
    previous: EvaluationContext | None = None,
    data_mode: str = "live",
    hypothetical: bool = False,
) -> Recommendation:
    ...


def evaluate(*args: object, **kwargs: object) -> Recommendation:
    """Evaluate policy using the canonical interface or a legacy call.

    The legacy positional form is retained only while existing callers migrate:
    ``evaluate(evaluation_id, facility, inputs, now, ...)``. It delegates to
    the same existing functional implementation as the canonical adapter and
    should be removed after downstream callers use the new signature.
    """

    if _is_legacy_call(args):
        return _evaluate_legacy(args, kwargs)
    return _evaluate_canonical(args, kwargs)


def _is_legacy_call(args: tuple[object, ...]) -> bool:
    return (
        len(args) >= 4
        and isinstance(args[0], str)
        and isinstance(args[1], FacilityPolicy)
        and isinstance(args[2], list)
        and isinstance(args[3], datetime)
    )


def _evaluate_legacy(
    args: tuple[object, ...], kwargs: dict[str, object]
) -> Recommendation:
    allowed = {"previous", "data_mode", "hypothetical"}
    unexpected = set(kwargs) - allowed
    if unexpected:
        raise TypeError(f"unexpected legacy keyword arguments: {sorted(unexpected)}")
    if len(args) > 7:
        raise TypeError("legacy evaluate accepts at most seven positional arguments")
    positional_names = (
        "evaluation_id",
        "facility",
        "inputs",
        "now",
        "previous",
        "data_mode",
        "hypothetical",
    )
    values = dict(zip(positional_names, args))
    for name in allowed:
        if name in values and name in kwargs:
            raise TypeError(f"{name} was provided both positionally and by keyword")
        if name in kwargs:
            values[name] = kwargs[name]
    return _legacy_evaluate(
        values["evaluation_id"],
        values["facility"],
        values["inputs"],
        values["now"],
        values.get("previous"),
        values.get("data_mode", "live"),
        values.get("hypothetical", False),
    )


def _evaluate_canonical(
    args: tuple[object, ...], kwargs: dict[str, object]
) -> Recommendation:
    if len(args) != 6:
        raise TypeError(
            "canonical evaluate requires evidence, source_health, facility, "
            "roster, policy, and now"
        )
    required_keywords = {"evaluation_id", "data_mode"}
    missing = required_keywords - kwargs.keys()
    if missing:
        raise TypeError(f"missing canonical keyword arguments: {sorted(missing)}")
    unexpected = set(kwargs) - {"evaluation_id", "data_mode", "previous"}
    if unexpected:
        raise TypeError(f"unexpected canonical keyword arguments: {sorted(unexpected)}")

    evidence, source_health, facility, roster, policy, now = args
    if not isinstance(evidence, list) or not all(
        isinstance(item, InputEvidence) for item in evidence
    ):
        raise TypeError("evidence must be a list of InputEvidence")
    if not isinstance(source_health, list) or not all(
        isinstance(item, SourceHealth) for item in source_health
    ):
        raise TypeError("source_health must be a list of SourceHealth")
    if not isinstance(facility, Facility):
        raise TypeError("facility must be a Facility")
    if not isinstance(roster, list) or not all(
        isinstance(item, Employee) for item in roster
    ):
        raise TypeError("roster must be a list of Employee")
    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    if not isinstance(now, datetime):
        raise TypeError("now must be a datetime")
    if not isinstance(kwargs["evaluation_id"], str):
        raise TypeError("evaluation_id must be a string")
    if not isinstance(kwargs["data_mode"], str):
        raise TypeError("data_mode must be a string")

    previous = kwargs.get("previous")
    if previous is not None and not isinstance(previous, Recommendation):
        raise TypeError("canonical previous must be a Recommendation or None")
    if policy.policy_version != facility.policy_version:
        raise ValueError("facility and policy versions must match")

    legacy_previous = _previous_context(previous)
    result = _legacy_evaluate(
        kwargs["evaluation_id"],
        facility.to_policy(),
        evidence,
        now,
        legacy_previous,
        kwargs["data_mode"],
        False,
    )
    result = _merge_source_health(result, source_health, now)
    primary_missing = any(
        "nws alert" in item.source.lower() and item.status != "fresh"
        for item in source_health
    )
    if primary_missing and previous is not None:
        result = result.model_copy(
            update={
                "posture": previous.posture,
                "held_by_hysteresis": previous.posture != result.raw_posture,
                "parameters": previous.parameters,
            }
        )
        result.rationale = build_rationale(
            result.posture,
            result.parameters,
            result.inputs,
            result.thresholds_crossed,
            result.thresholds_not_crossed,
            result.missing_evidence,
            result.confidence,
            result.decision_deadline,
        )
    return result


def _previous_context(previous: Recommendation | None) -> EvaluationContext | None:
    if previous is None:
        return None
    return EvaluationContext(
        evaluation_id=previous.evaluation_id,
        facility_id=previous.facility_id,
        evaluated_at=previous.evaluated_at,
        posture=previous.posture,
        raw_posture=previous.raw_posture,
        held_by_hysteresis=previous.held_by_hysteresis,
    )


def _merge_source_health(
    result: Recommendation,
    source_health: list[SourceHealth],
    now: datetime,
) -> Recommendation:
    """Prevent a degraded source-health report from becoming reassuring."""

    degraded = [item for item in source_health if item.status != "fresh"]
    if not degraded:
        return result

    existing = {item.source.lower() for item in result.missing_evidence}
    missing = list(result.missing_evidence)
    for health in degraded:
        if health.source.lower() in existing:
            continue
        age = health.last_good_age_minutes
        if age is None and health.fetched_at is not None:
            age = max(0.0, (now - health.fetched_at).total_seconds() / 60)
        missing.append(
            MissingEvidence(
                source=health.source,
                reason=health.reason or f"{health.source} is {health.status}",
                last_good_snapshot_id=health.last_good_snapshot_id,
                last_good_age_minutes=age,
                max_age_minutes=health.max_age_minutes,
            )
        )
    confidence_reasons = [item.reason for item in missing]
    parameters = result.parameters
    if result.posture == "normal_operations":
        parameters = {**parameters, "monitoring": "elevated"}
    update: dict[str, object] = {
        "missing_evidence": missing,
        "confidence": Confidence(level="low", reasons=confidence_reasons),
        "parameters": parameters,
    }
    updated = result.model_copy(
        update=update
    )
    updated.rationale = build_rationale(
        updated.posture,
        updated.parameters,
        updated.inputs,
        updated.thresholds_crossed,
        updated.thresholds_not_crossed,
        updated.missing_evidence,
        updated.confidence,
        updated.decision_deadline,
    )
    return updated
