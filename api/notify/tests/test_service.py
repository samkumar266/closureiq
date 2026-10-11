import json
import random
import threading

from api.notify.service import create_notification, idempotency_key, notify

NOW = "2026-10-15T20:31:00-05:00"


def kwargs(seed=42):
    from api.notify.simulator import counter_ids
    return dict(posture=None, approval_id="apr_0001", notification_id="ntf_0001", now_sim=NOW,
                rng=random.Random(seed), next_delivery_id=counter_ids("dlv"),
                next_timer_id=counter_ids("tmr"))


def test_double_approve_sends_once(closure_eval, kc_profile, kc_roster):
    sent, outbox = [], {}

    def fake(subject, text):
        sent.append((subject, text))
        return {"ok": True, "mode": "resend", "provider_ref": "re_123"}
    key = idempotency_key(closure_eval["evaluation_id"])
    first, c1 = notify(key, outbox, closure_eval, kc_profile, kc_roster, send_email_fn=fake, **kwargs())
    second, c2 = notify(key, outbox, closure_eval, kc_profile, kc_roster, send_email_fn=fake, **kwargs())
    assert (c1, c2) == (True, False) and second is first
    assert len(sent) == 1
    assert sent[0][0] == "[ClosureIQ demo] Kansas City Service Center: Closure"
    real = [d for d in first["plan"]["deliveries"] if d["real"]]
    assert real[0]["provider_ref"] == "re_123"


def test_concurrent_approves_send_once(closure_eval, kc_profile, kc_roster):
    sent, outbox = [], {}
    fake = lambda s, t: sent.append(s) or {"ok": True, "mode": "log_only", "provider_ref": None}
    key = idempotency_key(closure_eval["evaluation_id"])
    threads = [threading.Thread(target=notify, args=(key, outbox, closure_eval, kc_profile, kc_roster),
                                kwargs=dict(send_email_fn=fake, **kwargs())) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(sent) == 1


def test_identical_input_identical_output(closure_eval, kc_profile, kc_roster):
    a = create_notification(closure_eval, kc_profile, kc_roster, **kwargs(7))
    b = create_notification(closure_eval, kc_profile, kc_roster, **kwargs(7))
    assert json.dumps(a) == json.dumps(b)


def test_real_email_failure_fails_over(closure_eval, kc_profile, kc_roster):
    fake = lambda s, t: {"ok": False, "mode": "resend", "provider_ref": None, "error": "HTTP 500"}
    result, _ = notify("k", {}, closure_eval, kc_profile, kc_roster, send_email_fn=fake, **kwargs())
    real = next(d for d in result["plan"]["deliveries"] if d["real"])
    person = [d for d in result["plan"]["deliveries"] if d["recipient_id"] == real["recipient_id"]]
    assert len(person) >= 2 and person[1]["channel"] != "email"
