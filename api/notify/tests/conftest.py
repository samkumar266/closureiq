"""Shared fixtures: real files from mocks/ and mocks/seed/."""
import json
import random
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MOCKS = ROOT / "mocks"


def load(path):
    return json.loads((MOCKS / path).read_text())


@pytest.fixture
def kc_roster():
    return load("seed/roster_kc-service-center.json")["employees"]


@pytest.fixture
def kc_profile():
    return next(f for f in load("seed/facility_profiles.json")["facilities"]
                if f["facility_id"] == "kc-service-center")


@pytest.fixture
def closure_eval():
    return load("closure.json")


@pytest.fixture
def delayed_eval():
    return load("delayed_arrival.json")


@pytest.fixture
def rng():
    return random.Random(42)
