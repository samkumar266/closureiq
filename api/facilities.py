"""Synthetic facility profiles. Replace demo locations to match the team seed data.

The first facility uses the exact coordinate supplied for Badri's NWS integration.
The second comes from the architecture example. The third is an additional demo slot.
These are not real customer facilities.
"""
from __future__ import annotations

FACILITIES: dict[str, dict] = {
    "central-fl-service-center": {
        "facility_id": "central-fl-service-center",
        "name": "Central Florida Service Center",
        "location": {"lat": 29.18, "lon": -82.21, "timezone": "America/New_York"},
        "hours": {"open": "07:30", "close": "16:00"},
        "arrival_window": {"start": "07:00", "end": "08:30"},
        "departure_window": {"start": "15:00", "end": "16:30"},
        "commute_buffer_min": 45,
        "notification_lead_min": 90,
        "earliest_departure": "06:15",
        "assembly_point": "North parking lot",
        "manager_id": "e_001", "backup_manager_id": "e_002", "on_call_id": "e_003",
        "gauge": None,
        "policy_version": "policy-2026-10-10.1",
    }
    # "kc-service-center": {
    #     "facility_id": "kc-service-center",
    #     "name": "Kansas City Service Center",
    #     "location": {"lat": 39.0997, "lon": -94.5786, "timezone": "America/Chicago"},
    #     "hours": {"open": "07:30", "close": "16:00"},
    #     "arrival_window": {"start": "07:00", "end": "08:30"},
    #     "departure_window": {"start": "15:00", "end": "16:30"},
    #     "commute_buffer_min": 45,
    #     "notification_lead_min": 90,
    #     "earliest_departure": "06:15",
    #     "assembly_point": "North parking lot",
    #     "manager_id": "e_001", "backup_manager_id": "e_002", "on_call_id": "e_003",
    #     "gauge": {"usgs_site": "06893000", "nwps_id": "KCDM7"},
    #     "policy_version": "policy-2026-10-10.1",
    # },
    # "jacksonville-service-center": {
    #     "facility_id": "jacksonville-service-center",
    #     "name": "Jacksonville Service Center",
    #     "location": {"lat": 30.3322, "lon": -81.6557, "timezone": "America/New_York"},
    #     "hours": {"open": "07:30", "close": "16:00"},
    #     "arrival_window": {"start": "07:00", "end": "08:30"},
    #     "departure_window": {"start": "15:00", "end": "16:30"},
    #     "commute_buffer_min": 45,
    #     "notification_lead_min": 90,
    #     "earliest_departure": "06:15",
    #     "assembly_point": "North parking lot",
    #     "manager_id": "e_001", "backup_manager_id": "e_002", "on_call_id": "e_003",
    #     "gauge": None,
    #     "policy_version": "policy-2026-10-10.1",
    # },
}


def get_facility(facility_id: str) -> dict | None:
    """Return a copy to prevent route handlers from mutating seed state."""
    facility = FACILITIES.get(facility_id)
    if facility is None:
        return None
    import copy
    return copy.deepcopy(facility)


def public_facility(facility: dict) -> dict:
    """Return the contract's facility profile (includes the facility_id)."""
    return {k: v for k, v in facility.items()}
