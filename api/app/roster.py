"""Deterministic synthetic roster used only for the hackathon MVP demo."""
from __future__ import annotations

_GROUPS = [
    "essential", "essential", "essential", "essential",
    "detail_elsewhere", "detail_elsewhere", "detail_elsewhere",
    "onsite_telework_eligible", "onsite_telework_eligible", "onsite_telework_eligible",
    "onsite_not_telework_eligible", "onsite_not_telework_eligible", "onsite_not_telework_eligible",
    "already_teleworking", "already_teleworking", "already_teleworking",
    "on_leave_or_off", "on_leave_or_off",
    "contractor", "contractor",
    "onsite_telework_eligible", "onsite_not_telework_eligible",
    "detail_in", "detail_in", "onsite_telework_eligible",
]
_NAMES = [
    "Alex Morgan", "Jamie Reed", "Taylor Brooks", "Casey Rivera", "Riley Chen",
    "Jordan Patel", "Morgan Davis", "Avery Stone", "Cameron Ellis", "Quinn Bailey",
    "Drew Parker", "Emerson Cole", "Finley James", "Harper Lane", "Peyton Gray",
    "Reese Kelly", "Rowan Diaz", "Skyler Bell", "Dakota Ward", "Sage Turner",
    "Kendall Price", "Logan Murphy", "Elliot Ross", "Charlie Young", "Blake Cooper",
]


def get_roster() -> list[dict]:
    records = []
    for idx, group in enumerate(_GROUPS, start=1):
        essential = group == "essential"
        work_status = {
            "already_teleworking": "telework",
            "on_leave_or_off": "leave" if idx % 2 else "off",
            "detail_elsewhere": "off",
        }.get(group, "onsite")
        assignment = "assigned"
        if group == "detail_elsewhere": assignment = "detail_out"
        if group == "detail_in": assignment = "detail_in"
        if group == "contractor": assignment = "contractor"
        records.append({
            "employee_id": f"e_{idx:03d}",
            "name": _NAMES[idx - 1],
            "group": group,
            "assignment_type": assignment,
            "shift_start": "07:00" if idx in {21, 22} else ("06:00" if idx == 23 else "07:30"),
            "shift_end": "15:30" if idx == 21 else ("18:00" if idx == 22 else "16:00"),
            "work_status_today": work_status,
            "essential": essential,
            "telework_eligible": group not in {"essential", "onsite_not_telework_eligible", "contractor"},
            "commute_county": "Jackson" if idx % 5 == 0 else "Primary service county",
            "channels": ["email", "sms"] if idx % 3 == 0 else ["email"],
            "comm_needs": ["alternate_format"] if idx == 12 else (["language"] if idx == 18 else []),
            "supervisor_id": "e_001" if idx > 3 else None,
        })
    return records
