"""Facility profiles for the Watchlist.

The three synthetic sites come from mocks/seed/ (read once at import); to change
one, edit mocks/seed/facility_profiles.json and its roster file. Aiken County SC
is an extra live-alert test site; Kingman AZ is the demo facility and San Diego CA its
backup. None of these are real customer facilities.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

SEED_PROFILES = Path(__file__).resolve().parents[1] / "mocks" / "seed" / "facility_profiles.json"

# Extra site for live alert testing (no seed roster; notify uses the KC roster template).
EXTRA_FACILITIES: dict[str, dict] = {
    "aiken-sc-service-center": {
        "facility_id": "aiken-sc-service-center",
        "name": "Aiken County Service Center",
        "location": {"lat": 33.875, "lon": -81.575, "timezone": "America/New_York"},
        "hours": {"open": "07:30", "close": "16:00"},
        "arrival_window": {"start": "07:00", "end": "08:30"},
        "departure_window": {"start": "15:00", "end": "16:30"},
        "commute_buffer_min": 45,
        "notification_lead_min": 90,
        "earliest_departure": "06:15",
        "assembly_point": "South access gate",
        "manager_id": "e_101", "backup_manager_id": "e_102", "on_call_id": "e_103",
        "gauge": None,
        "policy_version": "policy-2026-10-10.1",
    },
    # Demo facility: under a live NWS High Wind Warning on 2026-10-11 (gusts forecast over T4/T5).
    # The frontend opens on the facility named in frontend/src/config.ts.
    "kingman-az-service-center": {
        "facility_id": "kingman-az-service-center",
        "name": "Kingman Service Center",
        "location": {"lat": 35.19, "lon": -114.053, "timezone": "America/Phoenix"},
        "hours": {"open": "07:30", "close": "16:00"},
        "arrival_window": {"start": "07:00", "end": "08:30"},
        "departure_window": {"start": "15:00", "end": "16:30"},
        "commute_buffer_min": 45,
        "notification_lead_min": 90,
        "earliest_departure": "06:15",
        "assembly_point": "North parking lot",
        "manager_id": "e_001", "backup_manager_id": "e_002", "on_call_id": "e_003",
        "gauge": None,
        # Measured wind (supplementary signal) from the nearest airport weather station: Kingman Airport.
        "observation_station": "KIGM",
        "policy_version": "policy-2026-10-10.1",
    },
    # Backup demo facility: under a live NWS Coastal Flood Warning on 2026-10-11.
    # Kept polling so it has stored evidence if the demo swaps to it in frontend/src/config.ts.
    "san-diego-ca-service-center": {
        "facility_id": "san-diego-ca-service-center",
        "name": "San Diego Service Center",
        "location": {"lat": 32.7157, "lon": -117.1611, "timezone": "America/Los_Angeles"},
        "hours": {"open": "07:30", "close": "16:00"},
        "arrival_window": {"start": "07:00", "end": "08:30"},
        "departure_window": {"start": "15:00", "end": "16:30"},
        "commute_buffer_min": 45,
        "notification_lead_min": 90,
        "earliest_departure": "06:15",
        "assembly_point": "North parking lot",
        "manager_id": "e_001", "backup_manager_id": "e_002", "on_call_id": "e_003",
        "gauge": None,
        # Measured wind (supplementary signal) from the nearest airport weather station: San Diego International.
        "observation_station": "KSAN",
        "policy_version": "policy-2026-10-10.1",
    },
}


def _load() -> dict[str, dict]:
    profiles = json.loads(SEED_PROFILES.read_text())["facilities"]
    facilities = {p["facility_id"]: p for p in profiles}
    facilities.update(EXTRA_FACILITIES)
    return facilities


FACILITIES: dict[str, dict] = _load()


def get_facility(facility_id: str) -> dict | None:
    """Return a copy to prevent route handlers from mutating seed state."""
    facility = FACILITIES.get(facility_id)
    if facility is None:
        return None
    return copy.deepcopy(facility)


def public_facility(facility: dict) -> dict:
    """Return the contract's facility profile (includes the facility_id)."""
    return {k: v for k, v in facility.items()}
