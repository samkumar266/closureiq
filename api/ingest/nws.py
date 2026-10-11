"""NWS API client. This module does not make policy decisions."""
from __future__ import annotations

from urllib.parse import urlparse
from datetime import datetime, timezone

from api.ingest.http import FetchResult, fetch_json

NWS_BASE = "https://api.weather.gov"


async def fetch_active_alerts(lat: float, lon: float) -> FetchResult:
    url = f"{NWS_BASE}/alerts/active?point={lat:g},{lon:g}"
    return await fetch_json("NWS alerts", url)


async def fetch_point_metadata(lat: float, lon: float) -> FetchResult:
    url = f"{NWS_BASE}/points/{lat:g},{lon:g}"
    return await fetch_json("NWS point metadata", url)


async def fetch_grid_data(url: str | None) -> FetchResult | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "api.weather.gov":
        return FetchResult(
            source="NWS forecast grid", url=url, ok=False, payload={}, raw_text="{}",
            http_status=None, error="Rejected unexpected forecastGridData URL host",
            fetched_at=datetime.now(timezone.utc),
        )
    return await fetch_json("NWS forecast grid", url)


async def fetch_hourly_forecast(url: str | None) -> FetchResult | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "api.weather.gov":
        return FetchResult(
            source="NWS hourly forecast", url=url, ok=False, payload={}, raw_text="{}",
            http_status=None, error="Rejected unexpected forecastHourly URL host",
            fetched_at=datetime.now(timezone.utc),
        )
    result = await fetch_json("NWS hourly forecast", url)
    return result
