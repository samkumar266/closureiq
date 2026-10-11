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
    pending: list[str] = []
    tool_results: list[dict[str, Any]] = []
    seen_tools: set[str] = set()
    whatif_id: str | None = None
    audit_failed = False

    async def consume(event: Any):
        nonlocal audit_failed, whatif_id
        for tool in _tool_events(event):
            tool_key = json.dumps(tool, sort_keys=True, default=str)
            if tool_key not in seen_tools:
                seen_tools.add(tool_key)
                if not _append_stream_audit(store, "agent_tool", tool):
                    audit_failed = True
                yield _sse("tool", tool)
        for result in _tool_results(event):
            tool_results.append(result)
            if result.get("hypothetical") is True:
                possible = result.get("whatif_id") or result.get("evaluation_id")
                if isinstance(possible, str):
                    whatif_id = possible
        # Hold each model message's text until the message is complete: text written in a
        # turn that calls a tool is a preamble ("I'll check...") and is dropped; only the
        # final message is validated, then sent and recorded.
        text = _event_text(event)
        if text:
            pending.append(text)
        message = event.get("message") if isinstance(event, dict) else None
        if isinstance(message, dict) and message.get("role") == "assistant":
            calls_tool = any(isinstance(item, dict) and "toolUse" in item for item in message.get("content") or [])
            if calls_tool:
                pending.clear()
            else:
                for item in flush():
                    yield item

    def flush():
        """Move the finished message's text into the answer. Nothing is sent to the
        client until the answer has passed validation (see below)."""
        if pending:
            answer_parts.append("".join(pending))
            pending.clear()
        return ()

    try:
        async for item in consume(first_event):
            yield item
        async for event in events:
            async for item in consume(event):
                yield item
        for item in flush():  # streams without message events (test doubles) end here
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
        # Retry once. The retry is checked against this turn's tool results, which
        # the model already has in its conversation.
        answer_parts.clear()
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
            for item in flush():
                yield item
        except Exception:
            pass
        retry_answer = "".join(answer_parts)
        validated = validate(
            retry_answer, tool_results, timezone=facility.timezone
        ).valid
        if validated:
            answer = retry_answer
    if validated and answer:
        yield _sse("token", {"text": answer})
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
    if not isinstance(args, dict):
        return None  # still streaming as a partial JSON string; the finished message reports it
    return {"name": name, "args": args}


def _tool_events(event: Any) -> list[dict[str, Any]]:
    """Tool calls with complete arguments.

    Strands streams current_tool_use.input as a partial JSON string, so a call is
    only reported once its input is a dict: either a current_tool_use with a dict
    input, or the toolUse items of the finished assistant message.
    """
    found = []
    single = _tool_event(event)
    if single is not None:
        found.append(single)
    message = event.get("message") if isinstance(event, dict) else None
    if isinstance(message, dict) and message.get("role") == "assistant":
        for item in message.get("content") or []:
            use = item.get("toolUse") if isinstance(item, dict) else None
            if isinstance(use, dict) and isinstance(use.get("name"), str):
                args = use.get("input")
                found.append({"name": use["name"], "args": args if isinstance(args, dict) else {}})
    return found


def _tool_results(event: Any) -> list[dict[str, Any]]:
    """Decoded tool results: a top-level tool_result, or the toolResult items of the
    user-role message Strands appends after running tools."""
    found = []
    single = _tool_result(event)
    if single is not None:
        found.append(single)
    message = event.get("message") if isinstance(event, dict) else None
    if isinstance(message, dict) and message.get("role") == "user":
        for item in message.get("content") or []:
            result = item.get("toolResult") if isinstance(item, dict) else None
            if isinstance(result, dict):
                decoded = _tool_result({"tool_result": result})
                if decoded is not None:
                    found.append(decoded)
    return found


def _tool_result(event: Any) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None
    result = event.get("tool_result", event.get("toolResult"))
    if not isinstance(result, dict):
        return None
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("json"), dict):
                return item["json"]
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            try:
                decoded = json.loads(item["text"])
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return decoded
            if isinstance(decoded, list):  # e.g. get_thresholds; let the validator see the rows
                return {"items": decoded}
    return result


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, sort_keys=True)}\n\n"
