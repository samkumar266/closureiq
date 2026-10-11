import pytest

from api.notify.recipients import select_recipients


def by_id(items):
    return {i["employee_id"]: i for i in items}


def test_kc_closure_who_is_in_or_out(kc_roster):
    items = by_id(select_recipients(kc_roster, "closure"))
    assert len(items) == 25
    included = {k for k, v in items.items() if v["included"]}
    excluded = {k for k, v in items.items() if not v["included"]}
    # detail elsewhere (e_020, e_021) and on leave / off (e_022, e_023) are out
    assert excluded == {"e_020", "e_021", "e_022", "e_023"}
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


def test_delayed_arrival_excludes_teleworkers(kc_roster):
    items = by_id(select_recipients(kc_roster, "delayed_arrival"))
    assert items["e_017"]["included"] is False
    assert items["e_017"]["reason"] == "Already teleworking; no change to work arrangement"


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
