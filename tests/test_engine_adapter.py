from datetime import datetime

from api.app.engine_adapter import _typed_previous, evaluate_recommendation
from api.engine import Recommendation
from api.facilities import get_facility


def test_legacy_fallback_previous_is_explicitly_ignored() -> None:
    legacy = {
        "engine_version": "badri-fallback-0.1",
        "evaluation_id": "eval_0005",
        "inputs": [{"id": "in_1", "value": ["legacy", "shape"]}],
    }
    facility = get_facility("central-fl-service-center")
    assert facility is not None

    assert _typed_previous(legacy) is None
    result = evaluate_recommendation(
        None,
        facility,
        [],
        evaluated_at=datetime.fromisoformat("2026-10-10T22:55:00-05:00"),
        previous_result=legacy,
    )
    assert result["engine_version"] == "shared-policy-engine-1.0"


def test_canonical_previous_remains_available_for_hysteresis() -> None:
    facility = get_facility("central-fl-service-center")
    assert facility is not None
    current = evaluate_recommendation(
        None,
        facility,
        [],
        evaluated_at=datetime.fromisoformat("2026-10-10T22:55:00-05:00"),
    )
    canonical = Recommendation.model_validate(
        {key: current[key] for key in Recommendation.model_fields if key in current}
    )

    previous = _typed_previous(current)

    assert previous == canonical
    assert previous is not None
