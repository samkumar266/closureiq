"""SSE streaming for the agent chat, shared by both API apps.

Moved out of api/app/main.py so the main app (api/main.py) can stream chat
without importing api/app/main.py, which opens the legacy SQLite store.
`store` only needs an append(kind, detail) method; `base` needs evaluation_id
and rationale; `facility` needs timezone.
"""

from __future__ import annotations

import json
from typing import Any

from ai.chat import stream_agent_events
from ai.validator import validate


def _append_stream_audit(
    store: Any, kind: str, detail: dict[str, Any]
) -> bool:
    """Record stream audit state without raising after SSE output begins."""
    try:
        store.append(kind, detail)
    except Exception:
        return False
    return True


async def _stream_chat(
    first_event: Any,
    events: Any,
    *,
    agent: Any,
    base: Any,
    facility: Any,
    store: Any,
    prompt: str,
):
    answer_parts: list[str] = []
    tool_results: list[dict[str, Any]] = []
    seen_tools: set[str] = set()
    whatif_id: str | None = None
    audit_failed = False

    async def consume(event: Any):
        nonlocal audit_failed, whatif_id
        tool = _tool_event(event)
        if tool is not None:
            tool_key = json.dumps(tool, sort_keys=True, default=str)
            if tool_key not in seen_tools:
                seen_tools.add(tool_key)
                if not _append_stream_audit(store, "agent_tool", tool):
                    audit_failed = True
                yield _sse("tool", tool)
        result = _tool_result(event)
        if result is not None:
            tool_results.append(result)
            if result.get("hypothetical") is True:
                possible = result.get("evaluation_id")
                if isinstance(possible, str):
                    whatif_id = possible
        text = _event_text(event)
        if text:
            answer_parts.append(text)
            yield _sse("token", {"text": text})

    try:
        async for item in consume(first_event):
            yield item
        async for event in events:
            async for item in consume(event):
                yield item
    except Exception:
        fallback = base.rationale
        yield _sse("replaced", {"text": fallback})
        _append_stream_audit(
            store,
            "agent_answer",
            {
                "evaluation_id": base.evaluation_id,
                "text": fallback,
                "validated": False,
                "whatif_id": whatif_id,
                "audit_error": True,
            },
        )
        yield _sse(
            "done",
            {"evaluation_id": base.evaluation_id, "validated": False, "whatif_id": whatif_id},
        )
        return

    answer = "".join(answer_parts)
    validation = validate(answer, tool_results, timezone=facility.timezone)
    validated = validation.valid
    if not validated:
        answer_parts.clear()
        tool_results.clear()
        try:
            retry_prompt = (
                f"{prompt}\n\nYour previous answer could not be verified: "
                f"{validation.reason or 'a factual claim was unsupported'}. "
                "Answer again using only current tool results and omit unsupported figures."
            )
            retry_events = stream_agent_events(agent, retry_prompt)
            async for event in retry_events:
                async for item in consume(event):
                    yield item
        except Exception:
            pass
        retry_answer = "".join(answer_parts)
        validated = validate(
            retry_answer, tool_results, timezone=facility.timezone
        ).valid
        if validated:
            answer = retry_answer
    if not validated:
        yield _sse(
            "replaced",
            {
                "text": (
                    f"{base.rationale} Figures could not be verified; "
                    "showing the engine rationale."
                )
            },
        )
    final_text = answer if validated else base.rationale
    if not _append_stream_audit(
        store,
        "agent_answer",
        {
            "evaluation_id": base.evaluation_id,
            "text": final_text,
            "validated": validated,
            "whatif_id": whatif_id,
            "audit_error": audit_failed,
        },
    ):
        audit_failed = True
    yield _sse(
        "done",
        {
            "evaluation_id": base.evaluation_id,
            "validated": validated and not audit_failed,
            "whatif_id": whatif_id,
        },
    )


def _event_text(event: Any) -> str:
    if not isinstance(event, dict):
        return ""
    data = event.get("data")
    if isinstance(data, str):
        return data
    if isinstance(data, dict) and isinstance(data.get("text"), str):
        return data["text"]
    return ""


def _tool_event(event: Any) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    current = event.get("current_tool_use")
    if not isinstance(current, dict):
        return None
    name = current.get("name")
    if not isinstance(name, str):
        return None
    args = current.get("input", current.get("args", {}))
    return {"name": name, "args": args if isinstance(args, dict) else {}}


def _tool_result(event: Any) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    result = event.get("tool_result", event.get("toolResult"))
    if not isinstance(result, dict):
        return None
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            try:
                decoded = json.loads(item["text"])
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return decoded
    return result


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, sort_keys=True)}\n\n"
