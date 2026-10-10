"""Timezone-aware, policy-independent time and interval utilities."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def require_aware(value: datetime, name: str = "datetime") -> datetime:
    """Reject naive datetimes before arithmetic or comparison."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone offset")
    return value


def facility_zone(timezone: str) -> ZoneInfo:
    """Return a configured facility timezone or raise a clear error."""

    if not timezone:
        raise ValueError("facility timezone must be non-empty")
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"invalid facility timezone: {timezone}") from exc


def to_facility_time(value: datetime, timezone: str) -> datetime:
    """Convert an aware instant to facility-local time, preserving its offset."""

    return require_aware(value).astimezone(facility_zone(timezone))


def add_minutes(value: datetime, minutes: int | float) -> datetime:
    """Add minutes to an aware datetime without selecting a policy meaning."""

    return require_aware(value) + timedelta(minutes=minutes)


def intervals_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    """Return whether two valid half-open intervals overlap."""

    _validate_interval(first_start, first_end, "first")
    _validate_interval(second_start, second_end, "second")
    return max(first_start, second_start) < min(first_end, second_end)


def overlap_duration(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> timedelta:
    """Return the positive overlap duration for two half-open intervals."""

    _validate_interval(first_start, first_end, "first")
    _validate_interval(second_start, second_end, "second")
    start = max(first_start, second_start)
    end = min(first_end, second_end)
    return max(timedelta(0), end - start)


def _validate_interval(start: datetime, end: datetime, name: str) -> None:
    require_aware(start, f"{name}_start")
    require_aware(end, f"{name}_end")
    if end < start:
        raise ValueError(f"{name} interval ends before it starts")
