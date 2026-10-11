import pytest

from api.notify.recipients import POSTURES
from api.notify.templates import HEADINGS, fmt_time, render_message, render_shelter, variant_for

GROUPS = ["essential", "onsite_telework_eligible", "onsite_not_telework_eligible",
          "already_teleworking", "contractor"]
TZ = "America/Chicago"
PARAMS = {"delay_until": "2026-10-16T10:00:00-05:00", "dismiss_at": "2026-10-16T13:15:00-05:00",
          "closed_from": "2026-10-16T07:30:00-05:00", "closed_until": "2026-10-16T16:00:00-05:00",
          "next_update": "2026-10-16T02:00:00-05:00"}


@pytest.mark.parametrize("posture", [p for p in POSTURES if p != "normal_operations"])
@pytest.mark.parametrize("group", GROUPS)
@pytest.mark.parametrize("variant", ["standard", "large_print"])
def test_every_message_has_seven_parts(group, posture, variant):
    msg = render_message(group, posture, PARAMS, "Kansas City Service Center", TZ, variant)
    if group == "already_teleworking" and posture != "closure":
        assert msg is None
        return
    text = msg["text"]
    for heading in HEADINGS["en"]:
        assert (heading.upper() if variant == "large_print" else heading) in text
    assert "received" in text
    assert "understood" not in text.lower()
    assert msg["needs_translation"] is False


def test_times_are_local_and_readable():
    msg = render_message("onsite_telework_eligible", "delayed_arrival", PARAMS, "KC", TZ)
    assert "10:00 AM" in msg["text"] and "2:00 AM" in msg["text"]


def test_spanish_closure_is_translated():
    msg = render_message("onsite_not_telework_eligible", "closure", PARAMS, "KC", TZ, "spanish")
    assert msg["needs_translation"] is False
    assert "No se presente" in msg["text"] and "recibió" in msg["text"]
    for heading in HEADINGS["es"]:
        assert heading in msg["text"]


def test_missing_spanish_variant_is_flagged_not_silent():
    msg = render_message("onsite_telework_eligible", "delayed_arrival", PARAMS, "KC", TZ, "spanish")
    assert msg["needs_translation"] is True
    assert msg["variant"] == "spanish"


def test_missing_time_is_explicit():
    assert fmt_time(None, TZ) == "not set yet"


def test_shelter_messages():
    en = render_shelter("KC")
    es = render_shelter("KC", "spanish")
    assert "SHELTER IN PLACE" in en["text"] and "received" in en["text"]
    assert "REFÚGIESE" in es["text"]


def test_variant_for():
    assert variant_for(["spanish"]) == "spanish"
    assert variant_for(["large_print"]) == "large_print"
    assert variant_for(["voice_call_first"]) == "standard"
    assert variant_for([]) == "standard"
