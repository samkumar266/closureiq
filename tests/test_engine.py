"""Contract-focused tests for the deterministic policy engine."""

from datetime import datetime
from pathlib import Path
import json

from api.engine import EvaluationContext, FacilityPolicy, InputEvidence, evaluate


ROOT = Path(__file__).parents[1]


def _facility() -> FacilityPolicy:
    return FacilityPolicy(
        facility_id="stl-service-center",
        open_time="07:30",
        close_time="16:00",
        arrival_start="07:00",
        arrival_end="08:30",
        departure_start="15:00",
        departure_end="16:30",
        commute_buffer_min=45,
        notification_lead_min=90,
        policy_version="policy-2026-10-10.1",
    )


def _inputs(name: str) -> list[InputEvidence]:
    payload = json.loads((ROOT / "mocks" / name).read_text(encoding="utf-8"))
    return [InputEvidence.model_validate(item) for item in payload["inputs"]]


def test_warning_with_wind_trigger_recommends_early_dismissal() -> None:
    result = evaluate(
        "eval_0044",
        _facility(),
        _inputs("early_dismissal.json"),
        datetime.fromisoformat("2026-10-13T12:10:00-05:00"),
    )
    assert result.posture == "early_dismissal"
    assert result.raw_posture == "early_dismissal"
    assert {item.id for item in result.thresholds_crossed} >= {"T1", "T2", "T3", "T4", "T5"}


def test_stale_alert_lowers_confidence_and_does_not_escalate() -> None:
    result = evaluate(
        "eval_0033",
        _facility(),
        _inputs("degraded_low_confidence.json"),
        datetime.fromisoformat("2026-10-14T14:30:00-05:00"),
    )
    assert result.posture == "normal_operations"
    assert result.parameters["monitoring"] == "elevated"
    assert result.confidence.level == "low"
    assert result.missing_evidence


def test_recommendation_is_replay_deterministic() -> None:
    args = ("eval_0038", _facility(), _inputs("normal.json"), datetime.fromisoformat("2026-10-12T05:40:00-05:00"))
    assert evaluate(*args).model_dump(mode="json") == evaluate(*args).model_dump(mode="json")


def test_fixture_postures_match_contract() -> None:
    expected = {
        "normal.json": "normal_operations",
        "delayed_arrival.json": "delayed_arrival",
        "early_dismissal.json": "early_dismissal",
        "unscheduled_leave.json": "unscheduled_leave_or_telework",
        "closure.json": "closure",
    }
    for filename, posture in expected.items():
        payload = json.loads((ROOT / "mocks" / filename).read_text(encoding="utf-8"))
        result = evaluate(
            payload["evaluation_id"],
            _facility(),
            [InputEvidence.model_validate(item) for item in payload["inputs"]],
            datetime.fromisoformat(payload["evaluated_at"]),
        )
        assert result.posture == posture
        assert result.supersedes is None
        assert result.decision_deadline is None if posture == "normal_operations" else result.decision_deadline is not None


def test_first_downgrade_is_held_until_second_spaced_evaluation() -> None:
    previous = EvaluationContext(
        evaluation_id="eval_0001",
        facility_id="stl-service-center",
        evaluated_at=datetime.fromisoformat("2026-10-13T12:00:00-05:00"),
        posture="early_dismissal",
        raw_posture="early_dismissal",
    )
    result = evaluate(
        "eval_0002",
        _facility(),
        _inputs("normal.json"),
        datetime.fromisoformat("2026-10-13T12:20:00-05:00"),
        previous=previous,
    )
    assert result.posture == "early_dismissal"
    assert result.raw_posture == "normal_operations"
    assert result.held_by_hysteresis is True


def test_second_lower_evaluation_after_fifteen_minutes_releases_hold() -> None:
    previous = EvaluationContext(
        evaluation_id="eval_0002",
        facility_id="stl-service-center",
        evaluated_at=datetime.fromisoformat("2026-10-12T05:34:00-05:00"),
        posture="early_dismissal",
        raw_posture="normal_operations",
        held_by_hysteresis=True,
    )
    result = evaluate(
        "eval_0003",
        _facility(),
        _inputs("normal.json"),
        datetime.fromisoformat("2026-10-12T05:49:00-05:00"),
        previous=previous,
    )
    assert result.posture == "normal_operations"
    assert result.raw_posture == "normal_operations"
    assert result.held_by_hysteresis is False


def test_failed_primary_alert_is_low_confidence_and_preserves_previous_posture() -> None:
    failed = _inputs("early_dismissal.json")
    failed[0] = failed[0].model_copy(update={"ok": False, "stale": True})
    previous = EvaluationContext(
        evaluation_id="eval_0010",
        facility_id="stl-service-center",
        evaluated_at=datetime.fromisoformat("2026-10-13T11:00:00-05:00"),
        posture="closure",
        raw_posture="closure",
    )
    result = evaluate(
        "eval_0011",
        _facility(),
        failed,
        datetime.fromisoformat("2026-10-13T12:10:00-05:00"),
        previous=previous,
    )
    assert result.posture == "closure"
    assert result.raw_posture == "normal_operations"
    assert result.confidence.level == "low"
    assert any("fetch failed" in item.reason for item in result.missing_evidence)


def test_unknown_certainty_cannot_produce_high_confidence() -> None:
    inputs = _inputs("normal.json")
    alert = inputs[0].model_copy(
        update={"value": {**inputs[0].value, "certainty": "Unknown"}}
    )
    inputs[0] = alert
    result = evaluate(
        "eval_0040",
        _facility(),
        inputs,
        datetime.fromisoformat("2026-10-12T05:40:00-05:00"),
    )
    assert result.confidence.level == "low"
    assert "certainty Unknown" in result.confidence.reasons


def test_numeric_and_tier_flips_are_deterministic_and_deduplicated() -> None:
    args = (
        "eval_0041",
        _facility(),
        _inputs("delayed_arrival.json"),
        datetime.fromisoformat("2027-01-14T03:20:00-06:00"),
    )
    first = evaluate(*args)
    second = evaluate(*args)
    assert first.flip_list
    assert first.flip_list == second.flip_list
    keys = [(item.change, item.resulting_posture) for item in first.flip_list]
    assert len(keys) == len(set(keys))
