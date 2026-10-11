"""Engine boundary owned by Badri's API wiring.

When Samanth's `api.engine` implementation is added, wire it in this adapter. Until then,
`fallback_evaluate` provides a deterministic, explicitly-labelled MVP stub so the API and
storage can be exercised end-to-end. It is not a validated operational closure policy.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo
from typing import Any
import json

from api.ingest.normalizers import normalize_alerts, parse_datetime, extract_usgs_latest
from api.ingest.units import target_unit_for_field, convert_value
from api.ingest.poller import SOURCE_MAX_AGE_SECONDS

POSTURES = ["normal_operations", "delayed_arrival", "early_dismissal", "unscheduled_leave_or_telework", "closure"]
POSTURE_RANK = {p: i for i, p in enumerate(POSTURES)}
SEVERITY_RANK = {"unknown": 0, "minor": 1, "moderate": 2, "severe": 3, "extreme": 4}


def _local_time(iso_value: str | None, timezone_name: str) -> str | None:
    parsed = parse_datetime(iso_value)
    if parsed is None:
        return None
    try:
        return parsed.astimezone(ZoneInfo(timezone_name)).isoformat()
    except Exception:
        return parsed.isoformat()


def _age_seconds(snapshot: dict | None, now: datetime) -> float | None:
    if not snapshot:
        return None
    fetched = parse_datetime(snapshot.get("fetched_at_wall"))
    if fetched is None:
        return None
    return max(0.0, (now.astimezone(timezone.utc) - fetched.astimezone(timezone.utc)).total_seconds())


def _last_good_or_latest(store, facility_id: str, source: str) -> dict | None:
    return store.latest_snapshot(facility_id, source, successful_only=True)


def _field_periods(grid_payload: dict, field_name: str) -> list[dict]:
    properties = grid_payload.get("properties") or {}
    field = properties.get(field_name)
    if not isinstance(field, dict):
        return []
    uom = field.get("uom", "")
    requested_unit, display_unit = target_unit_for_field(field_name)
    values = []
    for item in field.get("values") or []:
        try:
            value = float(item["value"])
        except (TypeError, ValueError, KeyError):
            continue
        if requested_unit:
            value = convert_value(value, uom, requested_unit)
            unit = display_unit
        else:
            unit = uom
        values.append({"value": round(value, 3), "unit": unit, "valid_time": item.get("validTime")})
    return values


GRID_OVERRIDE_UNITS = {"windGust": "mph", "windSpeed": "mph", "iceAccumulation": "in",
                       "snowfallAmount": "in", "temperature": "degF"}


def _grid_override_periods(override: dict) -> dict:
    """{"windGust": 65} -> {"windGust": [{"value": 65.0, "unit": "mph", "valid_time": "what-if"}]}."""
    out = {}
    for name, value in override.items():
        if name in GRID_OVERRIDE_UNITS and isinstance(value, (int, float)):
            out[name] = [{"value": float(value), "unit": GRID_OVERRIDE_UNITS[name], "valid_time": "what-if"}]
    return out


ALERT_OVERRIDE_KEYS = ("event", "severity", "certainty", "urgency", "tier", "onset", "ends")
ASSUMED_ALERT_HOURS = 6


def _apply_alert_override(active_alerts: list[dict], inputs: list[dict], overrides: dict | None,
                          now: datetime) -> tuple[list[dict], dict | None]:
    """What-if on the alerts input, e.g. {"in_1": {"severity": "Severe"}}.

    With an active alert, the strongest one is changed. With none, an example
    Warning is assumed (certainty Likely, starting now, lasting 6 hours) and
    returned so the result can say exactly what was assumed.
    """
    alert_input = next((i for i in inputs if i["source"] == "NWS alerts"), None)
    override = (overrides or {}).get(alert_input["id"]) if alert_input else None
    if not isinstance(override, dict):
        return active_alerts, None
    changes = {k: override[k] for k in ALERT_OVERRIDE_KEYS if k in override}
    if active_alerts:
        rank = {"none": 0, "advisory": 1, "watch": 2, "warning": 3}
        target = max(active_alerts, key=lambda a: rank.get(a.get("tier"), 0))
        updated = [dict(a, **changes) if a is target else a for a in active_alerts]
        return updated, None
    assumed = {"id": "what-if", "event": "Severe Thunderstorm Warning", "headline": "What-if alert (assumed)",
               "severity": "Severe", "certainty": "Likely", "urgency": "Expected", "tier": "warning",
               "hazard": "thunderstorm and wind", "onset": now.isoformat(),
               "ends": (now + timedelta(hours=ASSUMED_ALERT_HOURS)).isoformat()}
    assumed.update(changes)
    return [assumed], assumed


def _apply_grid_overrides(forecast_fields: dict, inputs: list[dict], overrides: dict | None) -> dict:
    """What-if: an override of the grid input, e.g. {"in_2": {"windGust": 65}}, replaces
    those fields before the T4-T6 checks, so the hypothetical result is re-evaluated."""
    grid_input = next((i for i in inputs if i["source"] == "NWS forecast grid"), None)
    if not overrides or not grid_input or not isinstance(overrides.get(grid_input["id"]), dict):
        return forecast_fields
    return {**forecast_fields, **_grid_override_periods(overrides[grid_input["id"]])}


def _grid_summary(payload: dict) -> dict:
    names = ["windGust", "windSpeed", "iceAccumulation", "snowfallAmount", "temperature"]
    return {name: _field_periods(payload, name) for name in names if _field_periods(payload, name)}


OBSERVATION_WINDOW_MINUTES = 60


def _to_mph(measure: dict | None) -> float | None:
    """NWS observation wind values come in km/h (wmoUnit:km_h-1) or m/s (wmoUnit:m_s-1)."""
    if not isinstance(measure, dict) or measure.get("value") is None:
        return None
    value = float(measure["value"])
    unit = str(measure.get("unitCode", ""))
    if unit.endswith("m_s-1"):
        return round(value * 2.23694, 1)
    return round(value * 0.621371, 1)


def _observed_wind(payload: dict, station: str, now: datetime) -> dict | None:
    """Highest measured gust and sustained wind in the last hour at the station.

    A missing gust means none was reported (calm or steady wind), so it counts as 0, not as missing data.
    Returns None when the station has no observation in the window (that is missing evidence).
    """
    recent = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        observed_at = parse_datetime(props.get("timestamp"))
        if observed_at and now - observed_at <= timedelta(minutes=OBSERVATION_WINDOW_MINUTES):
            recent.append(props)
    if not recent:
        return None
    gusts = [_to_mph(p.get("windGust")) or 0.0 for p in recent]
    speeds = [_to_mph(p.get("windSpeed")) or 0.0 for p in recent]
    return {
        "station": station,
        "max_gust_mph": max(gusts),
        "max_sustained_mph": max(speeds),
        "latest_observed_at": max(str(p.get("timestamp")) for p in recent),
        "observations": len(recent),
        "window_minutes": OBSERVATION_WINDOW_MINUTES,
    }


def _next_work_deadline(facility: dict, now_local: datetime) -> str:
    hh, mm = [int(x) for x in facility.get("earliest_departure", "06:15").split(":")]
    deadline = datetime.combine(now_local.date(), time(hh, mm), tzinfo=now_local.tzinfo) - timedelta(minutes=int(facility.get("notification_lead_min", 90)))
    if deadline <= now_local:
        deadline += timedelta(days=1)
    return deadline.isoformat()


def _interval_overlaps(alert_start: datetime, alert_end: datetime, start_hhmm: str, end_hhmm: str, now_local: datetime) -> bool:
    tz = now_local.tzinfo
    start_h, start_m = map(int, start_hhmm.split(":"))
    end_h, end_m = map(int, end_hhmm.split(":"))
    window_start = datetime.combine(now_local.date(), time(start_h, start_m), tzinfo=tz)
    window_end = datetime.combine(now_local.date(), time(end_h, end_m), tzinfo=tz)
    return alert_start < window_end and alert_end > window_start


def fallback_evaluate(store, facility: dict, snapshots: list[dict], *, evaluated_at: datetime | None = None,
                      previous_result: dict | None = None, overrides: dict | None = None,
                      hypothetical: bool = False, data_mode: str | None = None) -> dict:
    """Return the API contract's Recommendation object using a conservative MVP fallback."""
    now = evaluated_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    tzname = facility["location"]["timezone"]
    local_now = now.astimezone(ZoneInfo(tzname))
    # The input list is the exact evidence scope for this evaluation/replay; never query later
    # snapshots from the global database while replaying an old decision.
    snap_map: dict[str, dict] = {}
    good_map: dict[str, dict] = {}
    for item in snapshots:
        snap_map[item["source"]] = item
        if item.get("ok"):
            good_map[item["source"]] = item
    usable: dict[str, dict | None] = {}
    for source in SOURCE_MAX_AGE_SECONDS:
        usable[source] = good_map.get(source) or snap_map.get(source)

    inputs: list[dict] = []
    missing: list[dict] = []
    active_alerts: list[dict] = []
    confidence_reasons: list[str] = []
    all_fresh = True
    for source in ["NWS alerts", "NWS forecast grid", "NWS hourly forecast", "USGS gauge", "NWS flood categories"]:
        if source.startswith("USGS") or source == "NWS flood categories":
            if not facility.get("gauge"):
                continue
        max_age = SOURCE_MAX_AGE_SECONDS.get(source, 600)
        snapshot = usable.get(source)
        age = _age_seconds(snapshot, now)
        is_fresh = bool(snapshot and snapshot.get("ok") and age is not None and age <= max_age)
        if not is_fresh:
            all_fresh = False
            last_good = good_map.get(source)
            last_id = last_good.get("id") if last_good else None
            good_age = _age_seconds(last_good, now) if last_good else None
            missing.append({
                "source": source,
                "reason": "No successful snapshot available" if not snapshot or not snapshot.get("ok") else f"Last successful snapshot is older than {max_age} seconds",
                "last_good_snapshot_id": last_id,
                "last_good_age_minutes": round(good_age / 60, 1) if good_age is not None else None,
                "max_age_minutes": round(max_age / 60, 1),
            })
            confidence_reasons.append(f"{source} is missing or stale")
        if not snapshot:
            continue
        raw = snapshot.get("raw_payload_json") or {}
        fetched_local = _local_time(snapshot.get("fetched_at_wall"), tzname)
        input_id = f"in_{len(inputs) + 1}"
        if source == "NWS alerts":
            active_alerts = normalize_alerts(raw) if snapshot.get("ok") else []
            inputs.append({
                "id": input_id, "role": "drove" if active_alerts else "context",
                "source": source, "label": "Active NWS alerts at facility point",
                # DEPRECATED(closureiq): per-alert onset/ends were dropped, so the UI could only show one combined window.
                # "value": [{k: a.get(k) for k in ("id", "event", "headline", "severity", "certainty", "urgency", "tier", "hazard")} for a in active_alerts],
                "value": [{k: a.get(k) for k in ("id", "event", "headline", "severity", "certainty", "urgency", "tier", "hazard", "onset", "ends")} for a in active_alerts],
                "onset": min((a.get("onset") for a in active_alerts if a.get("onset")), default=None),
                "ends": max((a.get("ends") for a in active_alerts if a.get("ends")), default=None),
                "fetched_at": fetched_local, "snapshot_id": snapshot.get("id"), "stale": not is_fresh,
            })
        elif source == "NWS forecast grid":
            inputs.append({"id": input_id, "role": "context", "source": source,
                           "label": "NWS gridpoint forecast values", "value": _grid_summary(raw), "unit": None,
                           "fetched_at": fetched_local, "snapshot_id": snapshot.get("id"), "stale": not is_fresh})
        elif source == "NWS hourly forecast":
            properties = raw.get("properties") or {}
            periods = properties.get("periods") or []
            hourly_values = []
            for period in periods[:24]:
                pop = period.get("probabilityOfPrecipitation") or {}
                hourly_values.append({
                    "start_time": period.get("startTime"),
                    "end_time": period.get("endTime"),
                    "temperature": period.get("temperature"),
                    "temperature_unit": period.get("temperatureUnit"),
                    "wind_speed": period.get("windSpeed"),
                    "wind_direction": period.get("windDirection"),
                    "precipitation_probability": pop.get("value"),
                    "short_forecast": period.get("shortForecast"),
                })
            inputs.append({"id": input_id, "role": "context", "source": source,
                           "label": "NWS hourly forecast (next 24 periods)", "value": hourly_values, "unit": None,
                           "fetched_at": fetched_local, "snapshot_id": snapshot.get("id"), "stale": not is_fresh})
        elif source == "USGS gauge":
            gauge_value = extract_usgs_latest(raw) if snapshot.get("ok") else None
            inputs.append({"id": input_id, "role": "context", "source": source,
                           "label": f"USGS gauge {facility['gauge']['usgs_site']}", "value": gauge_value,
                           "unit": None, "fetched_at": fetched_local, "snapshot_id": snapshot.get("id"), "stale": not is_fresh})
        elif source == "NWS flood categories":
            props = raw.get("gauge") or raw.get("properties") or raw
            inputs.append({"id": input_id, "role": "context", "source": source,
                           "label": f"NWPS flood categories {facility['gauge']['nwps_id']}", "value": props,
                           "unit": None, "fetched_at": fetched_local, "snapshot_id": snapshot.get("id"), "stale": not is_fresh})

    # Supplementary measured signal: wind at the facility's airport station. Missing data is reported as
    # missing evidence but, unlike the required NWS sources above, does not force the posture.
    observation = None
    station = facility.get("observation_station")
    if station:
        obs_snapshot = usable.get("NWS station observations")
        if obs_snapshot and obs_snapshot.get("ok"):
            observation = _observed_wind(obs_snapshot.get("raw_payload_json") or {}, str(station), now)
        if obs_snapshot:
            inputs.append({"id": f"in_{len(inputs) + 1}", "role": "context", "source": "NWS station observations",
                           "label": f"Measured wind at {station} weather station (last {OBSERVATION_WINDOW_MINUTES} min)",
                           "value": observation, "unit": "mph",
                           "fetched_at": _local_time(obs_snapshot.get("fetched_at_wall"), tzname),
                           "snapshot_id": obs_snapshot.get("id"), "stale": observation is None})
        if observation is None:
            missing.append({
                "source": "NWS station observations",
                "reason": f"No measurement from {station} in the last {OBSERVATION_WINDOW_MINUTES} minutes",
                "last_good_snapshot_id": obs_snapshot.get("id") if obs_snapshot else None,
                "last_good_age_minutes": None, "max_age_minutes": OBSERVATION_WINDOW_MINUTES,
            })
            confidence_reasons.append(f"Measured wind at {station} is unavailable")

    # Find numeric wind/ice triggers in upcoming grid periods.
    forecast_snapshot = usable.get("NWS forecast grid")
    forecast_fields = _grid_summary(forecast_snapshot.get("raw_payload_json") or {}) if forecast_snapshot and forecast_snapshot.get("ok") else {}
    forecast_fields = _apply_grid_overrides(forecast_fields, inputs, overrides)
    numeric_trigger = False
    threshold_crossed: list[dict] = []
    for field_name, threshold_id, cutoff, unit, hazard in [
        ("windGust", "T4", 58.0, "mph", "thunderstorm and wind"),
        ("windSpeed", "T5", 40.0, "mph", "thunderstorm and wind"),
        ("iceAccumulation", "T6", 0.25, "in", "winter storm"),
    ]:
        periods = forecast_fields.get(field_name, [])
        candidates = [p for p in periods if isinstance(p.get("value"), (int, float))]
        if candidates:
            max_item = max(candidates, key=lambda p: p["value"])
            if max_item["value"] >= cutoff:
                numeric_trigger = True
                matching_input = next((i for i in inputs if i["source"] == "NWS forecast grid"), None)
                threshold_crossed.append({"id": threshold_id, "input_id": matching_input["id"] if matching_input else "in_1",
                    "cutoff": cutoff, "actual": max_item["value"], "unit": unit,
                    "margin": round(max_item["value"] - cutoff, 3), "anchor": "MVP threshold; confirm local NWS criteria", "anchor_url": None})

    # Measured wind counts as a numeric trigger too: the T4/T5 anchors describe gusts and winds that occur.
    observed_not_crossed: list[dict] = []
    obs_input = next((i for i in inputs if i["source"] == "NWS station observations"), None)
    if observation and obs_input:
        for key, threshold_id, cutoff in (("max_gust_mph", "T4", 58.0), ("max_sustained_mph", "T5", 40.0)):
            actual = observation[key]
            if actual >= cutoff:
                numeric_trigger = True
                obs_input["role"] = "drove"
                threshold_crossed.append({"id": threshold_id, "input_id": obs_input["id"], "cutoff": cutoff, "actual": actual,
                    "unit": "mph", "margin": round(actual - cutoff, 3),
                    "anchor": "MVP threshold; confirm local NWS criteria", "anchor_url": None})
            else:
                observed_not_crossed.append({"id": threshold_id, "input_id": obs_input["id"], "cutoff": cutoff,
                    "actual": actual, "unit": "mph", "distance": round(cutoff - actual, 3)})

    active_alerts, assumed_alert = _apply_alert_override(active_alerts, inputs, overrides, now)
    strongest = max(active_alerts, key=lambda a: (
        {"none": 0, "advisory": 1, "watch": 2, "warning": 3}.get(a.get("tier"), 0),
        SEVERITY_RANK.get(str(a.get("severity") or "unknown").lower(), 0)), default=None)
    posture = "normal_operations"
    raw_posture = posture
    safety_instruction = None
    decision_needed = False
    headline = "No active NWS alerts were found for this facility point."
    high_confidence_alert = False
    strong_warning = False
    window_posture = None
    if strongest:
        headline = str(strongest.get("headline") or strongest.get("event") or "Active NWS alert")
        tier = strongest.get("tier", "advisory")
        severity = str(strongest.get("severity") or "unknown").lower()
        certainty = str(strongest.get("certainty") or "unknown").lower()
        onset = parse_datetime(strongest.get("onset")) or now
        ends = parse_datetime(strongest.get("ends")) or parse_datetime(strongest.get("expires")) or (now + timedelta(hours=1))
        strong_warning = tier == "warning" and severity in {"severe", "extreme"} and certainty in {"likely", "observed"}
        high_confidence_alert = strong_warning and (numeric_trigger or tier == "warning")
        # Alert checks T1-T3 (architecture thresholds table), recorded so the UI can show what drove the call.
        alert_input = next((i for i in inputs if i["source"] == "NWS alerts"), None)
        for threshold_id, cutoff, actual, passed in (
            ("T1", "Warning", str(tier).title(), tier == "warning"),
            ("T2", "Severe or Extreme", str(strongest.get("severity") or "Unknown"), severity in {"severe", "extreme"}),
            ("T3", "Likely or Observed", str(strongest.get("certainty") or "Unknown"), certainty in {"likely", "observed"}),
        ):
            item = {"id": threshold_id, "input_id": alert_input["id"] if alert_input else "in_1", "cutoff": cutoff, "actual": actual}
            (threshold_crossed if passed else observed_not_crossed).append(item)
        threshold_crossed.sort(key=lambda t: int(str(t["id"]).lstrip("T") or 0))
        # Which commute windows the hazard covers decides delay, dismissal or closure (posture table timing).
        departure_overlap = _interval_overlaps(onset, ends, facility["departure_window"]["start"], facility["departure_window"]["end"], local_now)
        arrival_overlap = _interval_overlaps(onset, ends, facility["arrival_window"]["start"], facility["arrival_window"]["end"], local_now)
        window_posture = ("closure" if arrival_overlap and departure_overlap else "delayed_arrival" if arrival_overlap
                          else "early_dismissal" if departure_overlap else None)
        # DEPRECATED(closureiq) START: a strong warning drove delay/dismissal/closure even with no numeric
        # trigger crossed; the architecture posture table requires one (else unscheduled leave or telework).
        # if strong_warning:
        #     decision_needed = True
        #     departure_overlap = _interval_overlaps(onset, ends, facility["departure_window"]["start"], facility["departure_window"]["end"], local_now)
        #     arrival_overlap = _interval_overlaps(onset, ends, facility["arrival_window"]["start"], facility["arrival_window"]["end"], local_now)
        #     if arrival_overlap and departure_overlap:
        #         posture = "closure"
        #     elif arrival_overlap:
        #         posture = "delayed_arrival"
        #     elif departure_overlap:
        #         posture = "early_dismissal"
        #     elif onset <= now <= ends:
        #         posture = "normal_operations"
        #         safety_instruction = "Shelter in place and follow official instructions while the active warning remains in effect."
        #     else:
        #         posture = "unscheduled_leave_or_telework"
        # DEPRECATED(closureiq) END
        if strong_warning and numeric_trigger:
            decision_needed = True
            if window_posture:
                posture = window_posture
            elif onset <= now <= ends:
                posture = "normal_operations"
                safety_instruction = "Shelter in place and follow official instructions while the active warning remains in effect."
            else:
                posture = "unscheduled_leave_or_telework"
        elif strong_warning:
            # Warning without a crossed numeric trigger: posture table row "Unscheduled leave or telework".
            decision_needed = True
            posture = "unscheduled_leave_or_telework"
            # Life safety does not wait for a numeric trigger: a warning in effect now, outside the commute
            # windows, still gets the shelter-in-place line (architecture timing rule).
            if window_posture is None and onset <= now <= ends:
                safety_instruction = "Shelter in place and follow official instructions while the active warning remains in effect."
        elif tier == "watch":
            posture = "normal_operations"
        elif tier == "warning" or (numeric_trigger and not high_confidence_alert):
            posture = "unscheduled_leave_or_telework"
            decision_needed = True
        else:
            posture = "normal_operations"
        if tier == "warning" and onset <= now + timedelta(minutes=30):
            # Generic advice only when the engine has not already set a real
            # "Shelter in place" instruction (that line must reach the record).
            if safety_instruction is None:
                safety_instruction = "Follow official NWS instructions; seek appropriate shelter if directed."
            decision_needed = True
        if posture == "normal_operations" and tier == "watch":
            headline = f"Watch active: {headline}"
    # Contract rule: never show a calm green recommendation beside failed/stale required evidence.
    # The shared engine owns final policy; this conservative fallback requests human review whenever
    # any required source is unavailable/stale.
    alert_source_ok = any(i["source"] == "NWS alerts" and not i["stale"] for i in inputs)
    if not all_fresh:
        posture = "unscheduled_leave_or_telework"
        decision_needed = True
        problem_sources = ", ".join(m["source"] for m in missing)
        headline = f"Required weather evidence is missing or stale: {problem_sources}. Human review is required."
    elif not alert_source_ok:
        posture = "unscheduled_leave_or_telework"
        decision_needed = True
        headline = "NWS alert evidence is missing or stale; human review is required."
    raw_posture = posture

    # Hysteresis is owned by Samanth's engine. This fallback preserves current posture instead of
    # implementing a second competing hysteresis algorithm.
    held = False
    if previous_result and POSTURE_RANK.get(posture, 0) < POSTURE_RANK.get(previous_result.get("posture", "normal_operations"), 0):
        held = False  # Explicitly left to the official engine adapter.

    if not all_fresh:
        confidence_level = "low"
    elif strongest and str(strongest.get("certainty") or "unknown").lower() in {"unlikely", "unknown"}:
        confidence_level = "low"
        confidence_reasons.append(f"NWS certainty is {strongest.get('certainty')}")
    elif strongest and str(strongest.get("certainty") or "unknown").lower() == "possible":
        confidence_level = "medium"
        confidence_reasons.append("NWS certainty is Possible")
    elif strongest:
        onset = parse_datetime(strongest.get("onset"))
        if onset and (onset - now).total_seconds() > 36 * 3600:
            confidence_level = "low"
            confidence_reasons.append("Alert onset is more than 36 hours away")
        elif onset and (onset - now).total_seconds() > 12 * 3600:
            confidence_level = "medium"
            confidence_reasons.append("Alert onset is 12 to 36 hours away")
        else:
            confidence_level = "high"
            confidence_reasons.append("NWS alert certainty is Likely or Observed and sources are fresh")
    else:
        confidence_level = "high"
        confidence_reasons.append("Latest NWS alerts snapshot is fresh and contains no active alerts")
    if not confidence_reasons:
        confidence_reasons = ["No active alert signals were returned by NWS."]

    decision_deadline = _next_work_deadline(facility, local_now) if decision_needed else None
    params: dict[str, Any] = {"next_update": (local_now + timedelta(minutes=15 if strongest and strongest.get("tier") == "warning" else 60)).isoformat()}
    if posture == "normal_operations":
        params["monitoring"] = "elevated" if strongest and strongest.get("tier") == "watch" else "normal"
    elif posture == "delayed_arrival":
        params["delay_until"] = _local_time((parse_datetime(strongest.get("ends")) or (now + timedelta(minutes=60))).isoformat(), tzname) if strongest else None
    elif posture == "early_dismissal":
        # DEPRECATED(closureiq): "now + 30 min" moved on every run, so each poll looked like a new decision.
        # params["dismiss_at"] = _local_time((now + timedelta(minutes=30)).isoformat(), tzname)
        # Architecture posture table: dismiss_at = hazard onset - commute buffer.
        onset_at = parse_datetime(strongest.get("onset")) if strongest else None
        params["dismiss_at"] = (
            _local_time((onset_at - timedelta(minutes=int(facility.get("commute_buffer_min", 45)))).isoformat(), tzname)
            if onset_at else None
        )
    elif posture == "closure":
        # DEPRECATED(closureiq) START: closed_from was "now", so every poll looked like a new decision.
        # params["closed_from"] = local_now.isoformat()
        # params["closed_until"] = _local_time((parse_datetime(strongest.get("ends")) or (now + timedelta(hours=2))).isoformat(), tzname) if strongest else None
        # DEPRECATED(closureiq) END
        # Architecture posture table: closure runs from facility open to close on the facility's local day.
        open_h, open_m = map(int, facility["hours"]["open"].split(":"))
        close_h, close_m = map(int, facility["hours"]["close"].split(":"))
        params["closed_from"] = datetime.combine(local_now.date(), time(open_h, open_m), tzinfo=local_now.tzinfo).isoformat()
        params["closed_until"] = datetime.combine(local_now.date(), time(close_h, close_m), tzinfo=local_now.tzinfo).isoformat()

    # Contracts ask for snapshot IDs on every input. Numeric threshold references point to grid input.
    not_crossed: list[dict] = []
    grid_input = next((i for i in inputs if i["source"] == "NWS forecast grid"), None)
    if grid_input:
        for tid, cutoff, field, unit in [("T4", 58.0, "windGust", "mph"), ("T5", 40.0, "windSpeed", "mph"), ("T6", 0.25, "iceAccumulation", "in")]:
            values = [p["value"] for p in forecast_fields.get(field, []) if isinstance(p.get("value"), (int, float))]
            if values and max(values) < cutoff:
                not_crossed.append({"id": tid, "input_id": grid_input["id"], "cutoff": cutoff, "actual": max(values), "unit": unit, "distance": round(cutoff - max(values), 3)})

    not_crossed.extend(observed_not_crossed)

    flips = []
    if strong_warning and not numeric_trigger and window_posture:
        flips.append({"change": "Measured or forecast wind gusts reach 58 mph, or sustained winds reach 40 mph",
                      "resulting_posture": window_posture,
                      "note": "The warning already covers the commute windows; only a crossed numeric threshold is missing."})
    if strongest and strongest.get("tier") == "warning":
        flips.append({"change": "NWS warning is downgraded to a Watch", "resulting_posture": "normal_operations", "note": "Fallback policy; confirm with the shared engine."})
    if not alert_source_ok:
        flips.append({"change": "NWS alert source returns a fresh successful response", "resulting_posture": "normal_operations", "note": "Re-evaluate with current evidence before deciding."})
    if numeric_trigger:
        # DEPRECATED(closureiq): wording assumed the trigger was a forecast; it can now be a measurement too.
        # flips.append({"change": "Forecast value falls below the numeric trigger", "resulting_posture": "unscheduled_leave_or_telework", "note": "Numeric values must be confirmed against sourced local criteria."})
        flips.append({"change": "Measured and forecast values fall below the numeric thresholds", "resulting_posture": "unscheduled_leave_or_telework", "note": "Numeric values must be confirmed against sourced local criteria."})
    if not flips:
        flips.append({"change": "A warning or numeric threshold appears in fresh evidence", "resulting_posture": "unscheduled_leave_or_telework", "note": "Re-evaluate when evidence changes."})

    alerts_for_text = ", ".join(f"{a.get('event')} ({a.get('severity')}, certainty {a.get('certainty')})" for a in active_alerts[:3]) or "no active alerts"
    rationale = (
        f"MVP fallback recommends {posture.replace('_', ' ')} for {facility['name']}. "
        f"NWS point alerts: {alerts_for_text}. Confidence is {confidence_level}. "
        + (f"Missing or stale evidence: {', '.join(m['source'] for m in missing)}. " if missing else "All applicable sources are fresh. ")
        + ("A human must review the recommendation before any action is taken." if decision_needed else "No automatic operational action is taken.")
    )
    result = {
        "hypothetical": bool(hypothetical), "evaluation_id": None, "supersedes": None,
        "facility_id": facility["facility_id"], "evaluated_at": local_now.isoformat(),
        "policy_version": facility.get("policy_version", "policy-2026-10-10.1"),
        "data_mode": data_mode or (snapshots[-1].get("data_mode") if snapshots else store.get_data_mode("live")), "posture": posture, "raw_posture": raw_posture,
        "held_by_hysteresis": held, "parameters": params,
        "safety_instruction": safety_instruction, "decision_deadline": decision_deadline,
        "confidence": {"level": confidence_level, "reasons": confidence_reasons},
        "inputs": inputs, "thresholds_crossed": threshold_crossed,
        "thresholds_not_crossed": not_crossed, "missing_evidence": missing,
        "flip_list": flips, "rationale": rationale,
        "engine_version": "badri-fallback-0.1",
        "headline": headline,
    }
    if overrides:
        for input_item in result["inputs"]:
            if input_item["id"] in overrides:
                new_value = overrides[input_item["id"]]
                if input_item["source"] == "NWS alerts" and isinstance(new_value, dict):
                    input_item["value"] = [{k: a.get(k) for k in ("id", "event", "headline", "severity", "certainty",
                                                                   "urgency", "tier", "hazard")} for a in active_alerts]
                    input_item["onset"] = min((a["onset"] for a in active_alerts if a.get("onset")), default=None)
                    input_item["ends"] = max((a["ends"] for a in active_alerts if a.get("ends")), default=None)
                    input_item["role"] = "drove" if active_alerts else "context"
                elif input_item["source"] == "NWS forecast grid" and isinstance(new_value, dict):
                    # Show the overridden grid fields next to the untouched ones.
                    input_item["value"] = {**(input_item["value"] or {}),
                                           **_grid_override_periods(new_value)}
                else:
                    input_item["value"] = new_value
                input_item["stale"] = False if new_value is not None else True
        # Grid numbers (wind gust, sustained wind, ice) are re-checked against T4-T6 above;
        # other overridden inputs are shown but do not re-run the alert logic.
        result["rationale"] += f" What-if overrides applied to {', '.join(sorted(overrides))}."
        if assumed_alert:
            result["assumed_alert"] = assumed_alert
    return result


def evaluate_recommendation(store, facility: dict, snapshots: list[dict], *, evaluated_at: datetime | None = None,
                            previous_result: dict | None = None, overrides: dict | None = None,
                            hypothetical: bool = False, data_mode: str | None = None) -> dict:
    """Single seam to integrate Samanth's engine; fallback remains runnable standalone."""
    # Expected integration contract after Samanth's engine is merged:
    # api.engine.evaluate(evidence=..., facility=..., policy_version=..., now=...)
    # Keep the API from importing the agent/model directly.
    try:
        from api.engine import evaluate as shared_evaluate  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        shared_evaluate = None
    if shared_evaluate:
        try:
            return shared_evaluate(evidence=snapshots, facility=facility,
                                  policy_version=facility.get("policy_version"), now=evaluated_at,
                                  previous=previous_result, overrides=overrides,
                                  hypothetical=hypothetical, data_mode=data_mode)
        except TypeError:
            # Clear interface mismatch is documented in docs/ENGINE_INTEGRATION.md; fallback keeps MVP bootable.
            pass
    return fallback_evaluate(store, facility, snapshots, evaluated_at=evaluated_at,
                             previous_result=previous_result, overrides=overrides,
                             hypothetical=hypothetical, data_mode=data_mode)
