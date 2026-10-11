"""A real "Shelter in place" line must not be overwritten by generic advice."""
from datetime import datetime, timedelta, timezone

from api.app.engine_adapter import fallback_evaluate
from api.facilities import get_facility


def _alert_snapshot(now: datetime, onset: datetime, ends: datetime, event: str) -> dict:
    payload = {"type": "FeatureCollection", "features": [{
        "id": "urn:test:1",
        "properties": {"id": "urn:test:1", "event": event, "headline": event, "severity": "Severe",
                       "certainty": "Likely", "urgency": "Immediate", "status": "Actual",
                       "messageType": "Alert", "onset": onset.isoformat(), "ends": ends.isoformat(),
                       "expires": ends.isoformat(), "sent": onset.isoformat(), "references": []}}]}
    return {"id": "snap_0001", "facility_id": "kc-service-center", "source": "NWS alerts", "ok": True,
            "fetched_at_wall": now.isoformat(), "raw_payload_json": payload, "http_status": 200}


def test_active_midday_warning_keeps_shelter_in_place_line():
    facility = get_facility("kc-service-center")
    now = datetime(2026, 10, 16, 17, 0, tzinfo=timezone.utc)  # 12:00 Chicago, outside both windows
    snap = _alert_snapshot(now, now - timedelta(minutes=10), now + timedelta(minutes=60), "Severe Thunderstorm Warning")
    result = fallback_evaluate(None, facility, [snap], evaluated_at=now)
    assert result["safety_instruction"].startswith("Shelter in place")


def test_upcoming_warning_still_gets_generic_advice():
    facility = get_facility("kc-service-center")
    now = datetime(2026, 10, 16, 17, 0, tzinfo=timezone.utc)
    snap = _alert_snapshot(now, now + timedelta(minutes=20), now + timedelta(minutes=50), "Flash Flood Warning")
    result = fallback_evaluate(None, facility, [snap], evaluated_at=now)
    assert "seek appropriate shelter if directed" in (result["safety_instruction"] or "")
