"""Model selection for the ClosureIQ Strands agent."""

from __future__ import annotations

import os
from typing import Any


def get_model() -> Any:
    """Create the configured Strands model without exposing provider secrets."""
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if not provider:
        raise ValueError(
            "LLM_PROVIDER is required; choose bedrock, anthropic, or openai_compat"
        )

    if provider == "bedrock":
        from strands.models.bedrock import BedrockModel

        model_id = os.getenv("BEDROCK_MODEL_ID", "").strip()
        if model_id:
            return BedrockModel(model_id=model_id)
        return BedrockModel()

    if provider == "anthropic":
        from strands.models.anthropic import AnthropicModel

        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        model_id = os.getenv("MODEL_ID", "").strip()
        _require_environment(
            "anthropic", {"ANTHROPIC_API_KEY": api_key, "MODEL_ID": model_id}
        )
        return AnthropicModel(
            client_args={"api_key": api_key},
            model_id=model_id,
        )

    if provider == "openai_compat":
        from strands.models.openai import OpenAIModel

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        model_id = os.getenv("MODEL_ID", "").strip()
        _require_environment(
            "openai_compat",
            {
                "OPENAI_API_KEY": api_key,
                "OPENAI_BASE_URL": base_url,
                "MODEL_ID": model_id,
            },
        )
        return OpenAIModel(
            client_args={"api_key": api_key, "base_url": base_url},
            model_id=model_id,
        )

    raise ValueError(
        f"unsupported LLM_PROVIDER {provider!r}; choose bedrock, anthropic, or openai_compat"
    )


def _require_environment(provider: str, values: dict[str, str]) -> None:
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"{provider} provider requires environment variable(s): {names}")
