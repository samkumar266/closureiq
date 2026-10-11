"""Contract endpoints for ClosureIQ: evidence ingest, evaluation, history and store workflows."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Query, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

from api.config import settings
from api.facilities import FACILITIES, get_facility, public_facility
from api.ingest.poller import poll_facility, poll_alerts, poll_slow_sources, SOURCE_MAX_AGE_SECONDS
from api.ingest.normalizers import highest_alert_tier, parse_datetime
from api.app.engine_adapter import evaluate_recommendation, POSTURES
from api.app.events import event_hub
from api.app import notify_wiring
from api.app.thresholds import thresholds_response
from api.store.repository import Store

router = APIRouter(prefix="/api")


class WhatIfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overrides: dict[str, Any]


class ActorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=160)


class RejectRequest(ActorRequest):
    reason: str = Field(min_length=1, max_length=1000)


class OverrideRequest(RejectRequest):
    posture: str


class ModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_mode: str


class ClockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    speed: float = 1.0
    set_to: str | None = None


def store_from_request(request: Request) -> Store:
    return request.app.state.store


def error_payload(code: str, message: str, detail: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail or {}}}


def raise_contract_error(status_code: int, code: str, message: str, detail: dict | None = None):
    raise HTTPException(status_code=status_code, detail={"contract_error": error_payload(code, message, detail)})


def _local_iso(value: str | None, timezone_name: str) -> str | None:
    parsed = parse_datetime(value)
    if not parsed:
        return None
    try:
        return parsed.astimezone(ZoneInfo(timezone_name)).isoformat()
    except Exception:
        return parsed.isoformat()


def _snapshot_age(snapshot: dict | None) -> float | None:
    if not snapshot:
        return None
    parsed = parse_datetime(snapshot.get("fetched_at_wall"))
    if not parsed:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())


def _status_for_source(store: Store, facility: dict, source: str) -> dict:
    max_age = SOURCE_MAX_AGE_SECONDS.get(source, 600)
    latest_success = store.latest_snapshot(facility["facility_id"], source, successful_only=True)
    latest_attempt = store.latest_snapshot(facility["facility_id"], source, successful_only=False)
    age = _snapshot_age(latest_success)
    if latest_success is None:
        status = "missing"
        fetched = latest_attempt.get("fetched_at_wall") if latest_attempt else None
        age_seconds = _snapshot_age(latest_attempt)
    elif age is None or age > max_age:
        status = "stale"
        fetched = latest_success.get("fetched_at_wall")
        age_seconds = age
    else:
        status = "fresh"
        fetched = latest_success.get("fetched_at_wall")
        age_seconds = age
    return {"source": source, "status": status,
            "fetched_at": _local_iso(fetched, facility["location"]["timezone"]),
            "age_seconds": int(age_seconds) if age_seconds is not None else None,
            "max_age_seconds": max_age}


def _source_list(store: Store, facility: dict) -> list[dict]:
    sources = ["NWS alerts", "NWS point metadata", "NWS forecast grid", "NWS hourly forecast"]
    if facility.get("gauge"):
        sources.extend(["USGS gauge", "NWS flood categories"])
    return [_status_for_source(store, facility, source) for source in sources]


def _context_snapshots(store: Store, facility_id: str) -> list[dict]:
    """Return latest attempt per source plus last successful evidence if latest attempt failed."""
    latest = store.latest_snapshots(facility_id)
    by_key = {(s["source"], s["id"]): s for s in latest}
    rows = list(latest)
    seen = {s["id"] for s in rows}
    for snapshot in latest:
        if not snapshot["ok"]:
            good = store.latest_snapshot(facility_id, snapshot["source"], successful_only=True)
            if good and good["id"] not in seen:
                rows.append(good)
                seen.add(good["id"])
    # Keep evidence chronological so source replacement behavior is deterministic.
    rows.sort(key=lambda s: (s.get("fetched_at_wall") or "", s.get("id") or ""))
    return rows


def _serialize_evaluation(record: dict | None):
    return record["result"] if record else None


def _alert_payload_for_facility(store: Store, facility_id: str) -> dict:
    snapshot = store.latest_snapshot(facility_id, "NWS alerts", successful_only=True)
    return snapshot.get("raw_payload_json", {}) if snapshot else {}


def _facility_list_item(store: Store, facility: dict) -> dict:
    latest_eval = store.latest_evaluation(facility["facility_id"])
    source_statuses = [item["status"] for item in _source_list(store, facility)]
    if any(status == "missing" for status in source_statuses):
        source_health = "missing"
    elif any(status == "stale" for status in source_statuses):
        source_health = "degraded"
    else:
        source_health = "ok"
    current = None
    if latest_eval:
        result = latest_eval["result"]
        approval = store.get_approval_by_evaluation(latest_eval["id"])
        status = "pending"
        if approval:
            status = {"approve": "approved", "reject": "rejected", "override": "overridden"}.get(approval["action"], "pending")
        current = {
            "evaluation_id": latest_eval["id"], "posture": result.get("posture"),
            "confidence": result.get("confidence"), "evaluated_at": result.get("evaluated_at"),
            "decision_deadline": result.get("decision_deadline"),
            "headline": result.get("headline") or result.get("rationale"),
            "approval_status": status,
        }
    return {
        "facility_id": facility["facility_id"], "name": facility["name"],
        "location": facility["location"],
        "highest_alert_tier": highest_alert_tier(_alert_payload_for_facility(store, facility["facility_id"])),
        "source_health": source_health, "data_mode": store.get_data_mode(settings.data_mode),
        "current": current,
    }


@router.get("/health")
def health(request: Request):
    store = store_from_request(request)
    clock = store.get_clock()
    return {"ok": True, "data_mode": store.get_data_mode(settings.data_mode),
            "clock": {"mode": clock["mode"], "now_sim": clock["now_sim"], "now_wall": clock["now_wall"]},
            "last_poll_at": store.get_last_poll_at()}


@router.get("/facilities")
def list_facilities(request: Request):
    store = store_from_request(request)
    items = [_facility_list_item(store, f) for f in FACILITIES.values()]
    tier_rank = {"none": 0, "advisory": 1, "watch": 2, "warning": 3}
    posture_rank = {"normal_operations": 0, "delayed_arrival": 1, "early_dismissal": 2,
                    "unscheduled_leave_or_telework": 3, "closure": 4}
    items.sort(key=lambda item: (
        -tier_rank.get(item["highest_alert_tier"], 0),
        -posture_rank.get((item.get("current") or {}).get("posture", "normal_operations"), 0),
        item["name"].lower(),
    ))
    return {"facilities": items}


@router.get("/facilities/{facility_id}")
def facility_profile(facility_id: str):
    facility = get_facility(facility_id)
    if not facility:
        raise_contract_error(404, "not_found", "Unknown facility", {"facility_id": facility_id})
    return public_facility(facility)


@router.get("/facilities/{facility_id}/roster")
def facility_roster(facility_id: str):
    facility = get_facility(facility_id)
    if not facility:
        raise_contract_error(404, "not_found", "Unknown facility", {"facility_id": facility_id})
    return {"employees": notify_wiring.load_roster(facility_id)}


@router.get("/facilities/{facility_id}/status")
def facility_status(facility_id: str, request: Request):
    store = store_from_request(request)
    facility = get_facility(facility_id)
    if not facility:
        raise_contract_error(404, "not_found", "Unknown facility", {"facility_id": facility_id})
    latest = store.latest_evaluation(facility_id)
    approval = store.get_approval_by_evaluation(latest["id"]) if latest else None
    notification = store.get_notification_by_evaluation(latest["id"]) if latest else None
    if approval:
        approval = _format_approval(approval, facility["location"]["timezone"])
    return {"facility_id": facility_id,
            "evaluation": _serialize_evaluation(latest),
            "approval": approval,
            "notification_id": notification["id"] if notification else None,
            "sources": _source_list(store, facility)}


@router.post("/facilities/{facility_id}/evaluate")
async def evaluate_facility(facility_id: str, request: Request):
    store = store_from_request(request)
    facility = get_facility(facility_id)
    if not facility:
        raise_contract_error(404, "not_found", "Unknown facility", {"facility_id": facility_id})
    previous = store.latest_evaluation(facility_id)
    previous_result = previous["result"] if previous else None
    polled = await poll_facility(store, facility, force_slow=True)
    evidence = _context_snapshots(store, facility_id)
    now = datetime.now(timezone.utc)
    result = evaluate_recommendation(store, facility, evidence, evaluated_at=now, previous_result=previous_result)
    evidence_ids = list(dict.fromkeys(s["id"] for s in evidence))
    evaluation = store.append_evaluation(
        facility_id=facility_id, evaluated_at_wall=now.isoformat(),
        evaluated_at_sim=store.clock_now_sim(), data_mode=store.get_data_mode(settings.data_mode),
        evidence_ids=evidence_ids, engine_version=result.get("engine_version", "shared-engine-not-yet-integrated"),
        policy_version=facility.get("policy_version", "policy-2026-10-10.1"), result=result,
        posture=result["posture"], confidence=result["confidence"]["level"],
        supersedes=previous["id"] if previous else None,
    )
    saved = evaluation["result"]
    notify_wiring.on_evaluation_created(store, saved, facility)
    changed = not previous or previous["result"].get("posture") != saved.get("posture") or previous["result"].get("confidence") != saved.get("confidence")
    await event_hub.publish("evaluation.created", {
        "facility_id": facility_id, "evaluation_id": saved["evaluation_id"],
        "posture": saved["posture"], "confidence": saved["confidence"], "changed": changed,
    })
    if not any(row.get("ok") for row in polled):
        return JSONResponse(status_code=503, content=error_payload(
            "source_unavailable", "No source answered; a low-confidence evaluation was recorded.",
            {"evaluation_id": saved["evaluation_id"]},
        ))
    return saved


@router.get("/evaluations")
def evaluation_history(request: Request, facility_id: str | None = None,
                       limit: int = Query(default=20, ge=1, le=200)):
    store = store_from_request(request)
    if facility_id and not get_facility(facility_id):
        raise_contract_error(404, "not_found", "Unknown facility", {"facility_id": facility_id})
    return {"evaluations": [e["result"] for e in store.list_evaluations(facility_id, limit)]}


@router.get("/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: str, request: Request):
    record = store_from_request(request).get_evaluation(evaluation_id)
    if not record:
        raise_contract_error(404, "not_found", "Unknown evaluation", {"evaluation_id": evaluation_id})
    return record["result"]


@router.get("/evaluations/{evaluation_id}/record")
def decision_record(evaluation_id: str, request: Request):
    store = store_from_request(request)
    record = store.record_for_evaluation(evaluation_id)
    if not record:
        raise_contract_error(404, "not_found", "Unknown evaluation", {"evaluation_id": evaluation_id})
    facility = get_facility(record["evaluation"]["facility_id"])
    timezone_name = facility["location"]["timezone"]
    for item in record.get("evidence", []):
        item["fetched_at_wall"] = _local_iso(item.get("fetched_at_wall"), timezone_name)
        item["fetched_at_sim"] = _local_iso(item.get("fetched_at_sim"), timezone_name)
    if record.get("approval"):
        record["approval"] = _format_approval(record["approval"], timezone_name, include_sim=True)
    if record.get("notification"):
        for field in ("created_at_wall", "created_at_sim"):
            record["notification"][field] = _local_iso(record["notification"].get(field), timezone_name)
    for audit in record.get("audit_log", []):
        audit["at_wall"] = _local_iso(audit.get("at_wall"), timezone_name)
        audit["at_sim"] = _local_iso(audit.get("at_sim"), timezone_name)
    # Normalize delivery events to the contract's concise at_wall/at_sim field names.
    for delivery in record.get("deliveries", []):
        delivery["delivery_id"] = delivery.pop("id", None)
        delivery["status_history"] = [
            {"status": item["status"], "at_wall": _local_iso(item["status_at_wall"], timezone_name), "at_sim": _local_iso(item["status_at_sim"], timezone_name)}
            for item in delivery.get("status_history", [])
        ]
    return record


def _diff(stored: Any, replayed: Any, path: str = "") -> list[dict]:
    diffs: list[dict] = []
    if isinstance(stored, dict) and isinstance(replayed, dict):
        keys = sorted(set(stored) | set(replayed))
        for key in keys:
            next_path = f"{path}.{key}" if path else key
            if key not in stored:
                diffs.append({"path": next_path, "stored": None, "replayed": replayed[key]})
            elif key not in replayed:
                diffs.append({"path": next_path, "stored": stored[key], "replayed": None})
            else:
                diffs.extend(_diff(stored[key], replayed[key], next_path))
    elif isinstance(stored, list) and isinstance(replayed, list):
        if len(stored) != len(replayed):
            diffs.append({"path": path, "stored": stored, "replayed": replayed})
        else:
            for index, (a, b) in enumerate(zip(stored, replayed)):
                diffs.extend(_diff(a, b, f"{path}[{index}]"))
    elif stored != replayed:
        diffs.append({"path": path, "stored": stored, "replayed": replayed})
    return diffs


@router.post("/evaluations/{evaluation_id}/replay")
def replay_evaluation(evaluation_id: str, request: Request):
    store = store_from_request(request)
    record = store.get_evaluation(evaluation_id)
    if not record:
        raise_contract_error(404, "not_found", "Unknown evaluation", {"evaluation_id": evaluation_id})
    facility = get_facility(record["facility_id"])
    evidence = store.snapshots_by_ids(record["evidence_ids"])
    original_time = parse_datetime(record["evaluated_at_wall"]) or datetime.now(timezone.utc)
    replayed = evaluate_recommendation(store, facility, evidence, evaluated_at=original_time,
                                       previous_result=None, hypothetical=False,
                                       data_mode=record["data_mode"])
    # Compare only engine output fields. Storage-generated identity/supersedes/timestamps are excluded.
    stored_result = {k: v for k, v in record["result"].items() if k not in {"evaluation_id", "supersedes", "hypothetical", "data_mode"}}
    replay_result = {k: v for k, v in replayed.items() if k not in {"evaluation_id", "supersedes", "hypothetical", "data_mode"}}
    diff = _diff(stored_result, replay_result)
    store.append_audit("replay", {"evaluation_id": evaluation_id, "identical": not diff, "diff": diff})
    return {"identical": not diff, "diff": diff}


def run_what_if(store: Store, base: dict, overrides: dict) -> dict:
    """Rerun stored evidence with overrides. Writes only an audit row. Shared by the
    what-if route and the agent's run_what_if tool."""
    evidence = store.snapshots_by_ids(base["evidence_ids"])
    facility = get_facility(base["facility_id"])
    result = evaluate_recommendation(store, facility, evidence,
                                     evaluated_at=parse_datetime(base["evaluated_at_wall"]),
                                     previous_result=base["result"], overrides=overrides,
                                     hypothetical=True, data_mode=base["data_mode"])
    result["hypothetical"] = True
    whatif_id = store._next_id("wif")
    changed = [key for key in result if key in base["result"] and result[key] != base["result"][key]]
    store.append_audit("whatif", {"whatif_id": whatif_id, "based_on": base["id"], "evaluation_id": base["id"],
                                  "overrides": overrides, "result": result, "changed_fields": changed})
    return {"hypothetical": True, "whatif_id": whatif_id, "based_on": base["id"],
            "result": result, "changed_fields": changed}


@router.post("/evaluations/{evaluation_id}/what-if")
def what_if(evaluation_id: str, body: WhatIfRequest, request: Request):
    store = store_from_request(request)
    base = store.get_evaluation(evaluation_id)
    if not base:
        raise_contract_error(404, "not_found", "Unknown evaluation", {"evaluation_id": evaluation_id})
    return run_what_if(store, base, body.overrides)


@router.get("/thresholds")
def get_thresholds():
    return thresholds_response()


@router.post("/mode")
async def switch_mode(body: ModeRequest, request: Request):
    if body.data_mode not in {"live", "replay"}:
        raise_contract_error(400, "bad_request", "data_mode must be 'live' or 'replay'")
    store = store_from_request(request)
    store.set_data_mode(body.data_mode)
    store.append_audit("mode.changed", {"data_mode": body.data_mode})
    await event_hub.publish("mode.changed", {"data_mode": body.data_mode})
    return {"data_mode": body.data_mode}


@router.get("/clock")
def get_clock(request: Request):
    return store_from_request(request).get_clock()


@router.post("/clock")
async def set_clock(body: ClockRequest, request: Request):
    if body.mode not in {"system", "simulated"}:
        raise_contract_error(400, "bad_request", "mode must be 'system' or 'simulated'")
    if not 0 < body.speed <= 600:
        raise_contract_error(400, "bad_request", "speed must be greater than 0 and no more than 600")
    if body.set_to:
        parsed = parse_datetime(body.set_to)
        if parsed is None:
            raise_contract_error(400, "bad_request", "set_to must be an ISO 8601 timestamp with an offset")
    store = store_from_request(request)
    result = store.set_clock(body.mode, body.speed, body.set_to)
    asyncio.create_task(event_hub.publish("clock.changed", result))
    for name, data in notify_wiring.run_due_timers(store, lambda eid: store.get_evaluation(eid)["result"]):
        asyncio.create_task(event_hub.publish(name, data))
    return result


@router.get("/evaluations/{evaluation_id}/package-preview")
def package_preview(evaluation_id: str, request: Request, posture: str | None = None):
    store = store_from_request(request)
    record = store.get_evaluation(evaluation_id)
    if not record:
        raise_contract_error(404, "not_found", "Unknown evaluation", {"evaluation_id": evaluation_id})
    if posture is not None and posture not in POSTURES:
        raise_contract_error(422, "invalid_posture", "Override posture is not one of the five allowed values", {"posture": posture})
    return notify_wiring.preview(store, record, get_facility(record["facility_id"]), posture)


def _stale_check(store: Store, evaluation_id: str, facility_id: str):
    latest = store.latest_evaluation(facility_id)
    if latest and latest["id"] != evaluation_id:
        raise_contract_error(409, "stale_evaluation", "A newer evaluation exists; refresh before deciding.", {"latest_id": latest["id"]})


def _format_approval(approval: dict | None, timezone_name: str, *, include_sim: bool = False) -> dict | None:
    if not approval:
        return None
    formatted = {
        "id": approval["id"], "evaluation_id": approval["evaluation_id"],
        "action": approval["action"], "final_posture": approval["final_posture"],
        "actor": approval["actor"], "reason": approval.get("reason"),
        "acted_at_wall": _local_iso(approval.get("acted_at_wall"), timezone_name),
    }
    if include_sim:
        formatted["acted_at_sim"] = _local_iso(approval.get("acted_at_sim"), timezone_name)
    return formatted


def _approval_response(approval: dict, notification: dict | None, timezone_name: str) -> dict:
    return {"approval": _format_approval(approval, timezone_name),
            "notification_id": notification["id"] if notification else None}


def _create_notification(store: Store, evaluation: dict, approval: dict, final_posture: str) -> dict:
    facility = get_facility(evaluation["facility_id"])
    notification = notify_wiring.on_decision(store, evaluation, facility, approval, final_posture)
    return {"id": notification["id"]} if notification else None


@router.post("/evaluations/{evaluation_id}/approve")
async def approve_evaluation(evaluation_id: str, body: ActorRequest, request: Request):
    store = store_from_request(request)
    record = store.get_evaluation(evaluation_id)
    if not record:
        raise_contract_error(404, "not_found", "Unknown evaluation", {"evaluation_id": evaluation_id})
    if not body.actor.strip():
        raise_contract_error(400, "bad_request", "actor is required")
    existing = store.get_approval_by_evaluation(evaluation_id)
    if existing:
        return JSONResponse(status_code=409, content={
            **error_payload("already_decided", "This evaluation already has a recorded decision.", {"evaluation_id": evaluation_id}),
            "approval": _format_approval(existing, get_facility(record["facility_id"])["location"]["timezone"]),
        })
    _stale_check(store, evaluation_id, record["facility_id"])
    approval = store.append_approval(evaluation_id=evaluation_id, action="approve",
                                     final_posture=record["result"]["posture"], actor=body.actor, reason=None)
    notification = _create_notification(store, record["result"], approval, approval["final_posture"])
    await event_hub.publish("approval.recorded", {"evaluation_id": evaluation_id,
                              "action": "approve", "final_posture": approval["final_posture"]})
    return _approval_response(approval, notification, get_facility(record["facility_id"])["location"]["timezone"])


@router.post("/evaluations/{evaluation_id}/reject")
async def reject_evaluation(evaluation_id: str, body: RejectRequest, request: Request):
    store = store_from_request(request)
    record = store.get_evaluation(evaluation_id)
    if not record:
        raise_contract_error(404, "not_found", "Unknown evaluation", {"evaluation_id": evaluation_id})
    if not body.actor.strip() or not body.reason.strip():
        raise_contract_error(400, "bad_request", "actor and reason are required")
    existing = store.get_approval_by_evaluation(evaluation_id)
    if existing:
        return JSONResponse(status_code=409, content={
            **error_payload("already_decided", "This evaluation already has a recorded decision.", {"evaluation_id": evaluation_id}),
            "approval": _format_approval(existing, get_facility(record["facility_id"])["location"]["timezone"]),
        })
    _stale_check(store, evaluation_id, record["facility_id"])
    approval = store.append_approval(evaluation_id=evaluation_id, action="reject",
                                     final_posture=record["result"]["posture"], actor=body.actor,
                                     reason=body.reason.strip())
    notify_wiring.on_decision(store, record["result"], get_facility(record["facility_id"]), approval, None)
    await event_hub.publish("approval.recorded", {"evaluation_id": evaluation_id,
                              "action": "reject", "final_posture": approval["final_posture"]})
    return _approval_response(approval, None, get_facility(record["facility_id"])["location"]["timezone"])


@router.post("/evaluations/{evaluation_id}/override")
async def override_evaluation(evaluation_id: str, body: OverrideRequest, request: Request):
    store = store_from_request(request)
    record = store.get_evaluation(evaluation_id)
    if not record:
        raise_contract_error(404, "not_found", "Unknown evaluation", {"evaluation_id": evaluation_id})
    if body.posture not in POSTURES:
        raise_contract_error(422, "invalid_posture", "Override posture is not one of the five allowed values", {"posture": body.posture})
    if not body.reason.strip():
        raise_contract_error(400, "bad_request", "reason is required for override")
    if not body.actor.strip() or not body.reason.strip():
        raise_contract_error(400, "bad_request", "actor and reason are required")
    existing = store.get_approval_by_evaluation(evaluation_id)
    if existing:
        return JSONResponse(status_code=409, content={
            **error_payload("already_decided", "This evaluation already has a recorded decision.", {"evaluation_id": evaluation_id}),
            "approval": _format_approval(existing, get_facility(record["facility_id"])["location"]["timezone"]),
        })
    _stale_check(store, evaluation_id, record["facility_id"])
    approval = store.append_approval(evaluation_id=evaluation_id, action="override",
                                     final_posture=body.posture, actor=body.actor, reason=body.reason.strip())
    notification = _create_notification(store, record["result"], approval, body.posture)
    await event_hub.publish("approval.recorded", {"evaluation_id": evaluation_id,
                              "action": "override", "final_posture": body.posture})
    return _approval_response(approval, notification, get_facility(record["facility_id"])["location"]["timezone"])


@router.get("/notifications/{notification_id}")
def get_notification(notification_id: str, request: Request):
    record = store_from_request(request).get_notification(notification_id)
    if not record:
        raise_contract_error(404, "not_found", "Unknown notification", {"notification_id": notification_id})
    evaluation = store_from_request(request).get_evaluation(record["evaluation_id"])
    facility = get_facility(evaluation["facility_id"]) if evaluation else None
    timezone_name = facility["location"]["timezone"] if facility else "UTC"
    deliveries = []
    for delivery in record.get("deliveries", []):
        deliveries.append({
            "delivery_id": delivery["id"], "recipient_id": delivery["recipient_id"],
            "channel": delivery["channel"], "real": delivery["real"],
            "status": delivery["status"], "status_at_wall": _local_iso(delivery["status_at_wall"], timezone_name),
        })
    record["escalation"] = notify_wiring.escalation_for(store_from_request(request), record["evaluation_id"], timezone_name,
                                                      notification_id=record["id"])
    return {
        "notification_id": record["id"], "evaluation_id": record["evaluation_id"],
        "approval_id": record["approval_id"], "standing_policy": record["standing_policy"],
        "preview": record["preview"], "ack_deadline": record["ack_deadline"],
        "next_update": record["next_update"], "package": record["package"],
        "deliveries": deliveries, "escalation": record["escalation"],
    }


@router.post("/deliveries/{delivery_id}/ack")
async def acknowledge_delivery(delivery_id: str, request: Request, body: dict = Body(default={})):
    store = store_from_request(request)
    delivery = store.get_delivery(delivery_id)
    if not delivery:
        raise_contract_error(404, "not_found", "Unknown delivery", {"delivery_id": delivery_id})
    if delivery["status"] != "acknowledged":
        delivery = store.append_delivery_status(delivery_id, "acknowledged")
    notification_id = delivery["notification_id"]
    notification = store.get_notification(notification_id)
    evaluation = store.get_evaluation(notification["evaluation_id"]) if notification else None
    facility = get_facility(evaluation["facility_id"]) if evaluation else None
    timezone_name = facility["location"]["timezone"] if facility else "UTC"
    await event_hub.publish("delivery.updated", {"delivery_id": delivery_id,
                              "notification_id": notification_id, "status": "acknowledged"})
    return {"delivery_id": delivery_id, "recipient_id": delivery["recipient_id"],
            "channel": delivery["channel"], "real": delivery["real"],
            "status": delivery["status"], "status_at_wall": _local_iso(delivery["status_at_wall"], timezone_name)}


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facility_id: str
    evaluation_id: str
    message: str = Field(min_length=1)


class _AgentBackend:
    """Read-only tools for the agent, backed by the main store (see ai.chat.build_backend_chat_agent)."""

    def __init__(self, store: Store, base: dict):
        self.store, self.base = store, base

    def get_evidence(self, snapshot_id: str) -> dict:
        if snapshot_id not in self.base["evidence_ids"]:
            raise ValueError("evidence snapshot is not part of this evaluation")
        snap = self.store.get_snapshot(snapshot_id)
        return {"snapshot_id": snap["id"], "source": snap["source"], "url": snap.get("url"),
                "fetched_at_wall": snap.get("fetched_at_wall"), "ok": snap.get("ok"),
                "raw_payload": snap.get("raw_payload_json")}

    def list_affected_employees(self, group: str | None = None) -> list[dict]:
        roster = notify_wiring.load_roster(self.base["facility_id"])
        rows = [{k: e[k] for k in ("employee_id", "group", "essential", "telework_eligible", "work_status_today")}
                for e in roster]
        return [r for r in rows if not group or r["group"] == group]

    def get_thresholds(self) -> list[dict]:
        return thresholds_response()["thresholds"]

    def run_what_if(self, overrides: dict) -> dict:
        out = run_what_if(self.store, self.base, overrides)
        # agent_stream picks up the what-if id from a hypothetical result's evaluation_id
        return {**out["result"], "evaluation_id": out["whatif_id"], "whatif_id": out["whatif_id"],
                "based_on": out["based_on"], "changed_fields": out["changed_fields"]}


class _AuditSink:
    """append(kind, detail) for agent_stream, written to the audit log under the evaluation."""

    def __init__(self, store: Store, evaluation_id: str):
        self.store, self.evaluation_id = store, evaluation_id

    def append(self, kind: str, detail: dict) -> None:
        self.store.append_audit(kind, {"evaluation_id": self.evaluation_id, **detail})


@router.post("/agent/chat")
async def agent_chat(body: ChatRequest, request: Request):
    from types import SimpleNamespace
    from ai.chat import build_backend_chat_agent, stream_agent_events
    from api.app.agent_stream import _stream_chat

    store = store_from_request(request)
    base = store.get_evaluation(body.evaluation_id)
    if not base or base["facility_id"] != body.facility_id:
        raise_contract_error(404, "not_found", "Unknown evaluation for this facility",
                             {"evaluation_id": body.evaluation_id})
    facility = get_facility(base["facility_id"])
    audit = _AuditSink(store, body.evaluation_id)
    audit.append("agent_question", {"facility_id": body.facility_id, "message": body.message})
    try:
        agent = build_backend_chat_agent(base["result"], _AgentBackend(store, base))
    except ValueError as exc:  # model not configured: names the missing variables, never values
        raise_contract_error(503, "agent_unavailable", f"Agent unavailable: {exc}", {})
    except Exception:
        raise_contract_error(503, "agent_unavailable", "Agent unavailable: the model could not be created.", {})
    try:
        events = stream_agent_events(agent, body.message)
        first_event = await events.__anext__()
    except Exception:
        raise_contract_error(503, "agent_unavailable", "Agent unavailable: the model provider did not answer.", {})
    return StreamingResponse(
        _stream_chat(first_event, events, agent=agent,
                     base=SimpleNamespace(evaluation_id=base["id"], rationale=base["result"].get("rationale", "")),
                     facility=SimpleNamespace(timezone=facility["location"]["timezone"]),
                     store=audit, prompt=body.message),
        media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/events")
async def events():
    return StreamingResponse(event_hub.subscribe(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
