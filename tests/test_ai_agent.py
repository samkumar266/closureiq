from __future__ import annotations

import pytest

from ai.agent import get_evaluation
from ai.model import get_model


def test_get_evaluation_loads_the_documented_mock() -> None:
    evaluation = get_evaluation("eval_0012")

    assert evaluation["posture"] == "delayed_arrival"
    assert evaluation["evaluation_id"] == "eval_0012"


def test_get_evaluation_rejects_missing_id() -> None:
    with pytest.raises(ValueError, match="was not found"):
        get_evaluation("eval_missing")


def test_get_evaluation_reports_malformed_mock(monkeypatch, tmp_path) -> None:
    import ai.agent as agent_module

    malformed = tmp_path / "delayed_arrival.json"
    malformed.write_text("{", encoding="utf-8")
    monkeypatch.setattr(agent_module, "_MOCK_PATH", malformed)

    with pytest.raises(RuntimeError, match="malformed"):
        get_evaluation("eval_0012")


@pytest.mark.parametrize(
    ("provider", "environment", "class_name", "expected"),
    [
        (
            "anthropic",
            {"ANTHROPIC_API_KEY": "test-anthropic-key", "MODEL_ID": "claude-test"},
            "AnthropicModel",
            {"client_args": {"api_key": "test-anthropic-key"}, "model_id": "claude-test"},
        ),
        (
            "openai_compat",
            {
                "OPENAI_API_KEY": "test-openai-key",
                "OPENAI_BASE_URL": "https://example.invalid/v1",
                "MODEL_ID": "akamai-test",
            },
            "OpenAIModel",
            {
                "client_args": {
                    "api_key": "test-openai-key",
                    "base_url": "https://example.invalid/v1",
                },
                "model_id": "akamai-test",
            },
        ),
    ],
)
def test_get_model_selects_provider_configuration(
    monkeypatch, provider, environment, class_name, expected
) -> None:
    import importlib

    module_name = {
        "AnthropicModel": "strands.models.anthropic",
        "OpenAIModel": "strands.models.openai",
    }[class_name]
    provider_module = importlib.import_module(module_name)
    calls = []

    class FakeModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(provider_module, class_name, FakeModel)
    monkeypatch.setenv("LLM_PROVIDER", provider)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    get_model()

    assert calls == [expected]


def test_get_model_uses_explicit_bedrock_model_id(monkeypatch) -> None:
    import strands.models.bedrock as bedrock_module

    calls = []

    class FakeModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(bedrock_module, "BedrockModel", FakeModel)
    monkeypatch.setenv("LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "bedrock-test")

    get_model()

    assert calls == [{"model_id": "bedrock-test"}]


@pytest.mark.parametrize(
    ("provider", "missing"),
    [
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openai_compat", "OPENAI_BASE_URL"),
    ],
)
def test_get_model_reports_missing_provider_configuration(
    monkeypatch, provider, missing
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.delenv(missing, raising=False)
    if provider == "anthropic":
        monkeypatch.setenv("MODEL_ID", "model")
    else:
        monkeypatch.setenv("OPENAI_API_KEY", "key")
        monkeypatch.setenv("MODEL_ID", "model")

    with pytest.raises(ValueError, match=missing):
        get_model()


def test_get_model_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "local")

    with pytest.raises(ValueError, match="unsupported LLM_PROVIDER"):
        get_model()


def test_build_agent_registers_exactly_one_tool(monkeypatch) -> None:
    import ai.agent as agent_module

    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(agent_module, "Agent", FakeAgent)
    monkeypatch.setattr(agent_module, "get_model", lambda: "fake-model")

    agent_module.build_agent()

    assert captured["model"] == "fake-model"
    assert captured["tools"] == [agent_module.get_evaluation]
    assert captured["system_prompt"] == agent_module.SYSTEM_PROMPT


def test_smoke_submits_required_prompt(monkeypatch, capsys) -> None:
    import ai.smoke as smoke_module

    prompts = []

    class FakeAgent:
        def __call__(self, prompt):
            prompts.append(prompt)
            return {"ok": True}

    monkeypatch.setattr(smoke_module, "build_agent", lambda: FakeAgent())

    smoke_module.main()

    assert prompts == ["Why is the posture what it is?"]
    assert capsys.readouterr().out == "{'ok': True}\n"
