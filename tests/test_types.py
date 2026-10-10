from datetime import datetime

import pytest
from pydantic import ValidationError

from api.engine import (
    Facility,
    FacilityPolicy,
    InputEvidence,
    Policy,
    Recommendation,
    SourceHealth,
    evaluate,
)


def _facility() -> Facility:
    return Facility(
        facility_id="kc-service-center",
        name="Kansas City Service Center",
        location={"lat": 39.0997, "lon": -94.5786, "timezone": "America/Chicago"},
        hours={"open": "07:30", "close": "16:00"},
        arrival_window={"start": "07:00", "end": "08:30"},
        departure_window={"start": "15:00", "end": "16:30"},
        commute_buffer_min=45,
        notification_lead_min=90,
        earliest_departure="06:15",
        assembly_point="North parking lot",
        manager_id="e_001",
        backup_manager_id="e_002",
        on_call_id="e_003",
        gauge={"usgs_site": "06893000", "nwps_id": "KCDM7"},
        policy_version="policy-2026-10-10.1",
    )


def _evidence() -> list[InputEvidence]:
    return [
        InputEvidence(
            id="in_1",
            role="drove",
            source="NWS alerts",
            label="No active alerts",
            value={"active_count": 0},
            fetched_at="2026-10-10T16:00:00-05:00",
            snapshot_id="snap_0001",
        )
    ]


def test_posture_and_parameter_validation() -> None:
    result = evaluate(
        _evidence(),
        [
            SourceHealth(
                source="NWS alerts",
                status="fresh",
                fetched_at="2026-10-10T16:00:00-05:00",
                last_good_snapshot_id="snap_0001",
                last_good_age_minutes=1,
                max_age_minutes=10,
                reason=None,
            )
        ],
        _facility(),
        [],
        Policy(policy_version="policy-2026-10-10.1"),
        datetime.fromisoformat("2026-10-10T16:01:00-05:00"),
        evaluation_id="eval_0001",
        data_mode="live",
    )
    assert result.posture == "normal_operations"
    assert set(result.parameters) == {"monitoring", "next_update"}
    assert result.safety_instruction is None


def test_degraded_source_health_cannot_produce_high_confidence_normal() -> None:
    result = evaluate(
        _evidence(),
        [
            SourceHealth(
                source="NWS alerts",
                status="missing",
                fetched_at="2026-10-10T15:30:00-05:00",
                last_good_snapshot_id="snap_0000",
                last_good_age_minutes=31,
                max_age_minutes=10,
                reason="request failed",
            )
        ],
        _facility(),
        [],
        Policy(policy_version="policy-2026-10-10.1"),
        datetime.fromisoformat("2026-10-10T16:01:00-05:00"),
        evaluation_id="eval_0002",
        data_mode="live",
    )
    assert result.confidence.level == "low"
    assert result.missing_evidence
    assert result.parameters["monitoring"] == "elevated"


def test_naive_now_is_rejected_by_both_interfaces() -> None:
    with pytest.raises(ValueError, match="timezone"):
        evaluate("eval_0001", FacilityPolicy(
            facility_id="facility",
            open_time="07:30",
            close_time="16:00",
            arrival_start="07:00",
            arrival_end="08:30",
            departure_start="15:00",
            departure_end="16:30",
            commute_buffer_min=45,
            notification_lead_min=90,
            policy_version="policy-2026-10-10.1",
        ), _evidence(), datetime(2026, 10, 10, 16, 1))

    with pytest.raises(ValueError, match="timezone"):
        evaluate(
            _evidence(),
            [],
            _facility(),
            [],
            Policy(policy_version="policy-2026-10-10.1"),
            datetime(2026, 10, 10, 16, 1),
            evaluation_id="eval_0001",
            data_mode="live",
        )


def test_unknown_input_role_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InputEvidence.model_validate({
            "id": "in_1",
            "role": "invalid",
            "source": "NWS alerts",
            "label": "No active alerts",
            "value": {},
            "fetched_at": "2026-10-10T16:00:00-05:00",
            "snapshot_id": "snap_0001",
        })


def test_unknown_posture_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Recommendation.model_validate({
            "hypothetical": False,
            "evaluation_id": "eval_0001",
            "supersedes": None,
            "facility_id": "facility",
            "evaluated_at": "2026-10-10T16:00:00-05:00",
            "policy_version": "policy-2026-10-10.1",
            "data_mode": "live",
            "posture": "not_a_posture",
            "raw_posture": "normal_operations",
            "held_by_hysteresis": False,
            "parameters": {},
            "safety_instruction": None,
            "decision_deadline": None,
            "confidence": {"level": "low", "reasons": []},
            "inputs": [],
            "thresholds_crossed": [],
            "thresholds_not_crossed": [],
            "missing_evidence": [],
            "flip_list": [],
            "rationale": "test",
        })


def test_explicit_nullable_input_fields_remain_null() -> None:
    evidence = InputEvidence(
        id="in_2",
        role="context",
        source="NWS forecast grid",
        label="No forecast",
        value=None,
        unit=None,
        onset=None,
        ends=None,
        fetched_at="2026-10-10T16:00:00-05:00",
        snapshot_id="snap_0002",
    )
    serialized = evidence.model_dump(mode="json")
    assert serialized["value"] is None
    assert serialized["unit"] is None
    assert serialized["onset"] is None
    assert serialized["ends"] is None


def test_invalid_canonical_arguments_are_not_guessed() -> None:
    with pytest.raises(TypeError, match="canonical evaluate requires"):
        evaluate([], [], _facility())
