import json
import random

from api.notify.package import build_package
from api.notify.simulator import (acknowledge, counter_ids, current_status, events_due,
                                  mark_real_result, plan_deliveries, recipient_status,
                                  simulate_responses)

NOW = "2026-10-15T20:31:00-05:00"
LATER = "2026-10-15T21:00:00-05:00"


def make(closure_eval, kc_profile, kc_roster, seed=42, storm=False):
    pkg = build_package(closure_eval, kc_profile, kc_roster, now_sim=NOW)
    return pkg, plan_deliveries(pkg, start_sim=NOW, rng=random.Random(seed), storm=storm)


def test_one_real_email_only(closure_eval, kc_profile, kc_roster):
    _, plan = make(closure_eval, kc_profile, kc_roster)
    real = [d for d in plan["deliveries"] if d["real"]]
    assert len(real) == 1 and real[0]["channel"] == "email"
    assert all(d["channel"] == "email" for d in plan["deliveries"] if d["real"])


def test_statuses_follow_order(closure_eval, kc_profile, kc_roster):
    _, plan = make(closure_eval, kc_profile, kc_roster)
    for d in plan["deliveries"]:
        seq = [e["status"] for e in plan["events"] if e["delivery_id"] == d["delivery_id"]]
        assert seq[:2] == ["queued", "sent"] and seq[2] in ("delivered", "failed")


def test_failover_moves_to_next_channel(closure_eval, kc_profile, kc_roster):
    # storm mode with many seeds guarantees at least one failure
    _, plan = make(closure_eval, kc_profile, kc_roster, seed=7, storm=True)
    status = current_status(plan, LATER)
    failed = [d for d in plan["deliveries"] if status[d["delivery_id"]]["status"] == "failed"]
    assert failed
    for d in failed:
        person = [x for x in plan["deliveries"] if x["recipient_id"] == d["recipient_id"]]
        nxt = [x for x in person if x["attempt"] == d["attempt"] + 1]
        plan_len = next(r for r in build_package(closure_eval, kc_profile, kc_roster, now_sim=NOW)
                        ["package"]["recipients"] if r["employee_id"] == d["recipient_id"])["channel_plan"]
        if d["attempt"] < len(plan_len):
            assert nxt and nxt[0]["channel"] == plan_len[d["attempt"]]
            # the next attempt is queued exactly when the failure happened
            fail_at = next(e["at_sim"] for e in plan["events"]
                           if e["delivery_id"] == d["delivery_id"] and e["status"] == "failed")
            q_at = next(e["at_sim"] for e in plan["events"]
                        if e["delivery_id"] == nxt[0]["delivery_id"] and e["status"] == "queued")
            assert fail_at == q_at


def test_storm_raises_failures(closure_eval, kc_profile, kc_roster):
    def failures(storm):
        total = 0
        for seed in range(30):
            _, plan = make(closure_eval, kc_profile, kc_roster, seed=seed, storm=storm)
            total += sum(1 for e in plan["events"] if e["status"] == "failed")
        return total
    assert failures(True) > failures(False) * 2


def test_real_email_failure_fails_over(closure_eval, kc_profile, kc_roster):
    pkg, plan = make(closure_eval, kc_profile, kc_roster)
    real = next(d for d in plan["deliveries"] if d["real"])
    mark_real_result(plan, pkg, ok=False, rng=random.Random(1))
    status = current_status(plan, LATER)
    assert status[real["delivery_id"]]["status"] == "failed"
    nxt = [d for d in plan["deliveries"] if d["recipient_id"] == real["recipient_id"] and d["attempt"] == 2]
    assert nxt and nxt[0]["channel"] == "sms" and nxt[0]["real"] is False


def test_fast_forward_in_order(closure_eval, kc_profile, kc_roster):
    _, plan = make(closure_eval, kc_profile, kc_roster)
    assert events_due(plan, "2026-10-15T20:30:59-05:00") == []
    due = events_due(plan, LATER)
    assert due == plan["events"]
    times = [e["at_sim"] for e in due]
    assert times == sorted(times)


def test_ack_and_simulate_responses(closure_eval, kc_profile, kc_roster):
    _, plan = make(closure_eval, kc_profile, kc_roster)
    first = plan["deliveries"][0]["delivery_id"]
    assert acknowledge(plan, first, LATER)["status"] == "acknowledged"
    assert acknowledge(plan, first, LATER) is None  # second ack is a no-op
    new = simulate_responses(plan, LATER, random.Random(3), fraction=0.8)
    people = recipient_status(plan, LATER)
    acked = sum(1 for s in people.values() if s == "acknowledged")
    assert acked == len(new) + 1 and acked >= len(people) // 2


def test_identical_seed_identical_output(closure_eval, kc_profile, kc_roster):
    _, a = make(closure_eval, kc_profile, kc_roster, seed=9, storm=True)
    _, b = make(closure_eval, kc_profile, kc_roster, seed=9, storm=True)
    assert json.dumps(a) == json.dumps(b)
    _, c = make(closure_eval, kc_profile, kc_roster, seed=10, storm=True)
    assert json.dumps(a) != json.dumps(c)


def test_ids_come_from_injected_generator(closure_eval, kc_profile, kc_roster):
    pkg = build_package(closure_eval, kc_profile, kc_roster, now_sim=NOW)
    plan = plan_deliveries(pkg, start_sim=NOW, rng=random.Random(1), next_id=counter_ids("x"))
    assert plan["deliveries"][0]["delivery_id"] == "x_0001"
