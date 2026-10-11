"""Delivery simulator.

Each delivery moves queued -> sent -> delivered or failed, then acknowledged.
Every channel has its own delay and failure rate; storm mode raises failure
rates. A failed message moves to the next channel in that person's list
(unacknowledged is not the same as unreachable).

Deterministic: the seeded random.Random is passed in, and all status changes
are planned up front as events with a sim time. Fast-forward = apply every
event with at_sim <= now, in order.

Only email is real, and only one email per notification (the first included
person's), redirected to DEMO_EMAIL_TO by email_sender.py.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Callable

from api.clock import parse_iso

# seconds from queued to sent, seconds from sent to delivered/failed, failure rate
CHANNELS = {
    "email": {"send_s": 2, "deliver_s": (5, 30), "fail_rate": 0.03},
    "sms": {"send_s": 1, "deliver_s": (3, 15), "fail_rate": 0.08},
    "push": {"send_s": 1, "deliver_s": (1, 5), "fail_rate": 0.15},
    "voice": {"send_s": 5, "deliver_s": (20, 60), "fail_rate": 0.10},
}
STORM_MULTIPLIER = 4
MAX_FAIL_RATE = 0.9
STATUS_ORDER = {"queued": 0, "sent": 1, "delivered": 2, "failed": 2, "acknowledged": 3}


def fail_rate(channel: str, storm: bool) -> float:
    base = CHANNELS[channel]["fail_rate"]
    return min(MAX_FAIL_RATE, base * STORM_MULTIPLIER) if storm else base


def counter_ids(prefix: str = "dlv") -> Callable[[], str]:
    """Local id generator for tests. In the app, pass the store's id generator."""
    n = {"i": 0}

    def next_id() -> str:
        n["i"] += 1
        return f"{prefix}_{n['i']:04d}"
    return next_id


def _ev(at: datetime, delivery_id: str, status: str) -> dict:
    return {"at_sim": at.isoformat(), "delivery_id": delivery_id, "status": status}


def _plan_attempt(recipient_id: str, channels: list[str], index: int, start: datetime,
                  rng: random.Random, storm: bool, next_id, real_email: bool,
                  deliveries: list, events: list) -> None:
    """Plan one attempt on channels[index]; on failure, plan the next channel."""
    channel = channels[index]
    spec = CHANNELS.get(channel, CHANNELS["sms"])
    delivery_id = next_id()
    real = real_email and channel == "email"
    deliveries.append({"delivery_id": delivery_id, "recipient_id": recipient_id,
                       "channel": channel, "real": real, "attempt": index + 1})
    sent_at = start + timedelta(seconds=spec["send_s"])
    done_at = sent_at + timedelta(seconds=rng.randint(*spec["deliver_s"]))
    # The real email's outcome comes from the provider (see mark_real_result).
    failed = (not real) and rng.random() < fail_rate(channel, storm)
    events.append(_ev(start, delivery_id, "queued"))
    events.append(_ev(sent_at, delivery_id, "sent"))
    events.append(_ev(done_at, delivery_id, "failed" if failed else "delivered"))
    if failed and index + 1 < len(channels):
        _plan_attempt(recipient_id, channels, index + 1, done_at, rng, storm, next_id,
                      False, deliveries, events)


def _sort(events: list[dict]) -> list[dict]:
    return sorted(events, key=lambda e: (parse_iso(e["at_sim"]), e["delivery_id"],
                                         STATUS_ORDER[e["status"]]))


def plan_deliveries(package: dict, *, start_sim: datetime | str, rng: random.Random,
                    storm: bool = False, next_id: Callable[[], str] | None = None) -> dict:
    """Plan every delivery for a notification.

    Returns {"deliveries": [...], "events": [...]} where each delivery is
    {delivery_id, recipient_id, channel, real, attempt} and each event is
    {at_sim, delivery_id, status}, sorted by time.
    """
    start = parse_iso(start_sim)
    next_id = next_id or counter_ids()
    deliveries, events = [], []
    real_used = False
    for r in package["package"]["recipients"]:
        if not r["included"] or not r["channel_plan"]:
            continue
        real_email = not real_used and "email" in r["channel_plan"]
        real_used = real_used or real_email
        _plan_attempt(r["employee_id"], r["channel_plan"], 0, start, rng, storm, next_id,
                      real_email, deliveries, events)
    return {"deliveries": deliveries, "events": _sort(events)}


def mark_real_result(plan: dict, package: dict, ok: bool, *, rng: random.Random,
                     storm: bool = False, next_id: Callable[[], str] | None = None) -> dict:
    """Apply the real email provider's answer. On failure, fail over to the next channel."""
    real = next((d for d in plan["deliveries"] if d["real"]), None)
    if real is None or ok:
        return plan
    final = next(e for e in plan["events"] if e["delivery_id"] == real["delivery_id"]
                 and e["status"] == "delivered")
    final["status"] = "failed"
    channels = next((r["channel_plan"] for r in package["package"]["recipients"]
                     if r["employee_id"] == real["recipient_id"]), [])
    if real["channel"] in channels:
        index = channels.index(real["channel"]) + 1
        if index < len(channels):
            _plan_attempt(real["recipient_id"], channels, index, parse_iso(final["at_sim"]), rng,
                          storm, next_id or counter_ids("dlv_r"), False,
                          plan["deliveries"], plan["events"])
    plan["events"] = _sort(plan["events"])
    return plan


def events_due(plan: dict, now_sim: datetime | str, after_sim: datetime | str | None = None) -> list[dict]:
    """Events with after_sim < at_sim <= now_sim, in order. Use for fast-forward."""
    now = parse_iso(now_sim)
    after = parse_iso(after_sim) if after_sim else None
    return [e for e in plan["events"]
            if parse_iso(e["at_sim"]) <= now and (after is None or parse_iso(e["at_sim"]) > after)]


def current_status(plan: dict, now_sim: datetime | str) -> dict[str, dict]:
    """delivery_id -> {status, at_sim} as of now_sim. Deliveries not yet queued are left out."""
    out: dict[str, dict] = {}
    for e in events_due(plan, now_sim):
        out[e["delivery_id"]] = {"status": e["status"], "at_sim": e["at_sim"]}
    return out


def recipient_status(plan: dict, now_sim: datetime | str) -> dict[str, str]:
    """recipient_id -> acknowledged, delivered, unreachable or pending."""
    status = current_status(plan, now_sim)
    by_person: dict[str, list[str]] = {}
    for d in plan["deliveries"]:
        by_person.setdefault(d["recipient_id"], []).append(d["delivery_id"])
    out = {}
    for person, ids in by_person.items():
        states = [status[i]["status"] for i in ids if i in status]
        planned = len(ids)
        if "acknowledged" in states:
            out[person] = "acknowledged"
        elif "delivered" in states:
            out[person] = "delivered"
        elif len(states) == planned and states and all(s == "failed" for s in states):
            out[person] = "unreachable"
        else:
            out[person] = "pending"
    return out


def acknowledge(plan: dict, delivery_id: str, at_sim: datetime | str) -> dict | None:
    """Presenter acknowledges one delivery. Returns the new event, or None if already acknowledged."""
    if any(e["delivery_id"] == delivery_id and e["status"] == "acknowledged" for e in plan["events"]):
        return None
    event = _ev(parse_iso(at_sim), delivery_id, "acknowledged")
    plan["events"] = _sort(plan["events"] + [event])
    return event


def simulate_responses(plan: dict, now_sim: datetime | str, rng: random.Random,
                       fraction: float = 0.8) -> list[dict]:
    """'Simulate responses' button: acknowledge most delivered people, deterministically."""
    status = current_status(plan, now_sim)
    acked_people = {d["recipient_id"] for d in plan["deliveries"]
                    if status.get(d["delivery_id"], {}).get("status") == "acknowledged"}
    new = []
    for d in plan["deliveries"]:
        if d["recipient_id"] in acked_people:
            continue
        if status.get(d["delivery_id"], {}).get("status") != "delivered":
            continue
        if rng.random() < fraction:
            event = acknowledge(plan, d["delivery_id"], now_sim)
            if event:
                new.append(event)
                acked_people.add(d["recipient_id"])
    return new
