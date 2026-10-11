"""Focused tests for guarded chat behavior."""

import ast
import json

from fastapi.testclient import TestClient

from ai.chat import build_chat_agent, stream_agent_events, validate_answer
from api.app.main import create_app
from api.engine import FacilityPolicy, InputEvidence, Recommendation
from api.legacy_store import SQLiteStore


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


def _seed(store: SQLiteStore) -> Recommendation:
    with open("mocks/normal.json", encoding="utf-8") as handle:
        payload = json.load(handle)
    recommendation = Recommendation.model_validate(payload)
    evidence = [InputEvidence.model_validate(item) for item in payload["inputs"]]
    store.save_evaluation(recommendation, evidence, _facility())
    return recommendation


def test_answer_validation_requires_matching_units_and_supports_local_dates() -> None:
    facts = [
        {
            "rain": {"value": 10.4, "unit": "in"},
            "when": "2026-01-15T07:30:00-06:00",
        }
    ]
    assert validate_answer("Rain is 10 in on January 15, 2026.", facts, timezone="America/Chicago")
    assert not validate_answer("Rain is 10 mph.", facts, timezone="America/Chicago")
    assert not validate_answer("Rain is 10%.", facts, timezone="America/Chicago")
    range_facts = [{"range": {"min": 1, "max": 2, "unit": "in"}}]
    assert validate_answer("Rain is between 1 and 2 in.", range_facts, timezone="America/Chicago")
    assert not validate_answer("Rain is between 1 and 3 in.", range_facts, timezone="America/Chicago")


def test_answer_validation_normalizes_aware_times_and_rounding() -> None:
    facts = [{"amount": {"value": 10.4, "unit": "in"}, "at": "2026-07-01T12:30:00Z"}]
    assert validate_answer("It is 10 in at 7:30 AM.", facts, timezone="America/Chicago")
    assert validate_answer("It is 10 in at 07:30.", facts, timezone="America/Chicago")
    assert not validate_answer("It is 11 in at 7:30 AM.", facts, timezone="America/Chicago")
    assert not validate_answer("It is 10 in at 25:30.", facts, timezone="America/Chicago")


def test_answer_validation_supports_plain_local_times_and_rejects_invalid_times() -> None:
    facts = [{"start": "7:30 AM", "end": "10 AM", "review": "22:15"}]
    assert validate_answer("The start is 07:30.", facts, timezone="America/Chicago")
    assert validate_answer("The end is 10:00 AM.", facts, timezone="America/Chicago")
    assert validate_answer("The review is 10:15 PM.", facts, timezone="America/Chicago")
    assert not validate_answer("The start is 7:60 AM.", facts, timezone="America/Chicago")
    assert not validate_answer("The end is 25 AM.", facts, timezone="America/Chicago")
    assert not validate_answer("The review is 22:60.", facts, timezone="America/Chicago")


def test_chat_route_emits_sse_and_audits_question_tool_and_answer(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "closureiq.db")
    base = _seed(store)

    class FakeAgent:
        def stream_async(self, prompt):
            assert prompt == "Why?"

            async def events():
                yield {
                    "current_tool_use": {
                        "name": "get_evaluation",
                        "input": {"evaluation_id": base.evaluation_id},
                    }
                }
                yield {"tool_result": {"evaluation_id": base.evaluation_id}}
                yield {"data": "The posture is normal_operations."}

            return events()

    monkeypatch.setattr("api.app.main.build_chat_agent", lambda *args: FakeAgent())
    client = TestClient(create_app(store))
    response = client.post(
        "/api/agent/chat",
        json={
            "facility_id": base.facility_id,
            "evaluation_id": base.evaluation_id,
            "message": "Why?",
        },
    )

    assert response.status_code == 200
    assert "event: tool\n" in response.text
    assert "event: token\n" in response.text
    assert "event: done\n" in response.text
    assert '"validated": true' in response.text
    assert all(entry["kind"] in {"agent_question", "agent_tool", "agent_answer"} for entry in store.audit_entries())


def test_chat_provider_failure_before_first_event_returns_503(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "closureiq.db")
    base = _seed(store)

    class FailingAgent:
        def stream_async(self, prompt):
            async def events():
                raise RuntimeError("provider down")
                yield {}

            return events()

    monkeypatch.setattr("api.app.main.build_chat_agent", lambda *args: FailingAgent())
    response = TestClient(create_app(store)).post(
        "/api/agent/chat",
        json={
            "facility_id": base.facility_id,
            "evaluation_id": base.evaluation_id,
            "message": "Why?",
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "agent_unavailable"


def test_chat_provider_failure_after_first_event_is_replaced(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "closureiq.db")
    base = _seed(store)

    class PartialAgent:
        def stream_async(self, prompt):
            async def events():
                yield {"data": "partial"}
                raise RuntimeError("provider lost")

            return events()

    monkeypatch.setattr("api.app.main.build_chat_agent", lambda *args: PartialAgent())
    response = TestClient(create_app(store)).post(
        "/api/agent/chat",
        json={
            "facility_id": base.facility_id,
            "evaluation_id": base.evaluation_id,
            "message": "Why?",
        },
    )
    assert response.status_code == 200
    assert "event: replaced\n" in response.text
    assert '"validated": false' in response.text


def test_chat_retries_once_with_validation_feedback(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "closureiq.db")
    base = _seed(store)
    prompts = []

    class RetryAgent:
        def stream_async(self, prompt):
            prompts.append(prompt)

            async def events():
                yield {"data": "The posture is 99 in." if len(prompts) == 1 else "The posture is normal_operations."}

            return events()

    monkeypatch.setattr("api.app.main.build_chat_agent", lambda *args: RetryAgent())
    response = TestClient(create_app(store)).post(
        "/api/agent/chat",
        json={"facility_id": base.facility_id, "evaluation_id": base.evaluation_id, "message": "Why?"},
    )

    assert response.status_code == 200
    assert len(prompts) == 2
    assert "could not be verified" in prompts[1]
    assert '"validated": true' in response.text


def test_stream_audit_failure_does_not_escape_after_sse(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "closureiq.db")
    base = _seed(store)

    calls = 0

    def fail_after_question(kind, detail):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("disk full")

    monkeypatch.setattr(store, "append", fail_after_question)

    class FakeAgent:
        def stream_async(self, prompt):
            async def events():
                yield {"data": "The posture is normal_operations."}

            return events()

    monkeypatch.setattr("api.app.main.build_chat_agent", lambda *args: FakeAgent())
    response = TestClient(create_app(store)).post(
        "/api/agent/chat",
        json={"facility_id": base.facility_id, "evaluation_id": base.evaluation_id, "message": "Why?"},
    )

    assert response.status_code == 200
    assert "event: done\n" in response.text
    assert '"validated": false' in response.text


def test_ai_modules_do_not_import_write_or_approval_boundaries() -> None:
    for path in ("ai/agent.py", "ai/chat.py", "ai/model.py", "ai/smoke.py"):
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        imports = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]
        imports += [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ]
        assert not any(name.startswith("api.notify") or "approval" in name for name in imports)


def test_stream_retries_only_before_first_event() -> None:
    attempts = 0

    class RetryAgent:
        def stream_async(self, prompt):
            nonlocal attempts
            attempts += 1

            async def events():
                if attempts == 1:
                    raise RuntimeError("transient")
                yield {"data": "ok"}

            return events()

    async def collect():
        return [event async for event in stream_agent_events(RetryAgent(), "x")]

    import asyncio

    assert asyncio.run(collect()) == [{"data": "ok"}]
    assert attempts == 2


def test_chat_registers_all_five_read_only_tools(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "closureiq.db")
    base = _seed(store)
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("ai.chat.Agent", FakeAgent)
    monkeypatch.setattr("ai.chat.get_model", lambda: "fake")
    build_chat_agent(base, store.get_evidence(base.evaluation_id), _facility(), store)

    assert [tool.__name__ for tool in captured["tools"]] == [
        "get_evaluation",
        "get_evidence",
        "list_affected_employees",
        "get_thresholds",
        "run_what_if",
    ]


def test_get_evidence_rejects_snapshot_from_another_evaluation(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "closureiq.db")
    base = _seed(store)
    with open("mocks/delayed_arrival.json", encoding="utf-8") as handle:
        payload = json.load(handle)
    other = Recommendation.model_validate(payload).model_copy(
        update={"evaluation_id": "eval_0099", "facility_id": base.facility_id}
    )
    other_evidence = [InputEvidence.model_validate(item) for item in payload["inputs"]]
    store.save_evaluation(other, other_evidence, _facility())
    foreign_snapshot = other_evidence[0].snapshot_id
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("ai.chat.Agent", FakeAgent)
    monkeypatch.setattr("ai.chat.get_model", lambda: "fake")
    build_chat_agent(base, store.get_evidence(base.evaluation_id), _facility(), store)
    get_evidence = next(
        item for item in captured["tools"] if item.__name__ == "get_evidence"
    )

    try:
        get_evidence(foreign_snapshot)
    except ValueError as exc:
        assert str(exc) == "evidence snapshot was not found"
    else:
        raise AssertionError("foreign evidence snapshot was accessible")


def test_validator_contract_returns_fail_closed_result() -> None:
    from ai.validator import ValidationResult, validate

    result = validate("Threshold T6 applies.", [{"thresholds_crossed": [{"id": "T6"}]}])
    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert validate("Threshold T7 applies.", [{"thresholds_crossed": [{"id": "T6"}]}]).valid is False
