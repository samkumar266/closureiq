"""Shelter-in-place standing policy: the only notice sent without approval.

Allowed only for a Tornado Warning or any Warning with onset within the next
30 minutes. An engine safety_instruction alone does not send. The record shows
approval_id = null and standing_policy = "shelter_in_place", and the approver
is told straight away.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from api.clock import parse_iso
from api.notify.escalation import make_timer
from api.notify.package import build_package

STANDING_POLICY = "shelter_in_place"
IMMINENT_ONSET_MINUTES = 30


def _alert_inputs(evaluation: dict) -> list[dict]:
    return [i for i in evaluation.get("inputs", []) if "alert" in str(i.get("source", "")).lower()]


def _active_or_imminent(alert: dict, now: datetime) -> bool:
    onset = alert.get("onset")
    ends = alert.get("ends")
    if ends and parse_iso(ends) <= now:
        return False
    return onset is None or parse_iso(onset) <= now + timedelta(minutes=IMMINENT_ONSET_MINUTES)


def _event_names(alert_input: dict) -> list[str]:
    """Alert event names: the input label, plus each alert's `event` when the
    live input's value is a list of alerts."""
    names = [str(alert_input.get("label", ""))]
    value = alert_input.get("value")
    if isinstance(value, list):
        names += [str(a.get("event", "")) for a in value if isinstance(a, dict)]
    return names


def should_auto_send(evaluation: dict, now_sim: datetime | str) -> bool:
    """True when the shelter-in-place standing policy applies (architecture doc):
    a Tornado Warning that is active or imminent, or any Warning whose onset is
    within the next 30 minutes.

    A safety_instruction alone never sends: the engine also adds "Shelter in
    place" for warnings that are already under way (a flash flood, for example),
    and those wait for a person like every other posture.
    """
    if evaluation.get("hypothetical"):
        return False  # a what-if can never send anything
    now = parse_iso(now_sim)
    for alert in _alert_inputs(evaluation):
        names = _event_names(alert)
        if not _active_or_imminent(alert, now):
            continue
        if any(n.startswith("Tornado Warning") for n in names):
            return True
        if not any(n.endswith("Warning") for n in names):
            continue
        onset = alert.get("onset")
        if onset and now <= parse_iso(onset) <= now + timedelta(minutes=IMMINENT_ONSET_MINUTES):
            return True
    return False


def build_shelter_package(evaluation: dict, profile: dict, roster: list[dict], *,
                          now_sim: datetime | str, notification_id: str | None) -> dict:
    """Fixed short message to everyone on site, no approval."""
    return build_package(evaluation, profile, roster, now_sim=now_sim,
                         notification_id=notification_id, approval_id=None,
                         standing_policy=STANDING_POLICY)


def shelter_timers(evaluation: dict, profile: dict, notification_id: str | None,
                   now_sim: datetime | str, next_id: Callable[[], str]) -> list[dict]:
    """Tell the approver immediately (due now)."""
    now = parse_iso(now_sim)
    payload = {"evaluation_id": evaluation["evaluation_id"], "notification_id": notification_id,
               "facility_id": profile["facility_id"], "manager_id": profile["manager_id"],
               "backup_manager_id": profile["backup_manager_id"]}
    return [make_timer(next_id(), "shelter_notify_approver", now, payload, now)]
