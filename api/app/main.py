"""FastAPI entry point for the ClosureIQ API."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ai.chat import build_chat_agent, stream_agent_events
from ai.validator import validate
from ..engine import Recommendation, run_what_if
from ..store import SQLiteStore


class WhatIfRequest(BaseModel):
    """Documented what-if request body."""

    model_config = ConfigDict(extra="forbid")

    overrides: dict[str, Any] = Field(default_factory=dict)


class WhatIfResponse(BaseModel):
    """Documented what-if response wrapper."""

    hypothetical: bool
    whatif_id: str
    based_on: str
    result: Recommendation
    changed_fields: list[str]


class ChatRequest(BaseModel):
    """Documented agent chat request."""

    model_config = ConfigDict(extra="forbid")

    facility_id: str
    evaluation_id: str
    message: str = Field(min_length=1)


def create_app(store: SQLiteStore | None = None) -> FastAPI:
    """Create the API with an injectable SQLite store for isolated tests."""
    application = FastAPI(title="ClosureIQ API")
    api_store = store or SQLiteStore(os.getenv("DB_PATH", "data/closureiq.db"))

    @application.exception_handler(HTTPException)
    async def contract_http_error(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        del request
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "bad_request", "message": str(exc.detail), "detail": {}}},
        )

    @application.exception_handler(RequestValidationError)
    async def contract_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "bad_request",
                    "message": "request validation failed",
                    "detail": exc.errors(),
                }
            },
        )

    @application.post(
        "/api/evaluations/{evaluation_id}/what-if",
        response_model=WhatIfResponse,
    )
    def what_if(evaluation_id: str, request: WhatIfRequest) -> WhatIfResponse:
        stored = api_store.get_evaluation(evaluation_id)
        if stored is None:
            raise _error(404, "not_found", "evaluation was not found")
        base, facility = stored
        evidence = api_store.get_evidence(evaluation_id)
        whatif_id = api_store.next_whatif_id()
        try:
            result = run_what_if(
                base,
                evidence,
                request.overrides,
                facility=facility,
                now=base.evaluated_at,
                what_if_id=whatif_id,
            )
        except (TypeError, ValueError) as exc:
            raise _error(422, "bad_request", str(exc)) from exc
        api_store.append(
            "whatif",
            {
                "whatif_id": whatif_id,
                "based_on": evaluation_id,
                "overrides": request.overrides,
                "changed_fields": result.changed_fields,
            },
        )
        return WhatIfResponse(
            hypothetical=True,
            whatif_id=whatif_id,
            based_on=evaluation_id,
            result=result,
            changed_fields=result.changed_fields,
        )

    @application.post("/api/agent/chat")
    async def agent_chat(request: ChatRequest) -> StreamingResponse:
        stored = api_store.get_evaluation(request.evaluation_id)
        if stored is None or stored[0].facility_id != request.facility_id:
            raise _error(404, "not_found", "evaluation was not found")
        base, facility = stored
        evidence = api_store.get_evidence(request.evaluation_id)
        _append_audit(
            api_store,
            "agent_question",
            {
                "facility_id": request.facility_id,
                "evaluation_id": request.evaluation_id,
                "message": request.message,
            },
        )
        try:
            agent = build_chat_agent(base, evidence, facility, api_store)
            events = stream_agent_events(agent, request.message)
            first_event = await events.__anext__()
        except Exception as exc:
            raise _error(503, "agent_unavailable", "agent provider is unavailable") from exc

        return StreamingResponse(
            _stream_chat(
                first_event,
                events,
                agent=agent,
                base=base,
                facility=facility,
                store=api_store,
                prompt=request.message,
            ),
            media_type="text/event-stream",
        )

    return application


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message, "detail": {}}},
    )


app = create_app()


def _append_audit(store: SQLiteStore, kind: str, detail: dict[str, Any]) -> None:
    """Make audit failures visible to callers instead of claiming success."""
    try:
        store.append(kind, detail)
    except Exception as exc:
        raise _error(500, "audit_unavailable", "audit logging failed") from exc


def _append_stream_audit(
    store: SQLiteStore, kind: str, detail: dict[str, Any]
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
    base: Recommendation,
    facility: Any,
    store: SQLiteStore,
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
