"""USGS and NWPS supplementary source clients."""
from __future__ import annotations

from api.ingest.http import FetchResult, fetch_json


async def fetch_usgs_gauge(site_id: str) -> FetchResult:
    url = (
        "https://waterservices.usgs.gov/nwis/iv/?format=json"
        f"&sites={site_id}&parameterCd=00065,00060"
    )
    return await fetch_json("USGS gauge", url, headers={"Accept": "application/json"})


async def fetch_nwps_categories(gauge_id: str) -> FetchResult:
    url = f"https://api.water.noaa.gov/nwps/v1/gauges/{gauge_id}"
    return await fetch_json("NWS flood categories", url, headers={"Accept": "application/json"})
