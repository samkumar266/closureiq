"""Integration tests for the documented what-if API boundary."""

import json

from fastapi.testclient import TestClient

from api.app.main import create_app
from api.engine import FacilityPolicy, InputEvidence, Recommendation
from api.legacy_store import SQLiteStore 
from api.legacy_store import ensure_real_recommendation


def _facility() -> FacilityPolicy:
    return FacilityPolicy(
        facility_id="omaha-service-center",
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


def _seed(store: SQLiteStore) -> tuple[Recommendation, list[InputEvidence]]:
    payload = json.loads(open("mocks/normal.json", encoding="utf-8").read())
    base = Recommendation.model_validate(payload)
    evidence = [InputEvidence.model_validate(item) for item in payload["inputs"]]
    store.save_evaluation(base, evidence, _facility())
    return base, evidence


def test_what_if_returns_documented_wrapper_and_only_audit_row(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "closureiq.db")
    base, evidence = _seed(store)
    original_base = base.model_dump(mode="json")
    original_evidence = [item.model_dump(mode="json") for item in evidence]
    client = TestClient(create_app(store))

    response = client.post(
        f"/api/evaluations/{base.evaluation_id}/what-if",
        json={"overrides": {"in_2": 60}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["hypothetical"] is True
    assert body["whatif_id"] == "wif_0001"
    assert body["based_on"] == base.evaluation_id
    assert body["result"]["hypothetical"] is True
    assert store.evaluation_count() == 1
    assert store.get_evaluation(base.evaluation_id)[0].model_dump(mode="json") == original_base
    assert [
        item.model_dump(mode="json") for item in store.get_evidence(base.evaluation_id)
    ] == original_evidence
    assert store.audit_entries() == [
        {
            "audit_id": 1,
            "kind": "whatif",
            "detail": {
                "based_on": base.evaluation_id,
                "changed_fields": body["changed_fields"],
                "overrides": {"in_2": 60},
                "whatif_id": "wif_0001",
            },
        }
    ]


def test_missing_and_invalid_what_if_requests_return_contract_errors(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "closureiq.db")
    client = TestClient(create_app(store))

    missing = client.post(
        "/api/evaluations/eval_4040/what-if",
        json={"overrides": {"in_2": 60}},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    base, _ = _seed(store)
    invalid = client.post(
        f"/api/evaluations/{base.evaluation_id}/what-if",
        json={"overrides": {"alert_severity": "Severe"}},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "bad_request"
    assert len(store.audit_entries()) == 0

    invalid_type = client.post(
        f"/api/evaluations/{base.evaluation_id}/what-if",
        json={"overrides": {"in_1": 60}},
    )
    assert invalid_type.status_code == 422
    assert len(store.audit_entries()) == 0


def test_hypothetical_recommendations_are_rejected_by_normal_boundaries() -> None:
    payload = json.loads(open("mocks/normal.json", encoding="utf-8").read())
    hypothetical = Recommendation.model_validate(
        {**payload, "hypothetical": True}
    )
    try:
        ensure_real_recommendation(hypothetical)
    except ValueError as exc:
        assert "hypothetical" in str(exc)
    else:
        raise AssertionError("hypothetical recommendation was accepted")


def test_store_allocates_whatif_ids(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "closureiq.db")
    assert store.next_whatif_id() == "wif_0001"
