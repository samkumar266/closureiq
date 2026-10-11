"""The one real channel: email through the Resend HTTPS API.

Environment variables (never hard-coded, never logged):
- EMAIL_PROVIDER_KEY: Resend API key. If empty, log-only mode (nothing is sent).
- DEMO_EMAIL_TO: every real email goes here, whoever it was meant for.
- EMAIL_FROM: optional sender, default "ClosureIQ <onboarding@resend.dev>"
  (Resend's test sender, which can only deliver to your own Resend sign-up address).
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Mapping

import httpx

RESEND_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "ClosureIQ <onboarding@resend.dev>"
TIMEOUT_SECONDS = 10

log = logging.getLogger("closureiq.email")


def email_mode(env: Mapping[str, str] = os.environ) -> str:
    """'resend' when a key and a demo inbox are set, otherwise 'log_only'."""
    return "resend" if env.get("EMAIL_PROVIDER_KEY") and env.get("DEMO_EMAIL_TO") else "log_only"


def send_email(subject: str, text: str, *, env: Mapping[str, str] = os.environ,
               http_post: Callable[..., httpx.Response] = httpx.post) -> dict:
    """Send one email to DEMO_EMAIL_TO. Returns {ok, mode, provider_ref, error}. Never raises."""
    if email_mode(env) == "log_only":
        log.info("email log-only (no EMAIL_PROVIDER_KEY or DEMO_EMAIL_TO): %s", subject)
        return {"ok": True, "mode": "log_only", "provider_ref": None, "error": None}
    body = {"from": env.get("EMAIL_FROM") or DEFAULT_FROM, "to": [env["DEMO_EMAIL_TO"]],
            "subject": subject, "text": text}
    headers = {"Authorization": f"Bearer {env['EMAIL_PROVIDER_KEY']}"}
    try:
        response = http_post(RESEND_URL, json=body, headers=headers, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        log.warning("email send failed: %s", type(exc).__name__)
        return {"ok": False, "mode": "resend", "provider_ref": None, "error": type(exc).__name__}
    if response.status_code >= 300:
        log.warning("email send failed: HTTP %s", response.status_code)
        return {"ok": False, "mode": "resend", "provider_ref": None,
                "error": f"HTTP {response.status_code}"}
    provider_ref = (response.json() or {}).get("id")
    log.info("email sent via resend: %s (%s)", subject, provider_ref)
    return {"ok": True, "mode": "resend", "provider_ref": provider_ref, "error": None}
