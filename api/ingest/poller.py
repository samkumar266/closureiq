"""Fetch and persist source evidence. Raw snapshots are stored before normalization."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.config import settings
from api.ingest.http import FetchResult
from api.ingest.nws import fetch_active_alerts, fetch_point_metadata, fetch_grid_data, fetch_hourly_forecast
from api.ingest.usgs import fetch_usgs_gauge, fetch_nwps_categories
from api.store.repository import Store

SOURCE_MAX_AGE_SECONDS = {
    "NWS alerts": 600,
    "NWS point metadata": 10800,
    "NWS forecast grid": 10800,
    "NWS hourly forecast": 10800,
    "USGS gauge": 7200,
    "NWS flood categories": 86400,
}
SLOW_SOURCE_INTERVALS = {
    "NWS point metadata": 900,
    "NWS forecast grid": 900,
    "NWS hourly forecast": 900,
    "USGS gauge": 900,
    "NWS flood categories": 86400,
}


def _age_seconds(snapshot: dict[str, Any] | None) -> float | None:
    if not snapshot:
        return None
    try:
        fetched = datetime.fromisoformat(snapshot["fetched_at_wall"].replace("Z", "+00:00"))
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - fetched.astimezone(timezone.utc)).total_seconds()
    except (ValueError, KeyError, TypeError):
        return None


def _due(store: Store, facility_id: str, source: str, interval_seconds: int, force: bool) -> bool:
    if force:
        return True
    last = store.latest_snapshot(facility_id, source, successful_only=True)
    age = _age_seconds(last)
    return age is None or age >= interval_seconds


def _fixture_path(source: str, facility_id: str) -> Path:
    slug = {
        "NWS alerts": "nws_alerts.json",
        "NWS point metadata": "nws_points.json",
        "NWS forecast grid": "nws_grid.json",
        "NWS hourly forecast": "nws_hourly.json",
        "USGS gauge": "usgs_gauge.json",
        "NWS flood categories": "nwps_categories.json",
    }.get(source, "unknown.json")
    custom = settings.project_root / "mocks" / facility_id / slug
    if custom.exists():
        return custom
    return settings.project_root / "mocks" / slug


def _load_fixture(source: str, facility_id: str) -> FetchResult:
    path = _fixture_path(source, facility_id)
    now = datetime.now(timezone.utc)
    if not path.exists():
        return FetchResult(source, f"file://{path}", False, {}, "{}", None,
                           f"Replay fixture not found: {path.relative_to(settings.project_root)}", now)
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("fixture root must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        return FetchResult(source, f"file://{path}", False, {}, "{}", None,
                           f"Invalid replay fixture: {exc}", now)
    return FetchResult(source, f"file://{path}", True, payload, raw, 200, None, now)


def _persist(store: Store, facility: dict, result: FetchResult, mode: str) -> dict:
    snapshot = store.append_snapshot(
        facility_id=facility["facility_id"], source=result.source, url=result.url,
        fetched_at_wall=result.fetched_at.isoformat(), fetched_at_sim=store.clock_now_sim(),
        http_status=result.http_status, ok=result.ok, raw_payload=result.raw_text or "{}",
        source_updated_at=result.source_updated_at, error_text=result.error, data_mode=mode,
    )
    store.set_last_poll_at(result.fetched_at.isoformat())
    return snapshot


async def _fetch_source(store: Store, facility: dict, source: str, fetcher, mode: str):
    if mode == "replay":
        result = _load_fixture(source, facility["facility_id"])
    else:
        result = await fetcher
    return _persist(store, facility, result, mode)


async def poll_alerts(store: Store, facility: dict) -> dict:
    mode = store.get_data_mode(settings.data_mode)
    lat = float(facility["location"]["lat"])
    lon = float(facility["location"]["lon"])
    if mode == "replay":
        result = _load_fixture("NWS alerts", facility["facility_id"])
    else:
        result = await fetch_active_alerts(lat, lon)
    return _persist(store, facility, result, mode)


async def poll_slow_sources(store: Store, facility: dict, *, force: bool = False) -> list[dict]:
    """Poll point metadata and slow evidence independently using successful cached URLs."""
    mode = store.get_data_mode(settings.data_mode)
    facility_id = facility["facility_id"]
    lat = float(facility["location"]["lat"])
    lon = float(facility["location"]["lon"])
    created: list[dict] = []

    # Refresh /points on its own cadence. Even a failed refresh is persisted.
    if _due(store, facility_id, "NWS point metadata", 900, force):
        points_result = (
            _load_fixture("NWS point metadata", facility_id)
            if mode == "replay"
            else await fetch_point_metadata(lat, lon)
        )
        created.append(_persist(store, facility, points_result, mode))

    # Always derive URLs from the latest successful point snapshot. Do not let a
    # failed /points refresh erase a still-fresh URL previously learned from NWS.
    last_points = store.latest_snapshot(facility_id, "NWS point metadata", successful_only=True)
    grid_url = hourly_url = None
    if last_points:
        try:
            properties = json.loads(last_points["raw_payload"]).get("properties") or {}
            grid_url = properties.get("forecastGridData")
            hourly_url = properties.get("forecastHourly")
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

    if _due(store, facility_id, "NWS forecast grid", 900, force):
        if grid_url:
            result = (
                _load_fixture("NWS forecast grid", facility_id)
                if mode == "replay"
                else await fetch_grid_data(grid_url)
            )
        else:
            result = FetchResult(
                "NWS forecast grid", "", False, {}, "{}", None,
                "forecastGridData URL unavailable from a successful NWS /points response",
                datetime.now(timezone.utc),
            )
        if result is not None:
            created.append(_persist(store, facility, result, mode))

    if _due(store, facility_id, "NWS hourly forecast", 900, force):
        if hourly_url:
            result = (
                _load_fixture("NWS hourly forecast", facility_id)
                if mode == "replay"
                else await fetch_hourly_forecast(hourly_url)
            )
        else:
            result = FetchResult(
                "NWS hourly forecast", "", False, {}, "{}", None,
                "forecastHourly URL unavailable from a successful NWS /points response",
                datetime.now(timezone.utc),
            )
        if result is not None:
            created.append(_persist(store, facility, result, mode))

    gauge = facility.get("gauge")
    if gauge and _due(store, facility_id, "USGS gauge", 900, force):
        result = (
            _load_fixture("USGS gauge", facility_id)
            if mode == "replay"
            else await fetch_usgs_gauge(str(gauge["usgs_site"]))
        )
        created.append(_persist(store, facility, result, mode))

    if gauge and _due(store, facility_id, "NWS flood categories", 86400, force):
        result = (
            _load_fixture("NWS flood categories", facility_id)
            if mode == "replay"
            else await fetch_nwps_categories(str(gauge["nwps_id"]))
        )
        created.append(_persist(store, facility, result, mode))

    return created


async def poll_facility(store: Store, facility: dict, *, force_slow: bool = False) -> list[dict]:
    """Poll alerts and due supplementary sources for one facility."""
    rows = [await poll_alerts(store, facility)]
    rows.extend(await poll_slow_sources(store, facility, force=force_slow))
    return rows


async def startup_poll(store: Store, facilities: list[dict]) -> None:
    """Best-effort initial poll; one facility's failure should not block the others."""
    import asyncio
    await asyncio.gather(*(poll_facility(store, f, force_slow=True) for f in facilities), return_exceptions=True)
