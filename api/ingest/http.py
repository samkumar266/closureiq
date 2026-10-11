"""HTTP JSON fetch helper with the NWS User-Agent and one delayed retry."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from api.config import settings


@dataclass(slots=True)
class FetchResult:
    source: str
    url: str
    ok: bool
    payload: dict[str, Any]
    raw_text: str
    http_status: int | None
    error: str | None
    fetched_at: datetime
    source_updated_at: str | None = None


def _source_updated_at(payload: dict[str, Any]) -> str | None:
    props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
    for item in (payload.get("updated"), payload.get("updateTime"), props.get("updated"), props.get("updateTime")):
        if isinstance(item, str) and item:
            return item
    return None


async def fetch_json(source: str, url: str, *, headers: dict[str, str] | None = None,
                     retries: int = 1, retry_seconds: float | None = None) -> FetchResult:
    """Fetch JSON. On failure, retry once after the configured wait.

    A failed request remains represented as an explicit result so callers can record it.
    The original response text is retained for evidence storage.
    """
    request_headers = {
        "Accept": "application/geo+json, application/json;q=0.9",
        "User-Agent": settings.nws_user_agent,
    }
    if headers:
        request_headers.update(headers)
    wait_seconds = settings.nws_retry_seconds if retry_seconds is None else retry_seconds
    last_result: FetchResult | None = None

    for attempt in range(retries + 1):
        fetched_at = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(
                timeout=settings.nws_timeout_seconds,
                follow_redirects=True,
                headers=request_headers,
            ) as client:
                response = await client.get(url)
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            raw_text = response.text or "{}"
            if response.is_success and isinstance(payload, dict):
                return FetchResult(
                    source=source, url=url, ok=True, payload=payload,
                    raw_text=raw_text, http_status=response.status_code,
                    error=None, fetched_at=fetched_at,
                    source_updated_at=_source_updated_at(payload),
                )
            last_result = FetchResult(
                source=source, url=url, ok=False,
                payload=payload if isinstance(payload, dict) else {},
                raw_text=raw_text, http_status=response.status_code,
                error=f"HTTP {response.status_code}: {raw_text[:500]}",
                fetched_at=fetched_at, source_updated_at=_source_updated_at(payload) if isinstance(payload, dict) else None,
            )
        except (httpx.HTTPError, TimeoutError, OSError) as exc:
            last_result = FetchResult(
                source=source, url=url, ok=False, payload={}, raw_text="{}",
                http_status=None, error=f"{type(exc).__name__}: {exc}",
                fetched_at=fetched_at, source_updated_at=None,
            )
        if attempt < retries:
            await asyncio.sleep(max(0.0, wait_seconds))

    assert last_result is not None
    return last_result
