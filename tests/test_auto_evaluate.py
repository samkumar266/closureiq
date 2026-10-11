"""The scheduler records a new evaluation only when the decision changes."""
from api.app.routes import _decision_fingerprint


def _result(**changes):
    base = {
        "posture": "closure", "raw_posture": "closure", "confidence": {"level": "high", "reasons": []},
        "decision_deadline": "2026-10-11T04:45:00-07:00", "safety_instruction": None,
        "parameters": {"closed_from": "07:30", "closed_until": "16:00", "next_update": "2026-10-11T07:15:00-07:00"},
        "thresholds_crossed": [{"id": "T4"}, {"id": "T5"}], "missing_evidence": [],
        "inputs": [{"source": "NWS alerts", "value": [{"id": "alert-1"}]}],
    }
    base.update(changes)
    return base


def test_rerun_with_only_a_new_next_update_is_not_a_change():
    later = _result(parameters={"closed_from": "07:30", "closed_until": "16:00", "next_update": "2026-10-11T07:16:00-07:00"})
    assert _decision_fingerprint(_result()) == _decision_fingerprint(later)


def test_new_alert_posture_confidence_or_missing_source_is_a_change():
    base = _decision_fingerprint(_result())
    assert base != _decision_fingerprint(_result(inputs=[{"source": "NWS alerts", "value": [{"id": "alert-1"}, {"id": "alert-2"}]}]))
    assert base != _decision_fingerprint(_result(posture="unscheduled_leave_or_telework"))
    assert base != _decision_fingerprint(_result(confidence={"level": "low", "reasons": []}))
    assert base != _decision_fingerprint(_result(missing_evidence=[{"source": "NWS alerts"}]))
    assert base != _decision_fingerprint(_result(thresholds_crossed=[{"id": "T4"}]))
