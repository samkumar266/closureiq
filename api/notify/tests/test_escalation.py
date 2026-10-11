import json
import random
from datetime import timedelta

from api.clock import parse_iso
from api.notify.escalation import (cancel_on_decision, escalation_view, fire_due, next_due,
                                   schedule_ack_timer, schedule_approval_timers, window_w)
from api.notify.package import build_package
from api.notify.simulator import counter_ids, plan_deliveries, recipient_status, simulate_responses

DEADLINE = "2026-10-16T04:45:00-05:00"


def test_window_is_quarter_clamped():
    assert window_w(DEADLINE, "2026-10-16T03:45:00-05:00") == timedelta(minutes=15)
    assert window_w(DEADLINE, "2026-10-15T20:00:00-05:00") == timedelta(minutes=30)  # held at 30
    assert window_w(DEADLINE, "2026-10-16T04:35:00-05:00") == timedelta(minutes=5)   # held at 5
    assert window_w(DEADLINE, "2026-10-16T05:00:00-05:00") == timedelta(minutes=5)   # past deadline


def test_manager_silent_then_backup_then_unresolved_in_order(closure_eval, kc_profile):
    ids = counter_ids("tmr")
    timers = schedule_approval_timers(closure_eval, kc_profile, "2026-10-16T03:45:00-05:00", ids)
    assert [t["kind"] for t in timers] == ["manager_no_response_to_backup"]
    assert timers[0]["due_at_sim"] == "2026-10-16T04:00:00-05:00"  # W = 15
    # One 30-minute jump fires both: backup at 04:00, then UNRESOLVED at 04:00 + W(04:00)=04:11:15
    fired, created, actions = fire_due(timers, "2026-10-16T04:15:00-05:00",
                                       {"evaluation": closure_eval}, ids)
    assert [a["kind"] for a in actions] == ["manager_no_response_to_backup", "backup_silent_unresolved"]
    assert actions[0]["notify"] == ["e_002"]
    assert actions[1]["notify"] == ["e_003"] and actions[1]["mark_unresolved"] is True
    assert created[0]["due_at_sim"] == "2026-10-16T04:11:15-05:00"
    times = [parse_iso(a["at_sim"]) for a in actions]
    assert times == sorted(times)
    # nothing fires twice
    assert fire_due(timers, "2026-10-16T05:00:00-05:00", {"evaluation": closure_eval}, ids)[2] == []


def test_one_big_jump_equals_small_jumps(closure_eval, kc_profile):
    def run(steps):
        ids = counter_ids("tmr")
        timers = schedule_approval_timers(closure_eval, kc_profile, "2026-10-16T03:45:00-05:00", ids)
        actions = []
        for now in steps:
            actions += fire_due(timers, now, {"evaluation": closure_eval}, ids)[2]
        return json.dumps(actions), json.dumps(timers)
    big = run(["2026-10-16T04:30:00-05:00"])
    small = run(["2026-10-16T04:01:00-05:00", "2026-10-16T04:12:00-05:00", "2026-10-16T04:30:00-05:00"])
    assert big == small


def test_urgent_notifies_primary_and_backup_at_once(closure_eval, kc_profile):
    ids = counter_ids("tmr")
    now = "2026-10-16T04:25:00-05:00"  # 20 min to the deadline
    timers = schedule_approval_timers(closure_eval, kc_profile, now, ids)
    assert timers[0]["kind"] == "urgent_primary_and_backup" and timers[0]["due_at_sim"] == parse_iso(now).isoformat()
    actions = fire_due(timers, now, {"evaluation": closure_eval}, ids)[2]
    assert actions[0]["notify"] == ["e_001", "e_002"]


def test_shelter_is_urgent_even_far_from_deadline(closure_eval, kc_profile):
    timers = schedule_approval_timers(closure_eval, kc_profile, "2026-10-15T20:31:00-05:00",
                                      counter_ids("tmr"), shelter_in_place=True)
    assert timers[0]["kind"] == "urgent_primary_and_backup"


def test_decision_cancels_approval_chain(closure_eval, kc_profile):
    ids = counter_ids("tmr")
    timers = schedule_approval_timers(closure_eval, kc_profile, "2026-10-16T03:45:00-05:00", ids)
    changed = cancel_on_decision(timers, closure_eval["evaluation_id"], "2026-10-16T03:50:00-05:00")
    assert len(changed) == 1
    assert fire_due(timers, "2026-10-16T05:00:00-05:00", {"evaluation": closure_eval}, ids)[2] == []
    assert escalation_view(timers, "America/Chicago") == []


def test_no_deadline_no_approval_timers(closure_eval, kc_profile):
    ev = dict(closure_eval, decision_deadline=None)
    assert schedule_approval_timers(ev, kc_profile, "2026-10-16T03:45:00-05:00", counter_ids()) == []


def test_unacknowledged_fast_forward_lists_people_by_supervisor(closure_eval, kc_profile, kc_roster):
    now = "2026-10-15T20:31:00-05:00"
    pkg = build_package(closure_eval, kc_profile, kc_roster, now_sim=now,
                        notification_id="ntf_0001", approval_id="apr_0001")
    plan = plan_deliveries(pkg, start_sim=now, rng=random.Random(42))
    simulate_responses(plan, "2026-10-15T20:35:00-05:00", random.Random(5), fraction=0.7)
    ids = counter_ids("tmr")
    timers = [schedule_ack_timer(pkg, pkg["ack_deadline"], now, ids, kc_profile)]
    view = escalation_view(timers, "America/Chicago")
    assert list(view[0]) == ["step", "label", "due_sim", "fired_at_sim"]
    assert view[0]["fired_at_sim"] is None and view[0]["due_sim"] == "2026-10-15T20:51:00-05:00"
    ctx = {"evaluation": closure_eval, "roster": kc_roster,
           "recipient_status_at": lambda at: recipient_status(plan, at)}
    fired, _, actions = fire_due(timers, "2026-10-15T21:01:00-05:00", ctx, ids)  # jump +30
    unacked = actions[0]["unacknowledged_by_supervisor"]
    statuses = recipient_status(plan, "2026-10-15T20:51:00-05:00")
    expected = sorted(p for p, s in statuses.items() if s != "acknowledged")
    assert sorted(x["employee_id"] for rows in unacked.values() for x in rows) == expected
    assert expected  # someone was left unacknowledged
    assert "e_001" in actions[0]["notify"]
    assert escalation_view(timers, "America/Chicago")[0]["fired_at_sim"] == "2026-10-15T20:51:00-05:00"
    assert next_due(timers) is None
