"""Deterministic confidence calculation for normalized engine evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .types import Confidence, InputEvidence, MissingEvidence


def calculate_confidence(
    inputs: list[InputEvidence],
    alert: InputEvidence | None,
    missing_evidence: list[MissingEvidence],
    now: datetime,
    policy: dict[str, Any],
) -> Confidence:
    """Apply the configured confidence ladder to all applicable facts."""
    reasons: list[str] = []
    level = "high"
    if missing_evidence:
        level = "low"
        reasons.extend(item.reason for item in missing_evidence)
    failed = [item for item in inputs if not item.ok]
    if failed:
        level = "low"
        reasons.extend(f"{item.source} fetch failed" for item in failed)
    if any(item.stale for item in inputs):
        level = "low"
        reasons.append("one or more sources are stale")

    certainty = _alert_value(alert, "certainty")
    if certainty in {"Unlikely", "Unknown"}:
        level = "low"
        reasons.append(f"certainty {certainty}")
    elif certainty == "Possible":
        level = _lowest(level, "medium")
        reasons.append("certainty Possible")
    elif certainty in {"Likely", "Observed"}:
        reasons.append(f"certainty {certainty}")

    onset_hours = None
    confidence_rules = policy.get("confidence", {})
    high_limit = float(confidence_rules.get("high", {}).get("onset_within_h", 12))
    medium_limit = 36.0
    if alert is not None and alert.onset is not None:
        onset_hours = (alert.onset - now).total_seconds() / 3600
    if onset_hours is not None and onset_hours > medium_limit:
        level = "low"
        reasons.append("onset over 36 h away")
    elif onset_hours is not None and onset_hours >= high_limit:
        level = _lowest(level, "medium")
        reasons.append("onset 12 to 36 h away")
    elif onset_hours is not None:
        reasons.append("onset under 12 h away")

    if not reasons:
        reasons.append("all sources fresh")
    elif level == "high":
        reasons.insert(0, "all sources fresh")
    return Confidence(level=level, reasons=_deduplicate(reasons))


def _alert_value(alert: InputEvidence | None, key: str) -> str:
    if alert is None or not isinstance(alert.value, dict):
        return ""
    value = alert.value.get(key)
    return str(value) if value is not None else ""


def _lowest(current: str, candidate: str) -> str:
    rank = {"high": 0, "medium": 1, "low": 2}
    return candidate if rank[candidate] > rank[current] else current


def _deduplicate(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(reasons))
