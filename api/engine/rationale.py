"""Template-based rationale generation from completed engine facts."""

from __future__ import annotations

from datetime import datetime

from .types import Confidence, InputEvidence, MissingEvidence, ThresholdResult


def build_rationale(
    posture: str,
    parameters: dict[str, object],
    inputs: list[InputEvidence],
    crossed: list[ThresholdResult],
    not_crossed: list[ThresholdResult],
    missing: list[MissingEvidence],
    confidence: Confidence,
    decision_deadline: datetime | None,
) -> str:
    """Build a paste-ready paragraph without inventing unavailable values."""
    text = f"Recommend {posture.replace('_', ' ')}."
    alert = next((item for item in inputs if "alert" in item.source.lower()), None)
    if alert is not None and isinstance(alert.value, dict):
        severity = alert.value.get("severity")
        certainty = alert.value.get("certainty")
        details = [alert.label]
        if severity is not None:
            details.append(f"severity {severity}")
        if certainty is not None:
            details.append(f"certainty {certainty}")
        if alert.onset is not None and alert.ends is not None:
            details.append(f"runs from {alert.onset.isoformat()} to {alert.ends.isoformat()}")
        text += " " + ", ".join(details) + "."
    if crossed:
        facts = []
        for threshold in crossed:
            if threshold.margin is not None:
                facts.append(
                    f"{threshold.id} actual {threshold.actual} exceeds "
                    f"{threshold.cutoff} by {threshold.margin} {threshold.unit or ''}".strip()
                )
        if facts:
            text += " " + "; ".join(facts) + "."
    if not_crossed:
        facts = [
            f"{item.id} is {item.distance} {item.unit or ''} below cutoff".strip()
            for item in not_crossed
            if item.distance is not None
        ]
        if facts:
            text += " " + "; ".join(facts) + "."
    if missing:
        text += " This is not an all-clear: " + "; ".join(
            item.reason for item in missing
        ) + "."
    text += f" Confidence is {confidence.level}."
    if decision_deadline is not None:
        text += f" A decision is needed by {decision_deadline.isoformat()}."
    else:
        next_update = parameters.get("next_update")
        if isinstance(next_update, datetime):
            text += f" The next evaluation runs at {next_update.isoformat()}."
    return text
