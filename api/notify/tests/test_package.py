import json

from api.notify.package import build_package, build_preview

NOW = "2026-10-15T20:31:00-05:00"
TOP_KEYS = ["notification_id", "evaluation_id", "approval_id", "standing_policy", "preview",
            "ack_deadline", "next_update", "package", "deliveries", "escalation"]
INCLUDED_KEYS = ["employee_id", "included", "group", "reason", "message_id", "channel_plan"]
EXCLUDED_KEYS = ["employee_id", "included", "group", "reason"]


def test_contract_shape(closure_eval, kc_profile, kc_roster):
    pkg = build_package(closure_eval, kc_profile, kc_roster, now_sim=NOW,
                        notification_id="ntf_0001", approval_id="apr_0001")
    assert list(pkg) == TOP_KEYS
    assert pkg["preview"] is False and pkg["standing_policy"] is None
    assert pkg["notification_id"] == "ntf_0001" and pkg["approval_id"] == "apr_0001"
    assert pkg["next_update"] == "2026-10-16T02:00:00-05:00"
    assert set(pkg["package"]) == {"recipients", "messages", "warnings"}
    message_ids = {m["id"] for m in pkg["package"]["messages"]}
    for r in pkg["package"]["recipients"]:
        assert list(r) == (INCLUDED_KEYS if r["included"] else EXCLUDED_KEYS)
        if r["included"]:
            assert r["message_id"] in message_ids
    for m in pkg["package"]["messages"]:
        assert {"id", "group", "text"} <= set(m)
    json.dumps(pkg)  # serialisable


def test_ack_deadline_is_send_plus_20_the_night_before(closure_eval, kc_profile, kc_roster):
    pkg = build_package(closure_eval, kc_profile, kc_roster, now_sim=NOW)
    assert pkg["ack_deadline"] == "2026-10-15T20:51:00-05:00"


def test_ack_deadline_capped_by_departure(closure_eval, kc_profile, kc_roster):
    # 05:50: earliest shift 07:00 - 45 min commute = 06:15, minus 10 = 06:05 (< 06:10)
    pkg = build_package(closure_eval, kc_profile, kc_roster, now_sim="2026-10-16T05:50:00-05:00")
    assert pkg["ack_deadline"] == "2026-10-16T06:05:00-05:00"


def test_preview_has_no_ids(closure_eval, kc_profile, kc_roster):
    pkg = build_preview(closure_eval, kc_profile, kc_roster, now_sim=NOW)
    assert pkg["preview"] is True
    assert pkg["notification_id"] is None and pkg["approval_id"] is None
    assert pkg["deliveries"] == [] and pkg["escalation"] == []


def test_spanish_people_get_spanish_closure(closure_eval, kc_profile, kc_roster):
    pkg = build_package(closure_eval, kc_profile, kc_roster, now_sim=NOW)
    msgs = {m["id"]: m for m in pkg["package"]["messages"]}
    r = next(r for r in pkg["package"]["recipients"] if r["employee_id"] == "e_016")
    assert msgs[r["message_id"]]["variant"] == "spanish"
    assert pkg["package"]["warnings"] == []


def test_override_to_delayed_warns_translation_and_missing_time(closure_eval, kc_profile, kc_roster):
    pkg = build_preview(closure_eval, kc_profile, kc_roster, "delayed_arrival", now_sim=NOW)
    kinds = [w["type"] for w in pkg["package"]["warnings"]]
    assert "needs_translation" in kinds and "missing_parameters" in kinds
    tr = [w for w in pkg["package"]["warnings"] if w["type"] == "needs_translation"]
    assert sorted(sum((w["employee_ids"] for w in tr), [])) == ["e_004", "e_006", "e_016"]


def test_identical_input_identical_output(closure_eval, kc_profile, kc_roster):
    a = build_package(closure_eval, kc_profile, kc_roster, now_sim=NOW)
    b = build_package(closure_eval, kc_profile, kc_roster, now_sim=NOW)
    assert json.dumps(a) == json.dumps(b)
