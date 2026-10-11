"""Facility profiles for the Watchlist: the three synthetic sites in mocks/seed/.

Read once at import. These are not real customer facilities. To add or change a
site, edit mocks/seed/facility_profiles.json (and its roster file).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

SEED_PROFILES = Path(__file__).resolve().parents[1] / "mocks" / "seed" / "facility_profiles.json"


def _load() -> dict[str, dict]:
    profiles = json.loads(SEED_PROFILES.read_text())["facilities"]
    return {p["facility_id"]: p for p in profiles}


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
