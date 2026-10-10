from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from api.engine.hazards import (
    build_hazard_result,
    compare_numeric,
    event_mapping,
    evaluate_numeric_threshold,
    threshold_definition,
)
from api.engine.policy_validation import PolicyConfigurationError, validate_policy
from api.engine.timing import (
    add_minutes,
    facility_zone,
    intervals_overlap,
    overlap_duration,
    require_aware,
    to_facility_time,
)
from api.engine.types import AlertTier, HazardClass, InputEvidence


ROOT = Path(__file__).parents[1]


def _policy() -> dict[str, object]:
    return yaml.safe_load(
        (ROOT / "api" / "engine" / "policy.yaml").read_text(encoding="utf-8")
    )


def _evidence(value: float, unit: str) -> InputEvidence:
    return InputEvidence(
        id="in_1",
        role="drove",
        source="NWS forecast grid",
        label="Forecast value",
        value=value,
        unit=unit,
        fetched_at="2026-10-10T16:00:00-05:00",
        snapshot_id="snap_0001",
    )


@pytest.mark.parametrize(
    ("threshold_id", "value", "unit", "crossed", "margin", "distance"),
    [
        ("T4", 58, "mph", True, 0, None),
        ("T4", 57.5, "mph", False, None, 0.5),
        ("T6", 0.25, "in", True, 0, None),
        ("T7", 31.5, "ft", False, None, 0.5),
    ],
)
def test_numeric_threshold_boundaries_and_distances(
    threshold_id: str,
    value: float,
    unit: str,
    crossed: bool,
    margin: float | None,
    distance: float | None,
) -> None:
    result = evaluate_numeric_threshold(_evidence(value, unit), _policy(), threshold_id)
    assert result.crossed is crossed
    assert result.margin == margin
    assert result.distance == distance


def test_compare_numeric_rejects_unit_mismatch() -> None:
    with pytest.raises(ValueError, match="unit mismatch"):
        compare_numeric(1, 1, unit="ft", expected_unit="in", threshold_id="T6")


def test_missing_and_malformed_threshold_configuration_is_explicit() -> None:
    missing = _policy()
    missing["thresholds"] = [
        item for item in missing["thresholds"] if item["id"] != "T4"
    ]
    with pytest.raises(PolicyConfigurationError, match="T4"):
        validate_policy(missing)

    malformed = _policy()
    malformed["thresholds"][3]["unit"] = "knots"
    with pytest.raises(PolicyConfigurationError, match="unsupported unit"):
        validate_policy(malformed)


def test_policy_event_mapping_is_read_from_yaml() -> None:
    policy = _policy()
    assert event_mapping(policy, "High Wind Warning") == (
        "thunderstorm_wind",
        AlertTier.WARNING,
    )
    assert event_mapping(policy, "unknown event") is None


def test_malformed_event_mapping_is_rejected() -> None:
    policy = _policy()
    policy["events"]["flood"]["warning"] = "Flood Warning"
    with pytest.raises(PolicyConfigurationError, match="non-empty list"):
        validate_policy(policy)


def test_twelve_is_not_an_active_threshold() -> None:
    policy = _policy()
    validate_policy(policy)
    with pytest.raises(PolicyConfigurationError, match="proposed and inactive"):
        threshold_definition(policy, "T12")


def test_hazard_result_groups_observations_and_event_interval() -> None:
    evidence = InputEvidence(
        id="in_1",
        role="drove",
        source="NWS forecast grid",
        label="Forecast value",
        value=62,
        unit="mph",
        onset="2026-10-10T17:00:00-05:00",
        ends="2026-10-10T18:00:00-05:00",
        fetched_at="2026-10-10T16:00:00-05:00",
        snapshot_id="snap_0001",
    )
    observation = evaluate_numeric_threshold(evidence, _policy(), "T4")
    result = build_hazard_result(
        HazardClass.THUNDERSTORM_WIND,
        AlertTier.WARNING,
        evidence,
        (observation,),
    )
    assert result.event_interval is not None
    assert [item.threshold_id for item in result.thresholds_crossed] == ["T4"]
    assert result.distance_to_next_threshold is None


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        require_aware(datetime(2026, 10, 10, 16, 0))


def test_facility_timezone_conversion_and_dst() -> None:
    before_dst = datetime(2026, 11, 1, 6, 30, tzinfo=ZoneInfo("UTC"))
    after_dst = datetime(2026, 11, 1, 7, 30, tzinfo=ZoneInfo("UTC"))
    assert to_facility_time(before_dst, "America/Chicago").utcoffset().total_seconds() == -5 * 3600
    assert to_facility_time(after_dst, "America/Chicago").utcoffset().total_seconds() == -6 * 3600
    assert add_minutes(before_dst, 15).tzinfo == ZoneInfo("UTC")


def test_invalid_facility_timezone_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid facility timezone"):
        facility_zone("Not/A_Timezone")


def test_interval_overlap_boundaries() -> None:
    tz = ZoneInfo("America/Chicago")
    start = datetime(2026, 10, 10, 7, 0, tzinfo=tz)
    boundary = datetime(2026, 10, 10, 8, 0, tzinfo=tz)
    end = datetime(2026, 10, 10, 9, 0, tzinfo=tz)
    assert intervals_overlap(start, end, boundary, end)
    assert not intervals_overlap(start, boundary, boundary, end)
    assert overlap_duration(start, end, boundary, end).total_seconds() == 3600


def test_reversed_intervals_are_rejected() -> None:
    tz = ZoneInfo("America/Chicago")
    start = datetime(2026, 10, 10, 9, 0, tzinfo=tz)
    end = datetime(2026, 10, 10, 8, 0, tzinfo=tz)
    with pytest.raises(ValueError, match="ends before"):
        intervals_overlap(start, end, start, end)
