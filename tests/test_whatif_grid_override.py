"""A what-if on the forecast grid re-checks T4-T6 instead of only relabelling the input."""
from datetime import datetime, timezone

from api.app.engine_adapter import fallback_evaluate
from api.facilities import get_facility

NOW = datetime(2026, 10, 16, 17, 0, tzinfo=timezone.utc)


def _snap(source, payload, sid):
    return {"id": sid, "facility_id": "kc-service-center", "source": source, "ok": True,
            "fetched_at_wall": NOW.isoformat(), "raw_payload_json": payload, "http_status": 200}


def _grid(gust_kmh):
    return {"properties": {"windGust": {"uom": "wmoUnit:km_h-1",
                                        "values": [{"validTime": "2026-10-16T17:00:00+00:00/PT1H", "value": gust_kmh}]}}}


def test_gust_override_crosses_t4():
    facility = get_facility("kc-service-center")
    snaps = [_snap("NWS alerts", {"features": []}, "snap_1"), _snap("NWS forecast grid", _grid(30.0), "snap_2")]
    base = fallback_evaluate(None, facility, snaps, evaluated_at=NOW)
    assert not any(t["id"] == "T4" for t in base["thresholds_crossed"])
    grid_id = next(i["id"] for i in base["inputs"] if i["source"] == "NWS forecast grid")
    what_if = fallback_evaluate(None, facility, snaps, evaluated_at=NOW, overrides={grid_id: {"windGust": 65}},
                                hypothetical=True)
    t4 = next(t for t in what_if["thresholds_crossed"] if t["id"] == "T4")
    assert t4["actual"] == 65.0 and t4["margin"] == 7.0
    gust = next(i for i in what_if["inputs"] if i["id"] == grid_id)["value"]["windGust"]
    assert gust == [{"value": 65.0, "unit": "mph", "valid_time": "what-if"}]
    assert f"What-if overrides applied to {grid_id}." in what_if["rationale"]
