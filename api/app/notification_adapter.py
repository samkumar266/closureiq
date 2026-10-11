"""Minimal simulated notification package builder for API integration tests.

Suraj's `api/notify` module can replace this adapter. No email/SMS is sent by this starter.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from api.app.roster import get_roster

POSTURES = {"normal_operations", "delayed_arrival", "early_dismissal", "unscheduled_leave_or_telework", "closure"}


def build_package(evaluation: dict, posture: str | None = None) -> dict:
    final_posture = posture or evaluation.get("posture", "normal_operations")
    params = evaluation.get("parameters") or {}
    next_update = params.get("next_update")
    effective = {
        "normal_operations": "Normal operations; continue monitoring official alerts.",
        "delayed_arrival": f"Delayed arrival. Follow the revised arrival time: {params.get('delay_until') or 'see next update'}.",
        "early_dismissal": f"Early dismissal. Follow the stated dismissal time: {params.get('dismiss_at') or 'see next update'}.",
        "unscheduled_leave_or_telework": "Follow supervisor guidance for telework or leave; do not assume normal operations.",
        "closure": f"Facility closure from {params.get('closed_from') or 'the stated effective time'} until {params.get('closed_until') or 'further notice'}.",
    }.get(final_posture, "Follow the approved facility status and watch for the next update.")
    recipients = []
    included_rows = []
    for employee in get_roster():
        group = employee["group"]
        include = True
        reason = "Assigned onsite today; status may affect this employee"
        if group == "already_teleworking" and final_posture in {"delayed_arrival", "early_dismissal", "unscheduled_leave_or_telework"}:
            include = False
            reason = "Already teleworking; no change to work arrangement"
        elif group in {"detail_elsewhere", "on_leave_or_off"}:
            include = False
            reason = "Not assigned onsite at this facility today"
        elif group == "contractor":
            reason = "Site status only; work status goes through the contract lead"
        elif group == "essential":
            reason = "Essential staff reporting requirements stay unchanged; review safe-travel instruction"
        elif group == "detail_in":
            reason = "Detailed in from another office; treated as assigned onsite"
        recipient = {
            "employee_id": employee["employee_id"], "included": include,
            "group": group, "reason": reason,
        }
        if include:
            message_id = f"m_{group}"
            recipient["message_id"] = message_id
            recipient["channel_plan"] = employee["channels"]
            included_rows.append((employee, message_id))
        recipients.append(recipient)
    messages_by_group: dict[str, dict] = {}
    for employee, message_id in included_rows:
        group = employee["group"]
        if message_id not in messages_by_group:
            messages_by_group[message_id] = {
                "id": message_id, "group": group,
                "text": (f"ClosureIQ status: {final_posture.replace('_', ' ')}. {effective} "
                         f"Next update: {next_update or 'when new information is available'}. "
                         "Acknowledge receipt in the app. If no update arrives, do not treat silence as an all-clear."),
            }
    return {"recipients": recipients, "messages": list(messages_by_group.values())}


def preview_response(evaluation: dict, posture: str | None = None) -> dict:
    package = build_package(evaluation, posture)
    return {
        "notification_id": None,
        "evaluation_id": evaluation["evaluation_id"],
        "approval_id": None,
        "standing_policy": None,
        "preview": True,
        "ack_deadline": evaluation.get("decision_deadline"),
        "next_update": (evaluation.get("parameters") or {}).get("next_update"),
        "package": package,
        "deliveries": [],
        "escalation": [],
    }
