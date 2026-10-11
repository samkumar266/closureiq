"""What the agent's tools show the model: real values, small, with ids and local times."""
import json

from ai.chat import MAX_RESULT_CHARS, _bounded, _clock, summarize_evaluation, summarize_whatif, validate_answer
from api.app.routes import _AgentBackend

CLOSURE = json.loads(open("mocks/closure.json").read())


def _big(result):
    big = json.loads(json.dumps(result))
    big["inputs"].append({"id": "in_9", "role": "context", "source": "NWS forecast grid", "label": "grid",
                          "fetched_at": big["evaluated_at"], "snapshot_id": "snap_9", "stale": False,
                          "value": {"windGust": [{"value": float(v), "unit": "mph", "valid_time": f"t{v}"}
                                                 for v in range(3000)]}})
    return big


def test_evaluation_summary_keeps_values_not_just_keys():
    big = _big(CLOSURE)
    assert len(json.dumps(big)) > MAX_RESULT_CHARS
    summary = _bounded(summarize_evaluation(big))
    assert "note" not in summary  # not collapsed to key names
    assert summary["posture"] == "closure" and summary["rationale"] == CLOSURE["rationale"]
    assert summary["decision_deadline_local"] == "Fri 4:45 AM"
    assert summary["thresholds_crossed"][0]["actual"] == CLOSURE["thresholds_crossed"][0]["actual"]
    assert summary["what_would_change"] == CLOSURE["flip_list"]
    grid = next(i for i in summary["inputs"] if i["id"] == "in_9")
    assert grid["forecast_peaks"]["windGust"] == {"max": 2999.0, "unit": "mph", "valid_time": "t2999"}
    assert validate_answer("The decision is needed by Fri 4:45 AM.", [summary], timezone="America/Chicago")


def test_whatif_summary_has_id_hypothetical_and_thresholds():
    out = {"whatif_id": "wif_0042", "based_on": CLOSURE["evaluation_id"], "changed_fields": ["posture"],
           "result": dict(CLOSURE, posture="delayed_arrival",
                          assumed_alert={"event": "Severe Thunderstorm Warning", "severity": "Severe",
                                         "certainty": "Likely", "tier": "warning",
                                         "onset": "2026-10-16T03:00:00+00:00", "ends": "2026-10-16T09:00:00+00:00"})}
    s = summarize_whatif({**out, "overrides": {"in_1": {"severity": "Severe"}}}, CLOSURE)
    assert s["hypothetical"] is True and s["whatif_id"] == s["evaluation_id"] == "wif_0042"
    assert s["current_posture"] == "closure" and s["hypothetical_posture"] == "delayed_arrival" and s["posture_changed"]
    assert s["assumed_alert"]["onset_local"] == "Thu 10:00 PM"
    assert len(json.dumps(s)) < MAX_RESULT_CHARS


def test_clock_has_no_bare_day_number():
    assert _clock("2026-10-11T04:45:00-05:00", "2026-10-10T22:00:00-05:00") == "Sun 4:45 AM"


def test_roster_filter_cannot_telework_returns_everyone_ineligible():
    backend = _AgentBackend(None, {"facility_id": "kc-service-center"})
    everyone = backend.list_affected_employees(None)["employees"]
    cannot = backend.list_affected_employees("cannot_telework")["employees"]
    assert len(everyone) == 25
    assert cannot and all(not e["telework_eligible"] for e in cannot)
    assert len(cannot) == sum(1 for e in everyone if not e["telework_eligible"])
