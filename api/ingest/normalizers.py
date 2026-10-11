"""Pure parsing helpers shared by the API fallback and engine integration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

TIER_ORDER = {"none": 0, "advisory": 1, "watch": 2, "warning": 3}


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def alert_end(props: dict[str, Any]) -> str | None:
    return props.get("ends") or props.get("expires")


def classify_hazard(event: str | None) -> str:
    text = (event or "").lower()
    if any(word in text for word in ("flood", "flash flood", "coastal flood", "river flood")):
        return "flood"
    if any(word in text for word in ("winter", "ice storm", "blizzard", "snow", "freezing rain", "sleet")):
        return "winter storm"
    if any(word in text for word in ("thunderstorm", "wind", "tornado", "hurricane", "tropical storm", "landspout")):
        return "thunderstorm and wind"
    return "other"


def classify_tier(props: dict[str, Any]) -> str:
    """Use the event name's warning/watch/advisory wording, not severity alone."""
    event = (props.get("event") or "").lower()
    if "warning" in event or "emergency" in event:
        return "warning"
    if "watch" in event:
        return "watch"
    if any(x in event for x in ("advisory", "statement", "outlook", "special weather")):
        return "advisory"
    return "advisory"


def normalize_alerts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter NWS FeatureCollection to current, actual alert features.

    Update messages supersede referenced alert IDs; Cancel messages remove referenced
    alerts. Active NWS point responses usually already include the current representation,
    but handling references here makes saved evidence replay more faithful.
    """
    features = payload.get("features", [])
    if not isinstance(features, list):
        return []
    by_id: dict[str, dict[str, Any]] = {}
    cancelled: set[str] = set()
    replaced: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        status = str(props.get("status") or "").lower()
        message_type = str(props.get("messageType") or "").lower()
        if status != "actual":
            continue
        if message_type in {"test", "exercise", "draft"}:
            continue
        references = props.get("references") or []
        referenced_ids = [str(ref.get("identifier") or ref.get("@id") or "") for ref in references if isinstance(ref, dict)]
        referenced_ids = [ref for ref in referenced_ids if ref]
        if message_type == "cancel":
            cancelled.update(referenced_ids)
            continue
        if message_type == "update":
            replaced.update(referenced_ids)
        alert_id = str(props.get("id") or feature.get("id") or "")
        if alert_id:
            by_id[alert_id] = feature
    for old_id in cancelled | replaced:
        by_id.pop(old_id, None)
    normalized: list[dict[str, Any]] = []
    for feature in by_id.values():
        props = feature.get("properties") or {}
        normalized.append({
            "id": props.get("id") or feature.get("id"),
            "event": props.get("event"),
            "headline": props.get("headline"),
            "description": props.get("description"),
            "instruction": props.get("instruction"),
            "severity": props.get("severity"),
            "certainty": props.get("certainty"),
            "urgency": props.get("urgency"),
            "status": props.get("status"),
            "message_type": props.get("messageType"),
            "onset": props.get("onset"),
            "ends": alert_end(props),
            "expires": props.get("expires"),
            "sent": props.get("sent"),
            "sender_name": props.get("senderName"),
            "area_desc": props.get("areaDesc"),
            "affected_zones": props.get("affectedZones") or [],
            "tier": classify_tier(props),
            "hazard": classify_hazard(props.get("event")),
            "raw_properties": props,
            "geometry": feature.get("geometry"),
        })
    return normalized


def highest_alert_tier(payload: dict[str, Any] | None) -> str:
    alerts = normalize_alerts(payload or {})
    if not alerts:
        return "none"
    return max((a["tier"] for a in alerts), key=lambda tier: TIER_ORDER.get(tier, 0), default="none")


def extract_usgs_latest(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the most recent USGS value for stage (00065) and discharge (00060)."""
    time_series = (payload.get("value") or {}).get("timeSeries") or []
    readings: dict[str, dict[str, Any]] = {}
    for series in time_series:
        try:
            variable_code = series["variable"]["variableCode"][0]["value"]
            values = series["values"][0]["value"]
            if not values:
                continue
            item = max(values, key=lambda v: v.get("dateTime") or "")
            readings[variable_code] = {
                "value": float(item["value"]),
                "unit": "ft" if variable_code == "00065" else "ft3/s",
                "observed_at": item.get("dateTime"),
                "qualifiers": item.get("qualifiers") or [],
            }
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    if not readings:
        return None
    return {"stage": readings.get("00065"), "discharge": readings.get("00060")}
