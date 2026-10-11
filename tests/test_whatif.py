"""Focused tests for pure what-if evaluation."""

from datetime import datetime
import json
from pathlib import Path

import pytest

from api.engine import FacilityPolicy, InputEvidence, Recommendation, run_what_if

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


def _base() -> tuple[Recommendation, list[InputEvidence]]:
    payload = json.loads((ROOT / "mocks" / "normal.json").read_text())
    base = Recommendation.model_validate(payload)
    evidence = [InputEvidence.model_validate(item) for item in payload["inputs"]]
    return base, evidence


def test_scalar_id_override_is_hypothetical_and_does_not_mutate_inputs() -> None:
    base, evidence = _base()
    original = [item.model_dump() for item in evidence]
    result = run_what_if(
        base,
        evidence,
        {"in_2": 60},
        facility=_facility(),
        now=datetime.fromisoformat("2026-10-12T05:40:00-05:00"),
        what_if_id="wif_0001",
    )
    assert result.hypothetical is True
    assert result.based_on == base.evaluation_id
    assert result.evaluation_id == "wif_0001"
    assert result.changed_fields == ["confidence"]
    assert [item.model_dump() for item in evidence] == original


def test_dict_id_override_merges_without_mutating_existing_keys() -> None:
    base, evidence = _base()
    evidence[0] = evidence[0].model_copy(
        update={"value": {"active_count": 0, "event": "Watch"}}
    )
    result = run_what_if(
        base,
        evidence,
        {"in_1": {"severity": "Severe"}},
        facility=_facility(),
        now=base.evaluated_at,
    )
    assert result.inputs[0].value == {
        "active_count": 0,
        "event": "Watch",
        "severity": "Severe",
    }
    assert evidence[0].value == {"active_count": 0, "event": "Watch"}


def test_none_removes_input() -> None:
    base, evidence = _base()
    result = run_what_if(
        base,
        evidence,
        {"in_1": None},
        facility=_facility(),
        now=base.evaluated_at,
    )
    assert all(item.id != "in_1" for item in result.inputs)


def test_evidence_id_none_removes_evidence() -> None:
    base, evidence = _base()
    result = run_what_if(
        base,
        evidence,
        {"in_1": None},
        facility=_facility(),
        now=base.evaluated_at,
    )
    assert all(item.id != "in_1" for item in result.inputs)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"missing": 1}, "unknown"),
        ({"alert_severity": "Severe"}, "unknown"),
        ({"in_1": 1}, "dictionary"),
    ],
)
def test_invalid_overrides_are_rejected(
    overrides: dict[str, object], message: str
) -> None:
    base, evidence = _base()
    with pytest.raises(ValueError, match=message):
        run_what_if(base, evidence, overrides, facility=_facility())
