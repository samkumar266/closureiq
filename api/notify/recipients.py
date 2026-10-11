"""Who is in or out of a notification, and why.

Follows the "Who is told what" table in docs/architecture.md. Pure function:
roster rows in (contract shape, see mocks/seed/), recipient items out.
"""
from __future__ import annotations

POSTURES = ("normal_operations", "delayed_arrival", "early_dismissal",
            "unscheduled_leave_or_telework", "closure")

POSTURE_LABEL = {
    "normal_operations": "normal operations",
    "delayed_arrival": "delayed arrival",
    "early_dismissal": "early dismissal",
    "unscheduled_leave_or_telework": "unscheduled leave or telework",
    "closure": "closure",
}

# Groups that are physically on site today (used by shelter in place).
ON_SITE_GROUPS = {"essential", "onsite_telework_eligible",
                  "onsite_not_telework_eligible", "contractor"}


def channel_plan(employee: dict) -> list[str]:
    """Channel types in the order to try. voice_call_first moves voice to the front."""
    plan = [c["type"] for c in employee.get("channels", [])]
    if "voice_call_first" in (employee.get("comm_needs") or []) and "voice" in plan:
        plan.remove("voice")
        plan.insert(0, "voice")
    return plan


def _decide(group: str, posture: str) -> tuple[bool, str]:
    """(included, reason) for one group under one posture."""
    label = POSTURE_LABEL[posture]
    if group == "detail_elsewhere":
        return False, "On detail at another office today; not assigned to this site"
    if group == "on_leave_or_off":
        return False, "On leave or off today; no action needed"
    if posture == "normal_operations":
        return False, "Normal operations; no change to work arrangement"
    if group == "essential":
        return True, f"Essential staff; reporting is unchanged during {label}"
    if group == "onsite_telework_eligible":
        return True, f"Assigned onsite today and telework-eligible; posture is {label}"
    if group == "onsite_not_telework_eligible":
        return True, f"Assigned onsite today and not telework-eligible; posture is {label}"
    if group == "already_teleworking":
        if posture == "closure":
            return True, "Already teleworking; informational closure notice only"
        return False, "Already teleworking; no change to work arrangement"
    if group == "contractor":
        return True, "Contractor; told the site status, work status goes through the contract lead"
    return False, f"Unknown group '{group}'; excluded, check the roster"


def _shelter_decide(group: str) -> tuple[bool, str]:
    if group in ON_SITE_GROUPS:
        return True, "On site today; shelter-in-place standing policy applies"
    return False, "Not on site today; shelter-in-place notice is for people on site"


def select_recipients(roster: list[dict], posture: str,
                      shelter_in_place: bool = False) -> list[dict]:
    """One item per employee, in roster order.

    Included items: employee_id, included, group, reason, channel_plan.
    (package.py adds message_id.) Excluded items: employee_id, included, group, reason.
    """
    if posture not in POSTURES:
        raise ValueError(f"invalid posture: {posture}")
    items = []
    for employee in roster:
        group = employee["group"]
        included, reason = _shelter_decide(group) if shelter_in_place else _decide(group, posture)
        item = {"employee_id": employee["employee_id"], "included": included,
                "group": group, "reason": reason}
        if included:
            item["channel_plan"] = channel_plan(employee)
        items.append(item)
    return items
