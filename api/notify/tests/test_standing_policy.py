import random

from api.notify.service import create_notification, idempotency_key, notify
from api.notify.simulator import counter_ids
from api.notify.standing_policy import build_shelter_package, should_auto_send

NOW = "2026-10-16T13:00:00-05:00"


def tornado(closure_eval, onset="2026-10-16T13:10:00-05:00", label="Tornado Warning"):
    ev = dict(closure_eval, posture="normal_operations", evaluation_id="eval_0099")
    alert = dict(ev["inputs"][0], label=label, onset=onset, ends="2026-10-16T14:00:00-05:00")
    ev["inputs"] = [alert] + ev["inputs"][1:]
    return ev


def test_triggers(closure_eval):
    assert should_auto_send(tornado(closure_eval), NOW)
    assert should_auto_send(tornado(closure_eval, label="Severe Thunderstorm Warning"), NOW)  # onset in 10 min
    assert not should_auto_send(tornado(closure_eval, onset="2026-10-16T15:00:00-05:00",
                                        label="Severe Thunderstorm Warning"), NOW)
    # an instruction alone never sends (the flood warning in closure.json started hours ago)
    assert not should_auto_send(dict(closure_eval, safety_instruction="Shelter in place until 14:00"), NOW)
    assert not should_auto_send(closure_eval, "2026-10-15T20:30:00-05:00")  # plain flood warning, onset hours away
    assert not should_auto_send(dict(tornado(closure_eval), hypothetical=True), NOW)


def test_shelter_package_has_no_approval(closure_eval, kc_profile, kc_roster):
    pkg = build_shelter_package(tornado(closure_eval), kc_profile, kc_roster, now_sim=NOW,
                                notification_id="ntf_0009")
    assert pkg["approval_id"] is None and pkg["standing_policy"] == "shelter_in_place"
    assert pkg["preview"] is False
    included = {r["employee_id"] for r in pkg["package"]["recipients"] if r["included"]}
    assert "e_001" in included and "e_024" in included          # on site, contractor
    assert "e_017" not in included and "e_022" not in included  # teleworking, on leave
    assert all("SHELTER" in m["text"] or "REFÚGIESE" in m["text"] for m in pkg["package"]["messages"])


def test_shelter_send_tells_approver_and_is_idempotent(closure_eval, kc_profile, kc_roster):
    ev = tornado(closure_eval)
    sent, outbox = [], {}
    kwargs = dict(posture=None, approval_id=None, notification_id="ntf_0009", now_sim=NOW,
                  rng=random.Random(1), next_delivery_id=counter_ids("dlv"),
                  next_timer_id=counter_ids("tmr"), standing_policy="shelter_in_place")
    fake = lambda subject, text: sent.append(subject) or {"ok": True, "mode": "log_only", "provider_ref": None}
    key = idempotency_key(ev["evaluation_id"], "shelter_in_place")
    result, created = notify(key, outbox, ev, kc_profile, kc_roster, send_email_fn=fake, **kwargs)
    again, created2 = notify(key, outbox, ev, kc_profile, kc_roster, send_email_fn=fake, **kwargs)
    assert created and not created2 and again is result and len(sent) == 1
    assert "Shelter in place" in sent[0]
    assert result["timers"][0]["kind"] == "shelter_notify_approver"
    assert result["timers"][0]["due_at_sim"] == "2026-10-16T13:00:00-05:00"
    # a later human approval of the same evaluation is a different key
    assert idempotency_key(ev["evaluation_id"]) not in outbox


def test_generic_shelter_advice_does_not_auto_send(closure_eval):
    # Real engine text seen live on a Flash Flood Warning (Aiken SC, 2026-10-10).
    ev = dict(closure_eval, safety_instruction="Follow official NWS instructions; seek appropriate shelter if directed.")
    assert not should_auto_send(ev, "2026-10-15T20:30:00-05:00")
    # Live case, Aiken SC: flash flood warning under way for 40 min plus a real
    # "Shelter in place" line. Not a standing-policy case: it waits for approval.
    ev = dict(closure_eval, safety_instruction="Shelter in place and follow official instructions.")
    assert not should_auto_send(ev, "2026-10-15T20:30:00-05:00")


def test_live_alert_list_shape(closure_eval):
    # Live inputs carry a list of alerts in `value`; only a Tornado Warning in it triggers.
    def live(events):
        alert = {"id": "in_1", "role": "drove", "source": "NWS alerts", "label": "Active NWS alerts at facility point",
                 "value": [{"event": e, "tier": "warning"} for e in events],
                 "onset": "2026-10-16T12:00:00-05:00", "ends": "2026-10-16T14:00:00-05:00"}
        return dict(closure_eval, safety_instruction=None, inputs=[alert])
    assert not should_auto_send(live(["Flash Flood Warning", "Lake Wind Advisory"]), NOW)
    assert should_auto_send(live(["Tornado Warning"]), NOW)
