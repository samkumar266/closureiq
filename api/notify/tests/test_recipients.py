import pytest

from api.notify.recipients import select_recipients


def by_id(items):
    return {i["employee_id"]: i for i in items}


def test_kc_closure_who_is_in_or_out(kc_roster):
    items = by_id(select_recipients(kc_roster, "closure"))
    assert len(items) == 25
    included = {k for k, v in items.items() if v["included"]}
    excluded = {k for k, v in items.items() if not v["included"]}
    # DEPRECATED(closureiq): on leave / off (e_022, e_023) were excluded; they now get an informational notice.
    # assert excluded == {"e_020", "e_021", "e_022", "e_023"}
    # detail elsewhere (e_020, e_021) are out; on leave / off (e_022, e_023) are looped in, by email only
    assert excluded == {"e_020", "e_021"}
    assert {"e_022", "e_023"} <= included
    assert items["e_022"]["channel_plan"] == ["email"]
    # already teleworking gets the informational closure notice
    assert {"e_017", "e_018", "e_019"} <= included
    assert "informational" in items["e_017"]["reason"]
    assert "Essential" in items["e_001"]["reason"]
    assert "contract lead" in items["e_024"]["reason"]
    assert "On detail" in items["e_020"]["reason"]
    # every item has a reason; excluded have no channel plan
    for item in items.values():
        assert item["reason"]
        assert ("channel_plan" in item) == item["included"]


# DEPRECATED(closureiq) START: teleworkers were excluded from delayed arrival; changed hours now loop them in.
# def test_delayed_arrival_excludes_teleworkers(kc_roster):
#     items = by_id(select_recipients(kc_roster, "delayed_arrival"))
#     assert items["e_017"]["included"] is False
#     assert items["e_017"]["reason"] == "Already teleworking; no change to work arrangement"
# DEPRECATED(closureiq) END


def test_changed_hours_loop_in_teleworkers_and_people_off_by_email_only(kc_roster):
    items = by_id(select_recipients(kc_roster, "delayed_arrival"))
    for person in ("e_017", "e_022"):  # already teleworking, on leave or off
        assert items[person]["included"] is True
        assert "informational" in items[person]["reason"]
        assert items[person]["channel_plan"] == ["email"]


def test_telework_posture_does_not_message_teleworkers_or_people_off(kc_roster):
    items = by_id(select_recipients(kc_roster, "unscheduled_leave_or_telework"))
    assert items["e_017"]["included"] is False
    assert items["e_022"]["included"] is False


def test_normal_operations_excludes_everyone(kc_roster):
    assert not any(i["included"] for i in select_recipients(kc_roster, "normal_operations"))


def test_voice_call_first_puts_voice_first(kc_roster):
    items = by_id(select_recipients(kc_roster, "closure"))
    assert items["e_015"]["channel_plan"][0] == "voice"
    assert items["e_001"]["channel_plan"] == ["email", "sms", "push"]


def test_shelter_only_people_on_site(kc_roster):
    items = by_id(select_recipients(kc_roster, "normal_operations", shelter_in_place=True))
    assert items["e_001"]["included"] and items["e_024"]["included"]
    assert not items["e_017"]["included"] and not items["e_020"]["included"]


def test_invalid_posture_rejected(kc_roster):
    with pytest.raises(ValueError):
        select_recipients(kc_roster, "normal_operations_elevated_monitoring")
