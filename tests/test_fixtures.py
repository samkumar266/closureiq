import json
from pathlib import Path

from api.engine.models import Recommendation


ROOT = Path(__file__).parents[1]


def test_recommendation_fixtures_validate_and_round_trip() -> None:
    fixture_names = (
        "normal.json",
        "delayed_arrival.json",
        "early_dismissal.json",
        "unscheduled_leave.json",
        "closure.json",
        "degraded_low_confidence.json",
    )

    for fixture_name in fixture_names:
        fixture_path = ROOT / "mocks" / fixture_name
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        recommendation = Recommendation.model_validate(payload)

        assert recommendation.model_dump(mode="json") == payload, fixture_name
