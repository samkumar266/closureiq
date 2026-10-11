"""Agent chat mounted in the main app (api/main.py)."""
import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app

CLOSURE = json.loads(open("mocks/closure.json").read())


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ("LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_BASE_URL", "MODEL_ID", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    app = create_app(tmp_path / "t.db", enable_scheduler=False, poll_on_startup=False)
    with TestClient(app) as c:
        store = app.state.store
        ev = store.append_evaluation(
            facility_id="kc-service-center", evaluated_at_wall=CLOSURE["evaluated_at"],
            evaluated_at_sim=CLOSURE["evaluated_at"], data_mode="live", evidence_ids=[],
            engine_version="test", policy_version=CLOSURE["policy_version"], result=CLOSURE,
            posture="closure", confidence="high", supersedes=None)
        c.evaluation_id = ev["id"]
        yield c


def ask(client, facility="kc-service-center"):
    return client.post("/api/agent/chat", json={"facility_id": facility, "evaluation_id": client.evaluation_id,
                                                 "message": "What if the warning ended?"})


def test_no_key_gives_clear_agent_unavailable(client):
    r = ask(client)
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "agent_unavailable"
    assert err["message"].startswith("Agent unavailable") and "LLM_PROVIDER" in err["message"]


def test_wrong_facility_is_404(client):
    assert ask(client, "stl-service-center").status_code == 404


def test_streams_tool_token_done_with_fake_agent(client, monkeypatch):
    class FakeAgent:
        async def stream_async(self, prompt):
            yield {"current_tool_use": {"name": "get_evaluation", "input": {"evaluation_id": client.evaluation_id}}}
            yield {"data": "The engine recommends closure."}
    monkeypatch.setattr("ai.chat.build_backend_chat_agent", lambda *a: FakeAgent())
    r = ask(client)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [block.split("\n")[0].removeprefix("event: ") for block in r.text.strip().split("\n\n")]
    assert events[0] == "tool" and "token" in events and events[-1] == "done"


def test_strands_message_events_give_tool_args_results_and_whatif(client, monkeypatch):
    # Real Strands shape: partial string input while streaming, then finished messages.
    result = {"hypothetical": True, "whatif_id": "wif_0009", "evaluation_id": "wif_0009", "posture": "closure"}

    class FakeAgent:
        async def stream_async(self, prompt):
            yield {"current_tool_use": {"name": "run_what_if", "input": ""}}
            yield {"message": {"role": "assistant", "content": [{"toolUse": {
                "toolUseId": "t1", "name": "run_what_if",
                "input": {"evaluation_id": client.evaluation_id, "overrides": {"in_2": {"windGust": 65}}}}}]}}
            yield {"message": {"role": "user", "content": [{"toolResult": {
                "toolUseId": "t1", "status": "success", "content": [{"text": json.dumps(result)}]}}]}}
            yield {"data": "Hypothetically the posture would be closure."}
    monkeypatch.setattr("ai.chat.build_backend_chat_agent", lambda *a: FakeAgent())
    r = ask(client)
    blocks = [b.split("\n") for b in r.text.strip().split("\n\n")]
    tools = [json.loads(b[1][len("data: "):]) for b in blocks if b[0] == "event: tool"]
    assert tools == [{"name": "run_what_if", "args": {"evaluation_id": client.evaluation_id,
                                                      "overrides": {"in_2": {"windGust": 65}}}}]
    done = json.loads(blocks[-1][1][len("data: "):])
    assert done["whatif_id"] == "wif_0009" and done["validated"] is True


def test_tool_results_are_compacted_for_the_model():
    from ai.chat import MAX_RESULT_CHARS, _bounded, compact_for_model
    small = compact_for_model({"periods": list(range(100)), "text": "x" * 5000})
    assert small["periods"][:12] == list(range(12)) and small["periods"][12] == {"omitted_items": 88}
    assert small["text"].endswith("[truncated]") and len(small["text"]) < 700
    huge = {f"field_{i}": [{"v": "y" * 500}] * 12 for i in range(60)}  # ~360 KB, like a raw NWS grid
    assert len(json.dumps(_bounded(huge))) <= MAX_RESULT_CHARS


def test_list_tool_result_is_decoded_for_the_validator():
    from api.app.agent_stream import _tool_results
    rows = [{"id": "T4", "cutoff": 58.0, "unit": "mph"}]
    event = {"message": {"role": "user", "content": [{"toolResult": {
        "toolUseId": "t2", "status": "success", "content": [{"text": json.dumps(rows)}]}}]}}
    assert _tool_results(event) == [{"items": rows}]


def test_preamble_before_a_tool_call_is_dropped(client, monkeypatch):
    class FakeAgent:
        async def stream_async(self, prompt):
            yield {"data": "I'll check the evaluation."}
            yield {"message": {"role": "assistant", "content": [
                {"text": "I'll check the evaluation."},
                {"toolUse": {"toolUseId": "t1", "name": "get_evaluation", "input": {"evaluation_id": client.evaluation_id}}}]}}
            yield {"message": {"role": "user", "content": [{"toolResult": {
                "toolUseId": "t1", "status": "success", "content": [{"text": json.dumps({"posture": "closure"})}]}}]}}
            yield {"data": "The engine recommends closure."}
            yield {"message": {"role": "assistant", "content": [{"text": "The engine recommends closure."}]}}
    monkeypatch.setattr("ai.chat.build_backend_chat_agent", lambda *a: FakeAgent())
    r = ask(client)
    tokens = [json.loads(b.split("\n")[1][len("data: "):])["text"]
              for b in r.text.strip().split("\n\n") if b.startswith("event: token")]
    assert tokens == ["The engine recommends closure."]
