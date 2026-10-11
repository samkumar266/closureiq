"""Glue: build a package, plan deliveries, send the one real email, set timers.

Idempotent: one notification per idempotency key, where the key is
"{evaluation_id}:approval" or "{evaluation_id}:shelter_in_place". A double
approve returns the existing notification and sends nothing.

`outbox` is any dict-like keyed by idempotency key. Tests pass a dict; the app
backs it with the notifications.idempotency_key UNIQUE column (INTEGRATION.md).
"""
from __future__ import annotations

import random
import threading
from datetime import datetime
from typing import Callable, MutableMapping

from api.notify.escalation import schedule_ack_timer
from api.notify.package import build_package
from api.notify.recipients import POSTURE_LABEL
from api.notify.simulator import mark_real_result, plan_deliveries
from api.notify.standing_policy import STANDING_POLICY, shelter_timers

_lock = threading.Lock()


def idempotency_key(evaluation_id: str, kind: str = "approval") -> str:
    return f"{evaluation_id}:{kind}"


def notify_once(key: str, outbox: MutableMapping, build_fn: Callable[[], dict],
                send_fn: Callable[[dict], None]) -> tuple[dict, bool]:
    """Returns (notification, created). Stores before sending, so a retry never sends twice."""
    with _lock:
        if key in outbox:
            return outbox[key], False
        notification = build_fn()
        outbox[key] = notification
    send_fn(notification)
    return notification, True


def real_email_content(result: dict, profile: dict) -> tuple[str, str] | None:
    """Subject and text for the one real email (the first real delivery's message)."""
    real = next((d for d in result["plan"]["deliveries"] if d["real"]), None)
    if real is None:
        return None
    pkg = result["notification"]
    recipient = next(r for r in pkg["package"]["recipients"] if r["employee_id"] == real["recipient_id"])
    message = next(m for m in pkg["package"]["messages"] if m["id"] == recipient["message_id"])
    what = ("Shelter in place" if pkg["standing_policy"] == STANDING_POLICY
            else POSTURE_LABEL[result["posture"]].capitalize())
    subject = f"[ClosureIQ demo] {profile['name']}: {what}"
    text = (f"{message['text']}\n\n---\nClosureIQ demo: this copy was sent to the demo inbox. "
            f"Intended recipient: {real['recipient_id']} (synthetic). "
            f"Notification {pkg['notification_id']}, evaluation {pkg['evaluation_id']}.")
    return subject, text


def create_notification(evaluation: dict, profile: dict, roster: list[dict], *,
                        posture: str | None, approval_id: str | None, notification_id: str,
                        now_sim: datetime | str, rng: random.Random,
                        next_delivery_id: Callable[[], str], next_timer_id: Callable[[], str],
                        standing_policy: str | None = None, storm: bool = False) -> dict:
    """Pure part: package + delivery plan + timers. No sending.

    Returns {"notification", "plan", "timers", "posture"}.
    """
    final_posture = posture or evaluation["posture"]
    pkg = build_package(evaluation, profile, roster, final_posture, now_sim=now_sim,
                        notification_id=notification_id, approval_id=approval_id,
                        standing_policy=standing_policy)
    plan = plan_deliveries(pkg, start_sim=now_sim, rng=rng, storm=storm, next_id=next_delivery_id)
    timers = [schedule_ack_timer(pkg, pkg["ack_deadline"], now_sim, next_timer_id, profile)]
    if standing_policy == STANDING_POLICY:
        timers = shelter_timers(evaluation, profile, notification_id, now_sim, next_timer_id) + timers
    return {"notification": pkg, "plan": plan, "timers": timers, "posture": final_posture}


def send_real_email(result: dict, profile: dict, send_email_fn: Callable[[str, str], dict],
                    rng: random.Random, storm: bool = False,
                    next_delivery_id: Callable[[], str] | None = None) -> dict:
    """Send the one real email; on failure, fail over in the plan. Returns the sender's result."""
    content = real_email_content(result, profile)
    if content is None:
        return {"ok": False, "mode": "none", "provider_ref": None, "error": "no real email planned"}
    sent = send_email_fn(*content)
    mark_real_result(result["plan"], result["notification"], sent["ok"], rng=rng, storm=storm,
                     next_id=next_delivery_id)
    for d in result["plan"]["deliveries"]:
        if d["real"]:
            d["provider_ref"] = sent.get("provider_ref")
            # Log-only mode sent nothing, so the UI must not label it real.
            d["real"] = sent.get("mode") == "resend"
    result["email"] = sent
    return sent


def notify(key: str, outbox: MutableMapping, evaluation: dict, profile: dict, roster: list[dict],
           *, send_email_fn: Callable[[str, str], dict], **kwargs) -> tuple[dict, bool]:
    """create_notification + send_real_email, exactly once per key."""
    def build():
        return create_notification(evaluation, profile, roster, **kwargs)

    def send(result):
        send_real_email(result, profile, send_email_fn, kwargs["rng"], kwargs.get("storm", False),
                        kwargs.get("next_delivery_id"))
    return notify_once(key, outbox, build, send)
