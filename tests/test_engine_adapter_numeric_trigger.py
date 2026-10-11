"""Posture table: a strong warning needs a crossed numeric trigger for delay, dismissal or closure.

Measured wind from the facility's airport station counts as a numeric trigger (T4 gusts, T5 sustained).
"""
from datetime import datetime, timedelta, timezone

from api.app.engine_adapter import fallback_evaluate
from api.facilities import get_facility

from tests.test_engine_adapter_shelter import _alert_snapshot

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)  # 5:00 AM in Kingman (America/Phoenix)


def _warning():
    # High Wind Warning covering both commute windows (7:00-8:30 and 15:00-16:30 local).
    return _alert_snapshot(NOW, NOW, NOW + timedelta(hours=15), "High Wind Warning")


def _observations(gust_kmh: float | None, speed_kmh: float = 20.0) -> dict:
    features = [{"properties": {"timestamp": (NOW - timedelta(minutes=5)).isoformat(),
                                "windGust": {"unitCode": "wmoUnit:km_h-1", "value": gust_kmh},
                                "windSpeed": {"unitCode": "wmoUnit:km_h-1", "value": speed_kmh}}}]
    return {"id": "snap_0002", "facility_id": "kingman-az-service-center", "source": "NWS station observations",
            "ok": True, "fetched_at_wall": NOW.isoformat(), "raw_payload_json": {"features": features}, "http_status": 200}


def _fresh(source: str) -> dict:
    # The other required sources must be fresh, or the fallback forces unscheduled leave on its own.
    return {"id": f"snap_{source}", "facility_id": "kingman-az-service-center", "source": source, "ok": True,
            "fetched_at_wall": NOW.isoformat(), "raw_payload_json": {"properties": {}}, "http_status": 200}


def _evidence(observation: dict) -> list[dict]:
    return [_warning(), _fresh("NWS forecast grid"), _fresh("NWS hourly forecast"), observation]


def test_warning_without_numeric_trigger_is_unscheduled_leave_with_flip_to_closure():
    result = fallback_evaluate(None, get_facility("kingman-az-service-center"), _evidence(_observations(None)), evaluated_at=NOW)
    assert result["posture"] == "unscheduled_leave_or_telework"
    assert {"T1", "T2", "T3"} <= {t["id"] for t in result["thresholds_crossed"]}
    assert any(f["resulting_posture"] == "closure" for f in result["flip_list"])


def test_measured_gust_over_58_mph_crosses_t4_and_drives_closure():
    result = fallback_evaluate(None, get_facility("kingman-az-service-center"), _evidence(_observations(100.0)), evaluated_at=NOW)
    t4 = [t for t in result["thresholds_crossed"] if t["id"] == "T4"]
    assert t4 and t4[0]["actual"] == 62.1  # 100 km/h
    assert result["posture"] == "closure"


def test_missing_observation_is_reported_but_does_not_force_the_posture():
    stale = _observations(100.0)
    stale["raw_payload_json"]["features"][0]["properties"]["timestamp"] = (NOW - timedelta(hours=3)).isoformat()
    result = fallback_evaluate(None, get_facility("kingman-az-service-center"), _evidence(stale), evaluated_at=NOW)
    assert any(m["source"] == "NWS station observations" for m in result["missing_evidence"])
    assert "T4" not in {t["id"] for t in result["thresholds_crossed"]}
