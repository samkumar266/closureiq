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
from .agent_stream import _stream_chat
from ..engine import Recommendation, run_what_if
from ..legacy_store import SQLiteStore


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
    # Own default file: this legacy app must never open the main app's data/closureiq.db.
    api_store = store or SQLiteStore(os.getenv("LEGACY_DB_PATH", "data/legacy_closureiq.db"))

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
