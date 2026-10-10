"""Policy-independent hazard evaluation primitives.

This module evaluates threshold facts only. It deliberately does not select a
posture, rank hazards, infer unknown tiers, or validate alert geography.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from collections.abc import Mapping
import math
from typing import Any

from .policy_validation import (
    PROPOSED_THRESHOLD_IDS,
    PolicyConfigurationError,
    policy_values,
    threshold_definitions,
)
from .types import AlertTier, HazardClass, InputEvidence


@dataclass(frozen=True)
class EventInterval:
    """An aware event interval, when an evidence item supplies both endpoints."""

    onset: datetime
    ends: datetime

    def __post_init__(self) -> None:
        _require_aware(self.onset, "onset")
        _require_aware(self.ends, "ends")
        if self.ends < self.onset:
            raise ValueError("event interval ends before onset")


@dataclass(frozen=True)
class ThresholdObservation:
    """The result of comparing one evidence value with one policy cutoff."""

    threshold_id: str
    input_id: str
    cutoff: float
    actual: float
    unit: str
    crossed: bool
    margin: float | None
    distance: float | None


@dataclass(frozen=True)
class HazardResult:
    """Typed threshold facts for one hazard, with no posture decision."""

    hazard_class: HazardClass | str
    alert_tier: AlertTier | None
    event_interval: EventInterval | None
    thresholds_crossed: tuple[ThresholdObservation, ...]
    thresholds_not_crossed: tuple[ThresholdObservation, ...]
    distance_to_next_threshold: float | None


def threshold_definition(
    policy: Mapping[str, Any] | Any, threshold_id: str
) -> Mapping[str, Any]:
    """Look up one active threshold; proposed T12 is never returned."""

    if threshold_id in PROPOSED_THRESHOLD_IDS:
        raise PolicyConfigurationError(f"{threshold_id} is proposed and inactive")
    for definition in threshold_definitions(policy):
        if definition["id"] == threshold_id:
            return definition
    raise PolicyConfigurationError(f"active threshold is not configured: {threshold_id}")


def compare_numeric(
    actual: float | int,
    cutoff: float | int,
    *,
    unit: str,
    expected_unit: str,
    threshold_id: str = "threshold",
) -> ThresholdObservation:
    """Compare a numeric value at a policy boundary using matching units."""

    if unit != expected_unit:
        raise ValueError(
            f"{threshold_id} unit mismatch: expected {expected_unit}, received {unit}"
        )
    if isinstance(actual, bool) or isinstance(cutoff, bool):
        raise TypeError(f"{threshold_id} numeric values cannot be boolean")
    actual_value = float(actual)
    cutoff_value = float(cutoff)
    if not math.isfinite(actual_value) or not math.isfinite(cutoff_value):
        raise ValueError(f"{threshold_id} numeric values must be finite")
    crossed = actual_value >= cutoff_value
    difference = actual_value - cutoff_value
    return ThresholdObservation(
        threshold_id=threshold_id,
        input_id="",
        cutoff=cutoff_value,
        actual=actual_value,
        unit=unit,
        crossed=crossed,
        margin=difference if crossed else None,
        distance=-difference if not crossed else None,
    )


def evaluate_numeric_threshold(
    evidence: InputEvidence,
    policy: Mapping[str, Any] | Any,
    threshold_id: str,
) -> ThresholdObservation:
    """Evaluate one numeric evidence item against its configured cutoff."""

    definition = threshold_definition(policy, threshold_id)
    cutoff = definition["cutoff"]
    unit = definition.get("unit")
    if not isinstance(cutoff, (int, float)) or isinstance(cutoff, bool):
        raise PolicyConfigurationError(f"{threshold_id} requires a numeric cutoff")
    if not isinstance(unit, str):
        raise PolicyConfigurationError(f"{threshold_id} requires a supported unit")
    if not isinstance(evidence.value, (int, float)) or isinstance(evidence.value, bool):
        raise TypeError(f"{threshold_id} evidence value must be numeric")
    if evidence.unit != unit:
        raise ValueError(
            f"{threshold_id} unit mismatch: expected {unit}, received {evidence.unit}"
        )
    result = compare_numeric(
        evidence.value,
        cutoff,
        unit=unit,
        expected_unit=unit,
        threshold_id=threshold_id,
    )
    return ThresholdObservation(
        threshold_id=result.threshold_id,
        input_id=evidence.id,
        cutoff=result.cutoff,
        actual=result.actual,
        unit=result.unit,
        crossed=result.crossed,
        margin=result.margin,
        distance=result.distance,
    )


def event_mapping(
    policy: Mapping[str, Any] | Any,
    event_name: str,
) -> tuple[str, AlertTier] | None:
    """Find a configured event mapping; unknown names remain unresolved."""

    events = policy_values(policy).get("events")
    if not isinstance(events, Mapping):
        raise PolicyConfigurationError("policy.events must be a mapping")
    matches: list[tuple[str, AlertTier]] = []
    for hazard, tiers in events.items():
        if not isinstance(hazard, str) or not isinstance(tiers, Mapping):
            raise PolicyConfigurationError("malformed policy event mapping")
        for tier, names in tiers.items():
            if not isinstance(names, list):
                raise PolicyConfigurationError(f"{hazard}.{tier} must be a list")
            if event_name in names:
                try:
                    matches.append((hazard, AlertTier(tier)))
                except ValueError as exc:
                    raise PolicyConfigurationError(
                        f"unsupported alert tier in policy: {tier}"
                    ) from exc
    if len(matches) > 1:
        raise PolicyConfigurationError(f"event maps to multiple hazards: {event_name}")
    return matches[0] if matches else None


def build_hazard_result(
    hazard_class: HazardClass | str,
    alert_tier: AlertTier | None,
    evidence: InputEvidence,
    observations: tuple[ThresholdObservation, ...],
) -> HazardResult:
    """Assemble threshold facts without interpreting their policy effects."""

    interval = None
    if evidence.onset is not None or evidence.ends is not None:
        if evidence.onset is None or evidence.ends is None:
            raise ValueError("event interval requires both onset and ends")
        interval = EventInterval(evidence.onset, evidence.ends)
    crossed = tuple(item for item in observations if item.crossed)
    not_crossed = tuple(item for item in observations if not item.crossed)
    distances = [item.distance for item in not_crossed if item.distance is not None]
    return HazardResult(
        hazard_class=hazard_class,
        alert_tier=alert_tier,
        event_interval=interval,
        thresholds_crossed=crossed,
        thresholds_not_crossed=not_crossed,
        distance_to_next_threshold=min(distances) if distances else None,
    )


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone offset")
