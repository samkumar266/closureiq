import httpx

from api.notify.email_sender import RESEND_URL, email_mode, send_email

FAKE_KEY = "test-key-not-real"


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_log_only_without_key():
    calls = []
    out = send_email("s", "t", env={"DEMO_EMAIL_TO": "demo@closureiq.example"},
                     http_post=lambda *a, **k: calls.append(1))
    assert out == {"ok": True, "mode": "log_only", "provider_ref": None, "error": None}
    assert calls == []
    assert email_mode({"EMAIL_PROVIDER_KEY": FAKE_KEY}) == "log_only"  # no inbox either


def test_always_sends_to_demo_inbox():
    seen = {}

    def fake_post(url, json, headers, timeout):
        seen.update(url=url, json=json, headers=headers)
        return FakeResponse(200, {"id": "re_abc"})
    env = {"EMAIL_PROVIDER_KEY": FAKE_KEY, "DEMO_EMAIL_TO": "demo@closureiq.example"}
    out = send_email("Closure", "body", env=env, http_post=fake_post)
    assert out["ok"] and out["mode"] == "resend" and out["provider_ref"] == "re_abc"
    assert seen["url"] == RESEND_URL
    assert seen["json"]["to"] == ["demo@closureiq.example"]
    assert seen["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"


def test_http_error_and_exception_never_raise_or_leak_key(caplog):
    env = {"EMAIL_PROVIDER_KEY": FAKE_KEY, "DEMO_EMAIL_TO": "demo@closureiq.example"}
    out = send_email("s", "t", env=env, http_post=lambda *a, **k: FakeResponse(401, {}))
    assert out["ok"] is False and out["error"] == "HTTP 401"

    def boom(*a, **k):
        raise httpx.ConnectError("down")
    out = send_email("s", "t", env=env, http_post=boom)
    assert out["ok"] is False and out["error"] == "ConnectError"
    assert FAKE_KEY not in caplog.text
