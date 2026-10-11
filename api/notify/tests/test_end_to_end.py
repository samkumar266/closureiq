"""Demo steps 4 and 5 with an in-memory stand-in for Badri's store."""
import random

from api.clock import parse_iso

from api.notify.escalation import (cancel_on_decision, escalation_view, fire_due,
                                   schedule_approval_timers)
from api.notify.service import idempotency_key, notify
from api.notify.simulator import counter_ids, recipient_status_from_deliveries

TZ = "America/Chicago"
APPROVED_AT = "2026-10-16T03:40:00-05:00"


def test_approve_then_jump_30_fires_everything_in_order(closure_eval, kc_profile, kc_roster):
    timer_ids, delivery_ids = counter_ids("tmr"), counter_ids("dlv")
    timers = schedule_approval_timers(closure_eval, kc_profile, "2026-10-16T03:30:00-05:00", timer_ids)
    # approver decides at 03:40, before the backup window (W = 18:45 -> 03:48:45)
    cancel_on_decision(timers, closure_eval["evaluation_id"], APPROVED_AT)
    sent = []
    fake = lambda s, t: sent.append(s) or {"ok": True, "mode": "log_only", "provider_ref": None}
    result, created = notify(idempotency_key(closure_eval["evaluation_id"]), {}, closure_eval,
                             kc_profile, kc_roster, send_email_fn=fake, posture=None,
                             approval_id="apr_0001", notification_id="ntf_0001", now_sim=APPROVED_AT,
                             rng=random.Random(42), next_delivery_id=delivery_ids,
                             next_timer_id=timer_ids, storm=True)
    timers += result["timers"]
    assert created and len(sent) == 1
    # log-only mode: nothing actually sent, so nothing is labelled real
    assert not any(d["real"] for d in result["plan"]["deliveries"])

    deliveries, order = {}, []

    def on_fire(timer, action):  # what Badri's worker does per fired row
        order.append((timer["due_at_sim"], timer["id"]))
        if action["kind"] == "delivery_status":
            row = deliveries.setdefault(action["delivery_id"], {"recipient_id": action["recipient_id"]})
            row["status"] = action["status"]
    ctx = {"evaluation": closure_eval, "roster": kc_roster,
           "recipient_status_at": lambda at: recipient_status_from_deliveries(list(deliveries.values()))}
    # presenter acks two people at 03:41 (after delivery) then jumps +30 min
    fire_due(timers, "2026-10-16T03:41:00-05:00", ctx, timer_ids, on_fire)
    acked = [i for i, d in deliveries.items() if d["status"] == "delivered"][:2]
    for i in acked:
        deliveries[i]["status"] = "acknowledged"
    _, _, actions = fire_due(timers, "2026-10-16T04:11:00-05:00", ctx, timer_ids, on_fire)

    due_times = [parse_iso(o[0]) for o in order]
    assert due_times == sorted(due_times)
    esc = [a for a in actions if a["kind"] == "unacknowledged_to_supervisors"]
    assert len(esc) == 1 and esc[0]["at_sim"] == "2026-10-16T04:00:00-05:00"
    listed = {x["employee_id"] for rows in esc[0]["unacknowledged_by_supervisor"].values() for x in rows}
    acked_people = {deliveries[i]["recipient_id"] for i in acked}
    assert listed and not (listed & acked_people)
    view = escalation_view(timers, TZ)
    assert [v["step"] for v in view] == ["unacknowledged_to_supervisors"]  # cancelled chain hidden
    assert view[0]["fired_at_sim"] == "2026-10-16T04:00:00-05:00"
    # storm mode produced at least one failover that is now a real row
    assert any(d["status"] == "failed" for d in deliveries.values())
