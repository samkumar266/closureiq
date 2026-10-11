"""Application entry point: `uvicorn api.main:app --reload`."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ImportError:  # graceful local fallback; requirements.txt installs APScheduler for the intended run
    AsyncIOScheduler = None  # type: ignore[assignment,misc]
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.app.routes import router, error_payload, evaluate_and_record
from api.app.events import event_hub
from api.config import settings
from api.facilities import FACILITIES
from api.ingest.poller import poll_alerts, poll_observations, poll_slow_sources, startup_poll
from api.store.repository import Store

logger = logging.getLogger("closureiq.scheduler")


def create_app(db_path: str | Path | None = None, *, enable_scheduler: bool | None = None,
               poll_on_startup: bool | None = None) -> FastAPI:
    store = Store(db_path or settings.resolved_db_path(), default_data_mode=settings.data_mode)
    scheduler_enabled = settings.enable_scheduler if enable_scheduler is None else enable_scheduler
    startup_enabled = settings.poll_on_startup if poll_on_startup is None else poll_on_startup
    scheduler_holder: dict[str, object | None] = {"scheduler": None}
    fallback_scheduler_task: asyncio.Task | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal fallback_scheduler_task
        if scheduler_enabled:
            async def evaluate_all():
                # Architecture loop: poll -> store -> evaluate -> SSE. Records only when the decision changes.
                for facility in FACILITIES.values():
                    try:
                        await evaluate_and_record(store, facility, only_if_changed=True)
                    except Exception:
                        logger.exception("Scheduled evaluation failed for %s", facility["facility_id"])
            # DEPRECATED(closureiq) START: alerts poll without the evaluate step.
            # async def alerts_job():
            #     await asyncio.gather(*(poll_alerts(store, f) for f in FACILITIES.values()), return_exceptions=True)
            # DEPRECATED(closureiq) END
            async def alerts_job():
                await asyncio.gather(*(poll_alerts(store, f) for f in FACILITIES.values()), return_exceptions=True)
                await asyncio.gather(*(poll_observations(store, f) for f in FACILITIES.values()), return_exceptions=True)
                await evaluate_all()
            async def timers_job():
                from api.app import notify_wiring
                for name, data in notify_wiring.run_due_timers(store, lambda eid: store.get_evaluation(eid)["result"]):
                    await event_hub.publish(name, data)
            # DEPRECATED(closureiq) START: forecast poll without the evaluate step.
            # async def slow_job():
            #     await asyncio.gather(*(poll_slow_sources(store, f, force=False) for f in FACILITIES.values()), return_exceptions=True)
            # DEPRECATED(closureiq) END
            async def slow_job():
                await asyncio.gather(*(poll_slow_sources(store, f, force=False) for f in FACILITIES.values()), return_exceptions=True)
                await evaluate_all()
            if AsyncIOScheduler is not None:
                scheduler = AsyncIOScheduler(timezone="UTC")
                scheduler.add_job(alerts_job, "interval", seconds=60, id="nws-alerts-poll", max_instances=1, coalesce=True)
                scheduler.add_job(slow_job, "interval", seconds=900, id="slow-sources-poll", max_instances=1, coalesce=True)
                scheduler.add_job(timers_job, "interval", seconds=1, id="notify-timers", max_instances=1, coalesce=True)
                scheduler.start()
                scheduler_holder["scheduler"] = scheduler
            else:
                # Keeps the API runnable when APScheduler could not be installed offline.
                async def fallback_loop():
                    seconds_since_slow = 900
                    while True:
                        await asyncio.sleep(60)
                        await alerts_job()
                        seconds_since_slow += 60
                        if seconds_since_slow >= 900:
                            await slow_job()
                            seconds_since_slow = 0
                fallback_scheduler_task = asyncio.create_task(fallback_loop())
        if startup_enabled:
            app.state.startup_poll_task = asyncio.create_task(startup_poll(store, list(FACILITIES.values())))
        try:
            yield
        finally:
            if scheduler_holder["scheduler"]:
                scheduler_holder["scheduler"].shutdown(wait=False)
            if fallback_scheduler_task and not fallback_scheduler_task.done():
                fallback_scheduler_task.cancel()
            task = getattr(app.state, "startup_poll_task", None)
            if task and not task.done():
                task.cancel()

    app = FastAPI(
        title="ClosureIQ Badri Backend",
        version="0.1.0",
        description="Badri's evidence ingestion, SQLite store and API wiring for ClosureIQ MVP.",
        lifespan=lifespan,
    )
    app.state.store = store
    app.state.event_hub = event_hub
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.exception_handler(HTTPException)
    async def contract_http_error(_request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "contract_error" in detail:
            payload = detail["contract_error"]
        else:
            code = {400: "bad_request", 404: "not_found", 409: "conflict", 422: "bad_request"}.get(exc.status_code, "request_failed")
            payload = error_payload(code, str(detail), {})
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        safe_errors = [{"loc": list(err.get("loc", [])), "msg": err.get("msg", "Invalid request"), "type": err.get("type", "value_error")} for err in exc.errors()]
        return JSONResponse(status_code=400, content=error_payload("bad_request", "Request validation failed", {"errors": safe_errors}))

    @app.get("/")
    def root():
        return {"service": "ClosureIQ Badri Backend", "health": "/api/health", "docs": "/docs"}

    return app


app = create_app()
