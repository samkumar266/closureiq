"""Wires api/notify into the API. Pasted from api/notify/INTEGRATION.md.

Everything here reads and writes through the Store; api/notify itself stays pure.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

from api.notify import escalation, service, standing_policy
from api.notify.email_sender import send_email
from api.notify.package import build_preview
from api.notify.simulator import recipient_status_from_deliveries

SEED_DIR = Path(__file__).resolve().parents[2] / "mocks" / "seed"
TEMPLATE_FACILITY = "kc-service-center"  # roster used when a facility has no seed roster


def storm_mode() -> bool:
    return os.getenv("NOTIFY_STORM_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def load_profile(facility: dict) -> dict:
    profiles = json.loads((SEED_DIR / "facility_profiles.json").read_text())["facilities"]
    seed = next((p for p in profiles if p["facility_id"] == facility["facility_id"]), None)
    return seed or facility


def load_roster(facility_id: str) -> list[dict]:
    path = SEED_DIR / f"roster_{facility_id}.json"
    if not path.exists():
        path = SEED_DIR / f"roster_{TEMPLATE_FACILITY}.json"
    return json.loads(path.read_text())["employees"]


def _rng(evaluation_id: str, kind: str) -> random.Random:
    return random.Random(f"{evaluation_id}:{kind}")  # same evaluation -> same simulation


class StoreOutbox:
    """dict-like view of notifications keyed by idempotency_key, for service.notify_once."""

    def __init__(self, store, approval_id: str | None):
        self.store, self.approval_id = store, approval_id

    def __contains__(self, key):
        return self.store.get_notification_by_key(key) is not None

    def __getitem__(self, key):
        return self.store.get_notification_by_key(key)

    def __setitem__(self, key, result):
        pkg = result["notification"]
        self.store.append_notification(
            evaluation_id=pkg["evaluation_id"], approval_id=pkg["approval_id"], package=pkg["package"],
            ack_deadline=pkg["ack_deadline"], next_update=pkg["next_update"],
            standing_policy=pkg["standing_policy"], notification_id=pkg["notification_id"],
            idempotency_key=key)


def preview(store, evaluation_record: dict, facility: dict, posture: str | None) -> dict:
    """Body for GET /api/evaluations/{id}/package-preview."""
    return build_preview(evaluation_record["result"], load_profile(facility),
                         load_roster(facility["facility_id"]), posture, now_sim=store.clock_now_sim())


def _send(store, evaluation: dict, facility: dict, *, posture, approval_id, kind) -> dict:
    key = service.idempotency_key(evaluation["evaluation_id"], kind)
    existing = store.get_notification_by_key(key)
    if existing:
        return existing  # already sent: a double approve sends nothing
    result, created = service.notify(
        key, StoreOutbox(store, approval_id), evaluation, load_profile(facility),
        load_roster(facility["facility_id"]), send_email_fn=send_email, posture=posture,
        approval_id=approval_id, notification_id=store._next_id("ntf"), now_sim=store.clock_now_sim(),
        rng=_rng(evaluation["evaluation_id"], kind), next_delivery_id=lambda: store._next_id("dlv"),
        next_timer_id=lambda: store._next_id("tmr"),
        standing_policy=standing_policy.STANDING_POLICY if kind == standing_policy.STANDING_POLICY else None,
        storm=storm_mode())
    if not created:
        return result  # already stored: a double approve sends nothing
    for row in result["timers"]:
        store.append_timer(row)
    store.append_audit("notification.sent", {"evaluation_id": evaluation["evaluation_id"],
                                             "notification_id": result["notification"]["notification_id"],
                                             "email_mode": result.get("email", {}).get("mode")})
    return store.get_notification_by_key(key)


def on_decision(store, evaluation: dict, facility: dict, approval: dict, final_posture: str | None) -> dict | None:
    """Call after append_approval. Cancels the manager chain; builds and sends unless rejected."""
    now = store.clock_now_sim()
    for row in store.list_timers(evaluation["evaluation_id"], pending_only=True):
        if row["kind"] in escalation.APPROVAL_KINDS:
            store.mark_timer_cancelled(row["id"], now)
    if approval["action"] == "reject":
        return None
    return _send(store, evaluation, facility, posture=final_posture, approval_id=approval["id"], kind="approval")


def on_evaluation_created(store, evaluation: dict, facility: dict) -> dict | None:
    """Call after append_evaluation. Starts the manager-response timers and the
    shelter-in-place standing-policy send (the only automatic send)."""
    now = store.clock_now_sim()
    shelter = standing_policy.should_auto_send(evaluation, now)
    if evaluation.get("posture") != "normal_operations" or shelter:
        for row in escalation.schedule_approval_timers(evaluation, load_profile(facility), now,
                                                       lambda: store._next_id("tmr"), shelter):
            store.append_timer(row)
    if shelter:
        return _send(store, evaluation, facility, posture=None, approval_id=None,
                     kind=standing_policy.STANDING_POLICY)
    return None


def run_due_timers(store, evaluation_lookup) -> list[tuple[str, dict]]:
    """Fire every due timer in order. Returns SSE events [(name, data), ...] to publish.

    evaluation_lookup(evaluation_id) -> recommendation dict (store.get_evaluation(id)["result"]).
    Call it once a second from the scheduler, and right after POST /api/clock.
    """
    timers = store.list_timers(pending_only=True)
    events: list[tuple[str, dict]] = []

    def on_fire(timer, action):
        store.mark_timer_fired(timer["id"], timer["due_at_sim"])
        if action["kind"] == "delivery_status":
            if action["status"] == "queued":
                store.append_delivery(notification_id=action["notification_id"], recipient_id=action["recipient_id"],
                                      channel=action["channel"], real=action["real"], status="queued",
                                      provider_ref=action.get("provider_ref"), delivery_id=action["delivery_id"],
                                      at_sim=action["at_sim"])
            else:
                store.append_delivery_status(action["delivery_id"], action["status"], at_sim=action["at_sim"])
            events.append(("delivery.updated", {"delivery_id": action["delivery_id"],
                                                "notification_id": action["notification_id"],
                                                "status": action["status"]}))
            return
        store.append_audit("escalation.fired", {**action, "evaluation_id": timer["payload"].get("evaluation_id")})
        if action.get("mark_unresolved"):
            store.append_audit("evaluation.unresolved", {"evaluation_id": timer["payload"]["evaluation_id"]})
        events.append(("escalation.fired", {"notification_id": timer["payload"].get("notification_id"),
                                            "step": action["kind"], "next_due_sim": None}))

    # Fire per evaluation so each ack timer sees only its own notification's deliveries.
    for evaluation_id in dict.fromkeys(t["payload"].get("evaluation_id") for t in timers):
        group = [t for t in timers if t["payload"].get("evaluation_id") == evaluation_id]
        evaluation = evaluation_lookup(evaluation_id)
        notification_ids = {t["payload"]["notification_id"] for t in group if t["payload"].get("notification_id")}

        def statuses(_at, ids=notification_ids):
            return recipient_status_from_deliveries([d for nid in ids for d in store.list_deliveries(nid)])
        ctx = {"evaluation": evaluation, "roster": load_roster(evaluation["facility_id"]),
               "recipient_status_at": statuses}
        _, new_rows, _ = escalation.fire_due(group, store.clock_now_sim(), ctx,
                                             lambda: store._next_id("tmr"), on_fire=on_fire)
        for row in new_rows:  # follow-ups such as UNRESOLVED; may already be fired
            store.append_timer(row)
    next_due_sim = escalation.next_due(store.list_timers(pending_only=True))
    for name, data in events:
        if name == "escalation.fired":
            data["next_due_sim"] = next_due_sim
    return events


def escalation_for(store, evaluation_id: str, tz_name: str) -> list[dict]:
    """Contract escalation[] for GET /api/notifications/{id}."""
    return escalation.escalation_view(store.list_timers(evaluation_id), tz_name)
