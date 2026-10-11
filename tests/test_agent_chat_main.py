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
