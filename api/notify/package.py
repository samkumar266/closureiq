"""Build the notification package JSON exactly as docs/contract.md shows it.

Pure function: evaluation + facility profile + roster + sim time in, dict out.
The preview version has preview=True and null notification/approval ids.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api.clock import parse_iso
from api.notify.recipients import select_recipients
from api.notify.templates import render_message, render_shelter, variant_for

ACK_WINDOW_MIN = 20          # employees have 20 min to acknowledge ...
ACK_BEFORE_DEPARTURE_MIN = 10  # ... or until 10 min before they leave home
POSTURE_PARAM_KEYS = {
    "delayed_arrival": ["delay_until"], "early_dismissal": ["dismiss_at"],
    "closure": ["closed_from", "closed_until"], "unscheduled_leave_or_telework": [],
    "normal_operations": [],
}


def local_iso(value: datetime | str | None, tz_name: str) -> str | None:
    if value is None:
        return None
    return parse_iso(value).astimezone(ZoneInfo(tz_name)).isoformat()


def _effective_date(parameters: dict, now_sim: datetime, tz: ZoneInfo):
    for key in ("closed_from", "delay_until", "dismiss_at"):
        if parameters.get(key):
            return parse_iso(parameters[key]).astimezone(tz).date()
    return now_sim.astimezone(tz).date()


def earliest_departure(included_ids: set[str], roster: list[dict], profile: dict,
                       posture: str, parameters: dict, now_sim: datetime) -> datetime | None:
    """When the first included person leaves home (or the building, for early dismissal)."""
    tz = ZoneInfo(profile["location"]["timezone"])
    if posture == "early_dismissal" and parameters.get("dismiss_at"):
        return parse_iso(parameters["dismiss_at"])
    day = _effective_date(parameters, now_sim, tz)
    starts = [e["shift_start"] for e in roster if e["employee_id"] in included_ids and e.get("shift_start")]
    if not starts:
        return None
    hh, mm = map(int, min(starts).split(":"))
    shift = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
    return shift - timedelta(minutes=int(profile.get("commute_buffer_min", 0)))


def ack_deadline(now_sim: datetime, departure: datetime | None) -> datetime:
    """min(send + 20 min, departure - 10 min); never earlier than now."""
    by_window = now_sim + timedelta(minutes=ACK_WINDOW_MIN)
    if departure is None:
        return by_window
    by_departure = departure - timedelta(minutes=ACK_BEFORE_DEPARTURE_MIN)
    if by_departure <= now_sim:
        return by_window
    return min(by_window, by_departure)


def fill_closure_hours(posture: str, parameters: dict, profile: dict,
                       now_sim: datetime) -> tuple[dict, list[str]]:
    """An override to closure has no closed_from/closed_until from the engine.
    Fill them from the facility's open and close hours for the next operating day
    (today if it has not closed yet). Returns (parameters, keys_filled)."""
    if posture != "closure":
        return parameters, []
    missing = [k for k in ("closed_from", "closed_until") if not parameters.get(k)]
    if not missing or not profile.get("hours"):
        return parameters, []
    tz = ZoneInfo(profile["location"]["timezone"])
    local_now = now_sim.astimezone(tz)

    def at(day, hhmm):
        hh, mm = map(int, hhmm.split(":"))
        return datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
    day = local_now.date()
    if local_now >= at(day, profile["hours"]["close"]):
        day = day + timedelta(days=1)
    filled = dict(parameters)
    defaults = {"closed_from": at(day, profile["hours"]["open"]),
                "closed_until": at(day, profile["hours"]["close"])}
    for key in missing:
        filled[key] = defaults[key].isoformat()
    return filled, missing


def _attach_messages(recipients: list[dict], roster_by_id: dict, render) -> tuple[list, list]:
    """One message per (group, variant) actually used. Returns (messages, warnings)."""
    messages, warnings, ids = [], [], {}
    for item in recipients:
        if not item["included"]:
            continue
        variant = variant_for(roster_by_id[item["employee_id"]].get("comm_needs"))
        key = (item["group"], variant)
        if key not in ids:
            rendered = render(item["group"], variant)
            ids[key] = f"m_{len(messages) + 1}"
            messages.append({"id": ids[key], "group": item["group"], "text": rendered["text"],
                             "variant": rendered["variant"],
                             "needs_translation": rendered["needs_translation"]})
            if rendered["needs_translation"]:
                warnings.append({"type": "needs_translation", "message_id": ids[key],
                                 "group": item["group"], "variant": variant, "employee_ids": [],
                                 "text": f"No {variant} template for {item['group']}; "
                                         "English shown. Needs translation before sending."})
        item["message_id"] = ids[key]
        for w in warnings:
            if w["message_id"] == ids[key]:
                w["employee_ids"].append(item["employee_id"])
    return messages, warnings


def _order_keys(item: dict) -> dict:
    """Contract key order: included items carry message_id then channel_plan."""
    out = {k: item[k] for k in ("employee_id", "included", "group", "reason")}
    if item["included"]:
        out["message_id"] = item["message_id"]
        out["channel_plan"] = item["channel_plan"]
    return out


def build_package(evaluation: dict, profile: dict, roster: list[dict], posture: str | None = None,
                  *, now_sim: datetime | str, notification_id: str | None = None,
                  approval_id: str | None = None, standing_policy: str | None = None,
                  preview: bool = False) -> dict:
    """Full notification object (contract shape) with empty deliveries and escalation."""
    now_sim = parse_iso(now_sim)
    tz_name = profile["location"]["timezone"]
    final_posture = posture or evaluation["posture"]
    parameters = evaluation.get("parameters") or {}
    shelter = standing_policy == "shelter_in_place"
    parameters, filled = ([parameters, []] if shelter
                          else fill_closure_hours(final_posture, parameters, profile, now_sim))
    roster_by_id = {e["employee_id"]: e for e in roster}

    recipients = select_recipients(roster, final_posture, shelter_in_place=shelter)
    if shelter:
        render = lambda group, variant: render_shelter(profile["name"], variant)
    else:
        render = lambda group, variant: render_message(group, final_posture, parameters,
                                                       profile["name"], tz_name, variant)
    messages, warnings = _attach_messages(recipients, roster_by_id, render)
    if filled:
        warnings.append({"type": "derived_parameters", "message_id": None, "group": None,
                         "variant": None, "employee_ids": [],
                         "text": f"{', '.join(filled)} not set by the engine for {final_posture}; "
                                 "taken from the facility's open and close hours. Check before sending."})
    missing = [k for k in POSTURE_PARAM_KEYS[final_posture] if not parameters.get(k)]
    if missing and not shelter:
        warnings.append({"type": "missing_parameters", "message_id": None, "group": None,
                         "variant": None, "employee_ids": [],
                         "text": f"Posture {final_posture} has no {', '.join(missing)} from the engine; "
                                 "messages say 'not set yet'. Set the time before sending."})

    included_ids = {r["employee_id"] for r in recipients if r["included"]}
    departure = earliest_departure(included_ids, roster, profile, final_posture, parameters, now_sim)
    return {
        "notification_id": None if preview else notification_id,
        "evaluation_id": evaluation["evaluation_id"],
        "approval_id": None if preview else approval_id,
        "standing_policy": standing_policy,
        "preview": preview,
        "ack_deadline": local_iso(ack_deadline(now_sim, departure), tz_name),
        "next_update": local_iso(parameters.get("next_update"), tz_name),
        "package": {"recipients": [_order_keys(r) for r in recipients],
                    "messages": messages, "warnings": warnings},
        "deliveries": [],
        "escalation": [],
    }


def build_preview(evaluation: dict, profile: dict, roster: list[dict], posture: str | None = None,
                  *, now_sim: datetime | str) -> dict:
    """GET /api/evaluations/{id}/package-preview body."""
    return build_package(evaluation, profile, roster, posture, now_sim=now_sim, preview=True)
