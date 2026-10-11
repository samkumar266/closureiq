"""Escalation timers (architecture doc, Escalation table).

Timers are plain rows shaped like Badri's `timers` table:
{id, kind, due_at_sim, payload, fired_at_sim, cancelled_at_sim, created_at_sim}.
Due times are on the simulated clock. fire_due() fires every timer with
due_at_sim <= now in (due, id) order; a fired timer may add a follow-up timer,
which also fires in the same call if it is already due. Follow-ups are timed
from the parent's due time, so one big jump and many small jumps give the
same result.

Rules:
- Employees not acknowledged: min(20 min after send, departure - 10 min)
  -> manager and supervisors get each person's contact status.
- Manager not responding: W = (deadline - now) / 4, held to 5..30 min
  -> notify the backup manager.
- Urgent (shelter in place, tornado, or under 30 min to deadline): no window
  -> primary and backup at the same time.
- Backup silent: one more window W -> mark UNRESOLVED, notify the on-call.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from api.clock import parse_iso

W_MIN_MINUTES = 5
W_MAX_MINUTES = 30
URGENT_DEADLINE_MINUTES = 30

LABELS = {
    "manager_no_response_to_backup": "Backup manager notified: no decision from the manager",
    "urgent_primary_and_backup": "Urgent: primary and backup managers notified at the same time",
    "backup_silent_unresolved": "Backup silent: marked UNRESOLVED and on-call notified",
    "unacknowledged_to_supervisors": "Supervisors told who has not acknowledged",
    "shelter_notify_approver": "Approver told a shelter-in-place notice went out",
}
DELIVERY_KIND = "delivery_status"  # planned delivery status change (see simulator.delivery_timer_rows)
APPROVAL_KINDS = {"manager_no_response_to_backup", "urgent_primary_and_backup",
                  "backup_silent_unresolved"}


def window_w(deadline: datetime | str, now: datetime | str) -> timedelta:
    """W = (deadline - now) / 4, held between 5 and 30 minutes."""
    quarter = (parse_iso(deadline) - parse_iso(now)) / 4
    return max(timedelta(minutes=W_MIN_MINUTES), min(timedelta(minutes=W_MAX_MINUTES), quarter))


def make_timer(timer_id: str, kind: str, due: datetime, payload: dict, created: datetime) -> dict:
    return {"id": timer_id, "kind": kind, "due_at_sim": due.isoformat(), "payload": payload,
            "fired_at_sim": None, "cancelled_at_sim": None, "created_at_sim": created.isoformat()}


def is_urgent(evaluation: dict, now: datetime | str, shelter_in_place: bool = False) -> bool:
    if shelter_in_place:
        return True
    deadline = evaluation.get("decision_deadline")
    if deadline is None:
        return False
    return parse_iso(deadline) - parse_iso(now) < timedelta(minutes=URGENT_DEADLINE_MINUTES)


def schedule_approval_timers(evaluation: dict, profile: dict, now_sim: datetime | str,
                             next_id: Callable[[], str], shelter_in_place: bool = False) -> list[dict]:
    """Timers that run while a recommendation waits for a decision.

    Returns [] when decision_deadline is null (no decision needed).
    """
    deadline = evaluation.get("decision_deadline")
    if deadline is None:
        return []
    now = parse_iso(now_sim)
    payload = {"evaluation_id": evaluation["evaluation_id"], "facility_id": profile["facility_id"],
               "manager_id": profile["manager_id"], "backup_manager_id": profile["backup_manager_id"],
               "on_call_id": profile["on_call_id"]}
    if is_urgent(evaluation, now, shelter_in_place):
        return [make_timer(next_id(), "urgent_primary_and_backup", now, payload, now),
                make_timer(next_id(), "backup_silent_unresolved", now + window_w(deadline, now),
                           payload, now)]
    return [make_timer(next_id(), "manager_no_response_to_backup", now + window_w(deadline, now),
                       payload, now)]


def schedule_ack_timer(notification: dict, ack_deadline: datetime | str, now_sim: datetime | str,
                       next_id: Callable[[], str], profile: dict) -> dict:
    """The no-acknowledgment timer, due at the package's ack_deadline."""
    payload = {"evaluation_id": notification["evaluation_id"],
               "notification_id": notification["notification_id"],
               "facility_id": profile["facility_id"], "manager_id": profile["manager_id"]}
    return make_timer(next_id(), "unacknowledged_to_supervisors", parse_iso(ack_deadline), payload,
                      parse_iso(now_sim))


def cancel_on_decision(timers: list[dict], evaluation_id: str, now_sim: datetime | str) -> list[dict]:
    """Approve, reject or override stops the manager-response chain. Returns changed rows."""
    changed = []
    for t in timers:
        if (t["kind"] in APPROVAL_KINDS and t["payload"].get("evaluation_id") == evaluation_id
                and t["fired_at_sim"] is None and t["cancelled_at_sim"] is None):
            t["cancelled_at_sim"] = parse_iso(now_sim).isoformat()
            changed.append(t)
    return changed


def _pending(timers: list[dict]) -> list[dict]:
    return [t for t in timers if t["fired_at_sim"] is None and t["cancelled_at_sim"] is None]


def _unacked_action(timer: dict, ctx: dict) -> dict:
    """Group everyone not yet acknowledged by supervisor, with their contact status."""
    statuses = ctx.get("recipient_status_at", lambda at: {})(timer["due_at_sim"])
    supervisors = {e["employee_id"]: e.get("supervisor_id") for e in ctx.get("roster", [])}
    by_supervisor: dict[str, list[dict]] = {}
    for person, status in sorted(statuses.items()):
        if status == "acknowledged":
            continue
        sup = supervisors.get(person) or timer["payload"]["manager_id"]
        by_supervisor.setdefault(sup, []).append({"employee_id": person, "contact_status": status})
    notify = sorted(set(by_supervisor) | {timer["payload"]["manager_id"]}) if by_supervisor else []
    return {"notify": notify, "unacknowledged_by_supervisor": by_supervisor,
            "options": ["resend_next_channel", "call"] if by_supervisor else [],
            "note": None if by_supervisor else "Everyone acknowledged; nothing to escalate"}


def _fire_one(timer: dict, ctx: dict, next_id: Callable[[], str]) -> tuple[dict, list[dict]]:
    """Returns (action, follow_up_timers)."""
    p, kind, due = timer["payload"], timer["kind"], parse_iso(timer["due_at_sim"])
    if kind == DELIVERY_KIND:
        return {"timer_id": timer["id"], "kind": kind, "at_sim": timer["due_at_sim"], **p}, []
    action = {"timer_id": timer["id"], "kind": kind, "label": LABELS[kind],
              "at_sim": timer["due_at_sim"], "simulated": True, "mark_unresolved": False}
    follow = []
    if kind == "manager_no_response_to_backup":
        action["notify"] = [p["backup_manager_id"]]
        deadline = ctx["evaluation"]["decision_deadline"]
        follow.append(make_timer(next_id(), "backup_silent_unresolved", due + window_w(deadline, due),
                                 p, due))
    elif kind == "urgent_primary_and_backup":
        action["notify"] = [p["manager_id"], p["backup_manager_id"]]
    elif kind == "backup_silent_unresolved":
        action["notify"] = [p["on_call_id"]]
        action["mark_unresolved"] = True
    elif kind == "unacknowledged_to_supervisors":
        action.update(_unacked_action(timer, ctx))
    elif kind == "shelter_notify_approver":
        action["notify"] = [p["manager_id"], p["backup_manager_id"]]
    return action, follow


def fire_due(timers: list[dict], now_sim: datetime | str, ctx: dict,
             next_id: Callable[[], str],
             on_fire: Callable[[dict, dict], None] | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """Fire every pending timer due at or before now_sim, in (due, id) order.

    ctx: {"evaluation": dict, "roster": list, "recipient_status_at": callable(at_sim) -> dict}
    Returns (fired_rows, new_rows, actions). Rows in `timers` are updated in place
    (fired_at_sim set once) and new follow-up rows are appended to `timers`.
    on_fire(timer, action), if given, runs right after each firing, before the next
    timer fires, so the app can write delivery statuses in order (an ack timer then
    sees every delivery change that happened before it).
    """
    now = parse_iso(now_sim)
    fired, created, actions = [], [], []
    while True:
        due = sorted((t for t in _pending(timers) if parse_iso(t["due_at_sim"]) <= now),
                     key=lambda t: (parse_iso(t["due_at_sim"]), t["id"]))
        if not due:
            return fired, created, actions
        timer = due[0]
        timer["fired_at_sim"] = timer["due_at_sim"]
        action, follow = _fire_one(timer, ctx, next_id)
        timers.extend(follow)
        fired.append(timer)
        created.extend(follow)
        actions.append(action)
        if on_fire:
            on_fire(timer, action)


def next_due(timers: list[dict]) -> str | None:
    """Next escalation due time (for the escalation.fired SSE event's next_due_sim)."""
    pending = sorted((t for t in _pending(timers) if t["kind"] in LABELS),
                     key=lambda t: parse_iso(t["due_at_sim"]))
    return pending[0]["due_at_sim"] if pending else None


def escalation_view(timers: list[dict], tz_name: str) -> list[dict]:
    """Contract `escalation[]`: {step, label, due_sim, fired_at_sim}. Cancelled timers hidden."""
    tz = ZoneInfo(tz_name)
    rows = sorted((t for t in timers if t["cancelled_at_sim"] is None and t["kind"] in LABELS),
                  key=lambda t: (parse_iso(t["due_at_sim"]), t["id"]))
    local = lambda v: parse_iso(v).astimezone(tz).isoformat() if v else None
    return [{"step": t["kind"], "label": LABELS[t["kind"]], "due_sim": local(t["due_at_sim"]),
             "fired_at_sim": local(t["fired_at_sim"])} for t in rows]
