"""Contract-shaped threshold catalogue, read from api/engine/policy.yaml (the single source of truth).

Contract: "Anchor text and anchor_url come from api/engine/policy.yaml". Every crossed threshold in an
evaluation carries the same sourced anchor, so the dashboard can show why each cutoff is defensible.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from api.engine.policy_validation import threshold_definitions, validate_policy

POLICY_PATH = Path(__file__).resolve().parents[1] / "engine" / "policy.yaml"
_POLICY: dict[str, Any] = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
validate_policy(_POLICY)
POLICY_VERSION = _POLICY["policy_version"]

# DEPRECATED(closureiq) START: hard-coded copy of the thresholds with placeholder anchors, no URLs, and
# statuses that disagreed with policy.yaml. Now built from policy.yaml below.
# POLICY_VERSION = "policy-2026-10-10.1"
# THRESHOLDS = [
#     {"id": "T1", "hazard": "all", "input": "NWS alert tier", "cutoff": "warning", "unit": None,
#      "effect": "Allows delay, dismissal or closure", "anchor": "NWS warning definition", "anchor_url": None, "status": "confirm"},
#     {"id": "T2", "hazard": "all", "input": "NWS severity", "cutoff": "Severe or Extreme", "unit": None,
#      "effect": "Allows dismissal and closure", "anchor": "NWS alert severity field", "anchor_url": None, "status": "confirm"},
#     {"id": "T3", "hazard": "all", "input": "NWS certainty", "cutoff": "Likely or Observed", "unit": None,
#      "effect": "Required for posture above unscheduled leave/telework", "anchor": "NWS alert certainty field", "anchor_url": None, "status": "confirm"},
#     {"id": "T4", "hazard": "thunderstorm and wind", "input": "Forecast wind gust", "cutoff": 58, "unit": "mph",
#      "effect": "Numeric trigger", "anchor": "Typical NWS severe-thunderstorm wind criterion", "anchor_url": None, "status": "confirm"},
#     {"id": "T5", "hazard": "thunderstorm and wind", "input": "Sustained wind for 1 hour", "cutoff": 40, "unit": "mph",
#      "effect": "Numeric trigger", "anchor": "Typical NWS high-wind warning criterion; offices vary", "anchor_url": None, "status": "confirm"},
#     {"id": "T6", "hazard": "winter storm", "input": "Ice accumulation", "cutoff": 0.25, "unit": "in",
#      "effect": "Numeric trigger", "anchor": "Typical NWS ice-storm warning criterion", "anchor_url": None, "status": "confirm"},
#     {"id": "T7", "hazard": "flood", "input": "Gauge stage", "cutoff": 32, "unit": "ft",
#      "effect": "Numeric trigger at KCDM7", "anchor": "NWS flood category for gauge KCDM7", "anchor_url": None, "status": "verified"},
#     {"id": "T8", "hazard": "flood", "input": "Gauge stage", "cutoff": 35, "unit": "ft",
#      "effect": "Counts as extreme severity at KCDM7", "anchor": "NWS flood category for gauge KCDM7", "anchor_url": None, "status": "verified"},
#     {"id": "T9", "hazard": "flood", "input": "Gauge stage", "cutoff": 29, "unit": "ft",
#      "effect": "Raises monitoring only", "anchor": "NWS action stage for gauge KCDM7", "anchor_url": None, "status": "verified"},
#     {"id": "T10", "hazard": "all", "input": "Clearing buffer", "cutoff": 60, "unit": "min",
#      "effect": "Sets delay_until", "anchor": "Team choice", "anchor_url": None, "status": "assumption"},
#     {"id": "T11", "hazard": "all", "input": "Commute buffer / notification lead", "cutoff": {"commute_buffer_min": 45, "notification_lead_min": 90}, "unit": "min",
#      "effect": "Sets decision deadline", "anchor": "Team choice in facility profile", "anchor_url": None, "status": "assumption"},
# ]
# DEPRECATED(closureiq) END


def _contract_cutoff(cutoff: Any) -> Any:
    # policy.yaml lists categorical cutoffs ([Severe, Extreme]); the contract shows them as text.
    return " or ".join(str(item) for item in cutoff) if isinstance(cutoff, list) else cutoff


THRESHOLDS = [
    {"id": item["id"], "hazard": item.get("hazard"), "input": item.get("input"),
     "cutoff": _contract_cutoff(item.get("cutoff")), "unit": item.get("unit"), "effect": item.get("effect"),
     "anchor": item.get("anchor"), "anchor_url": item.get("anchor_url"), "status": item.get("status")}
    for item in threshold_definitions(_POLICY)
]
_BY_ID = {item["id"]: item for item in THRESHOLDS}
# Office-specific criteria pages (policy.yaml local_anchors), keyed by threshold id, then NWS office code.
_LOCAL = {item["id"]: dict(item.get("local_anchors") or {}) for item in threshold_definitions(_POLICY)}


def anchor_for(threshold_id: str, office: str | None = None) -> dict[str, Any]:
    """The sourced anchor for one threshold: the facility's own NWS office page if policy.yaml has one,
    otherwise the default (national) source. The office code comes from the facility's /points response."""
    local = _LOCAL.get(threshold_id, {}).get((office or "").upper())
    item = local or _BY_ID.get(threshold_id, {})
    return {"anchor": item.get("anchor"), "anchor_url": item.get("anchor_url")}


def thresholds_response() -> dict:
    return {"policy_version": POLICY_VERSION, "thresholds": THRESHOLDS}
