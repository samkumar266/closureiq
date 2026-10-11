"""Pure, deterministic ClosureIQ policy evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from .models import (
    EvaluationContext,
    FacilityPolicy,
    Flip,
    InputEvidence,
    MissingEvidence,
    Recommendation,
    ThresholdResult,
)
from .confidence import calculate_confidence
from .rationale import build_rationale

POLICY_PATH = Path(__file__).with_name("policy.yaml")
_POLICY: dict[str, Any] = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
POSTURES = tuple(_POLICY["postures"])
_RANK = {posture: index for index, posture in enumerate(POSTURES)}


def evaluate(
    evaluation_id: str,
    facility: FacilityPolicy,
    inputs: list[InputEvidence],
    now: datetime,
    previous: EvaluationContext | None = None,
    data_mode: str = "live",
    hypothetical: bool = False,
) -> Recommendation:
    """Evaluate active T1-T11 without clock, network, randomness, or mutable state."""
    if now.tzinfo is None:
        raise ValueError("now must include a timezone offset")
    alert = _find_alert(inputs)
    crossed, not_crossed = _thresholds(inputs, alert)
    missing = _missing_evidence(inputs, now)
    raw_posture = _raw_posture(facility, alert, crossed)
    posture, held = _apply_hysteresis(raw_posture, previous, now)
    monitoring = _monitoring(alert, missing)
    next_update = _next_update(now, monitoring)
    parameters = _parameters(posture, facility, alert, now, next_update)
    deadline = _decision_deadline(facility, posture, alert, now)
    confidence = calculate_confidence(inputs, alert, missing, now, _POLICY)
    if _primary_source_missing(inputs, missing):
        if previous is not None:
            posture = previous.posture
            held = posture != raw_posture
        else:
            posture = "normal_operations"
            held = False
        monitoring = "elevated"
        parameters = _parameters(posture, facility, alert, now, next_update)
    result = Recommendation(
        hypothetical=hypothetical,
        evaluation_id=evaluation_id,
        supersedes=previous.evaluation_id if previous else None,
        facility_id=facility.facility_id,
        evaluated_at=now,
        policy_version=_POLICY["policy_version"],
        data_mode=data_mode,
        posture=posture,
        raw_posture=raw_posture,
        held_by_hysteresis=held,
        parameters=parameters,
        safety_instruction=None,
        decision_deadline=deadline,
        confidence=confidence,
        inputs=inputs,
        thresholds_crossed=crossed,
        thresholds_not_crossed=not_crossed,
        missing_evidence=missing,
        flip_list=_flips(alert, inputs, facility),
        rationale="",
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


def _find_alert(inputs: list[InputEvidence]) -> InputEvidence | None:
    for item in inputs:
        if "alert" in item.source.lower() and isinstance(item.value, dict):
            return item
    return None


def _number(inputs: list[InputEvidence], text: str) -> InputEvidence | None:
    for item in inputs:
        if text in item.label.lower() and isinstance(item.value, (int, float)) and not item.stale:
            return item
    return None


def _alert_value(alert: InputEvidence | None, key: str, default: str = "") -> str:
    if alert and isinstance(alert.value, dict):
        value = alert.value.get(key)
        return str(value) if value is not None else default
    return default


def _alert_tier(alert: InputEvidence | None) -> str:
    tier = _alert_value(alert, "highest_tier")
    if tier:
        return tier
    if alert is None:
        return ""
    label = alert.label.lower()
    if "warning" in label:
        return "warning"
    if "watch" in label:
        return "watch"
    if "advisory" in label:
        return "advisory"
    return "none"


def _thresholds(
    inputs: list[InputEvidence], alert: InputEvidence | None
) -> tuple[list[ThresholdResult], list[ThresholdResult]]:
    crossed: list[ThresholdResult] = []
    not_crossed: list[ThresholdResult] = []
    tier = _alert_tier(alert)
    severity = _alert_value(alert, "severity")
    certainty = _alert_value(alert, "certainty")
    _categorical(crossed, not_crossed, "T1", alert, "Warning", tier, tier == "warning")
    _categorical(crossed, not_crossed, "T2", alert, "Severe or Extreme", severity, severity in {"Severe", "Extreme"})
    _categorical(crossed, not_crossed, "T3", alert, "Likely or Observed", certainty, certainty in {"Likely", "Observed"})
    _numeric(inputs, crossed, not_crossed, "T4", "gust", 58, "mph")
    _numeric(inputs, crossed, not_crossed, "T5", "sustained", 40, "mph")
    _numeric(inputs, crossed, not_crossed, "T6", "ice", 0.25, "in")
    _numeric(inputs, crossed, not_crossed, "T7", "stage", 32, "ft")
    _numeric(inputs, crossed, not_crossed, "T8", "stage", 35, "ft")
    _numeric(inputs, crossed, not_crossed, "T9", "stage", 29, "ft")
    return crossed, not_crossed


def _categorical(
    crossed: list[ThresholdResult],
    not_crossed: list[ThresholdResult],
    threshold_id: str,
    item: InputEvidence | None,
    cutoff: str,
    actual: str,
    is_crossed: bool,
) -> None:
    if item is None:
        return
    result = ThresholdResult(id=threshold_id, input_id=item.id, cutoff=cutoff, actual=actual)
    (crossed if is_crossed else not_crossed).append(result)


def _numeric(
    inputs: list[InputEvidence],
    crossed: list[ThresholdResult],
    not_crossed: list[ThresholdResult],
    threshold_id: str,
    label: str,
    cutoff: float,
    unit: str,
) -> None:
    item = _number(inputs, label)
    if item is None:
        return
    actual = float(item.value)
    result = ThresholdResult(
        id=threshold_id,
        input_id=item.id,
        cutoff=cutoff,
        actual=item.value,
        unit=unit,
        margin=actual - cutoff if actual >= cutoff else None,
        distance=cutoff - actual if actual < cutoff else None,
        anchor=_anchor(threshold_id),
        anchor_url=_anchor_url(threshold_id),
    )
    (crossed if actual >= cutoff else not_crossed).append(result)


def _anchor(threshold_id: str) -> str | None:
    return next((item["anchor"] for item in _POLICY["thresholds"] if item["id"] == threshold_id), None)


def _anchor_url(threshold_id: str) -> str | None:
    return next((item.get("anchor_url") for item in _POLICY["thresholds"] if item["id"] == threshold_id), None)


def _raw_posture(
    facility: FacilityPolicy,
    alert: InputEvidence | None,
    crossed: list[ThresholdResult],
) -> str:
    if alert is None or alert.stale:
        return "normal_operations"
    tier = _alert_tier(alert)
    severe = _alert_value(alert, "severity") in {"Severe", "Extreme"}
    certain = _alert_value(alert, "certainty") in {"Likely", "Observed"}
    numeric = {item.id for item in crossed if item.id in {"T4", "T5", "T6", "T7", "T8", "T9"}}
    if tier != "warning":
        return "normal_operations"
    if not severe or not certain or not numeric:
        return "unscheduled_leave_or_telework"
    if "T8" in {item.id for item in crossed} or _spans_departure(alert, facility):
        return "closure" if _spans_arrival(alert, facility) else "early_dismissal"
    if _spans_arrival(alert, facility):
        return "delayed_arrival"
    return "unscheduled_leave_or_telework"


def _spans_arrival(alert: InputEvidence, facility: FacilityPolicy) -> bool:
    return _overlaps(alert, facility.arrival_start, facility.arrival_end)


def _spans_departure(alert: InputEvidence, facility: FacilityPolicy) -> bool:
    return _overlaps(alert, facility.departure_start, facility.departure_end)


def _overlaps(alert: InputEvidence, start: Any, end: Any) -> bool:
    if alert.onset is None or alert.ends is None:
        return False
    window_start = datetime.combine(alert.onset.date(), start, tzinfo=alert.onset.tzinfo)
    window_end = datetime.combine(alert.onset.date(), end, tzinfo=alert.onset.tzinfo)
    return alert.onset <= window_end and alert.ends >= window_start


def _apply_hysteresis(
    raw: str, previous: EvaluationContext | None, now: datetime
) -> tuple[str, bool]:
    if previous is None or _RANK[raw] >= _RANK[previous.posture]:
        return raw, False
    previous_raw = previous.raw_posture or previous.posture
    if (
        previous.held_by_hysteresis
        and _RANK[previous_raw] < _RANK[previous.posture]
        and now - previous.evaluated_at >= timedelta(minutes=15)
    ):
        return raw, False
    return previous.posture, True


def _missing_evidence(inputs: list[InputEvidence], now: datetime) -> list[MissingEvidence]:
    limits = _POLICY["confidence"]["freshness_limit_min"]
    result: list[MissingEvidence] = []
    for source in ("NWS alerts", "NWS forecast grid", "USGS gauge"):
        matching = [
            item
            for item in inputs
            if source.lower().rstrip("s") in item.source.lower()
        ]
        if not matching:
            continue
        item = matching[0]
        age = max(0.0, (now - item.fetched_at).total_seconds() / 60)
        limit = next((value for key, value in limits.items() if key in source.lower()), 120)
        if not item.ok or item.stale or age > limit:
            reason = f"{item.source} fetch failed" if not item.ok else f"{item.source} is stale"
            result.append(MissingEvidence(
                source=item.source,
                reason=reason,
                last_good_snapshot_id=item.snapshot_id,
                last_good_age_minutes=round(age, 2),
                max_age_minutes=limit,
            ))
    if inputs and _find_alert(inputs) is None:
        result.append(
            MissingEvidence(
                source="NWS alerts",
                reason="NWS alerts are missing",
                last_good_snapshot_id=None,
                last_good_age_minutes=None,
                max_age_minutes=limits.get("alerts", 10),
            )
        )
    return result


def _primary_source_missing(
    inputs: list[InputEvidence], missing: list[MissingEvidence]
) -> bool:
    return any(
        "nws alert" in item.source.lower() and (
            not item.ok or item.stale
        )
        for item in inputs
    ) or any("nws alert" in item.source.lower() for item in missing)


def _monitoring(alert: InputEvidence | None, missing: list[MissingEvidence]) -> str:
    return "elevated" if missing or _alert_tier(alert) in {"watch", "advisory"} else "normal"


def _next_update(now: datetime, monitoring: str) -> datetime:
    minutes = 60 if monitoring == "elevated" else 15
    return now + timedelta(minutes=minutes)


def _parameters(posture: str, facility: FacilityPolicy, alert: InputEvidence | None, now: datetime, next_update: datetime) -> dict[str, object]:
    if posture == "normal_operations":
        return {"monitoring": _monitoring(alert, []), "next_update": next_update}
    if posture == "delayed_arrival":
        return {"delay_until": (alert.ends + timedelta(minutes=60) if alert and alert.ends else next_update), "next_update": next_update}
    if posture == "early_dismissal":
        return {"dismiss_at": datetime.combine(now.date(), facility.departure_start, tzinfo=now.tzinfo), "next_update": next_update}
    if posture == "closure":
        return {"closed_from": datetime.combine(now.date(), facility.open_time, tzinfo=now.tzinfo), "closed_until": datetime.combine(now.date(), facility.close_time, tzinfo=now.tzinfo), "next_update": next_update}
    return {"next_update": next_update}


def _decision_deadline(facility: FacilityPolicy, posture: str, alert: InputEvidence | None, now: datetime) -> datetime | None:
    if posture == "normal_operations" or alert is None:
        return None
    affected = alert.onset or now
    return affected - timedelta(minutes=facility.notification_lead_min)


def _flips(
    alert: InputEvidence | None,
    inputs: list[InputEvidence],
    facility: FacilityPolicy,
) -> list[Flip]:
    """Re-evaluate just across active numeric and alert-tier boundaries."""
    flips: list[Flip] = []
    cutoffs = (
        ("gust", 58.0, "mph"),
        ("sustained", 40.0, "mph"),
        ("ice", 0.25, "in"),
        ("stage", 29.0, "ft"),
        ("stage", 32.0, "ft"),
        ("stage", 35.0, "ft"),
    )
    for label, cutoff, unit in cutoffs:
        item = _number(inputs, label)
        if item is None or item.unit != unit:
            continue
        actual = float(item.value)
        if actual >= cutoff:
            changed = item.model_copy(update={"value": cutoff - _epsilon(cutoff)})
            resulting = _variant_posture(inputs, changed, facility)
            flips.append(
                Flip(
                    change=f"{item.label} falls below {cutoff:g} {unit}",
                    resulting_posture=resulting,
                )
            )
        else:
            changed = item.model_copy(update={"value": cutoff + _epsilon(cutoff)})
            resulting = _variant_posture(inputs, changed, facility)
            flips.append(
                Flip(
                    change=f"{item.label} rises above {cutoff:g} {unit}",
                    resulting_posture=resulting,
                )
            )
    if alert is not None and _alert_tier(alert) == "watch":
        value = dict(alert.value) if isinstance(alert.value, dict) else {}
        value["highest_tier"] = "warning"
        changed = alert.model_copy(update={"value": value})
        resulting = _variant_posture(inputs, changed, facility)
        flips.append(
            Flip(change="Warning replaces the Watch", resulting_posture=resulting)
        )
    return _deduplicate_flips(flips)


def _variant_posture(
    inputs: list[InputEvidence],
    changed: InputEvidence,
    facility: FacilityPolicy,
) -> str:
    variant = [changed if item.id == changed.id else item for item in inputs]
    alert = _find_alert(variant)
    crossed, _ = _thresholds(variant, alert)
    return _raw_posture(facility, alert, crossed)


def _epsilon(cutoff: float) -> float:
    return max(abs(cutoff) * 0.001, 0.001)


def _deduplicate_flips(flips: list[Flip]) -> list[Flip]:
    seen: set[tuple[str, str]] = set()
    result: list[Flip] = []
    for flip in flips:
        key = (flip.change, flip.resulting_posture.value)
        if key not in seen:
            seen.add(key)
            result.append(flip)
    return result
