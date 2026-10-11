"""Unit conversions for NWS gridpoint data. Keep conversions centralized."""
from __future__ import annotations


def convert_value(value: float, source_uom: str, target: str) -> float:
    """Convert common NWS forecast units into the requested US unit.

    Unknown unit pairs are returned unchanged so callers can preserve the original unit.
    """
    uom = (source_uom or "").lower()
    if target == "mph":
        if "km_h-1" in uom or "km/h" in uom:
            return value * 0.621371
        if "m_s-1" in uom or "m/s" in uom:
            return value * 2.236936
        if "mi_h-1" in uom or "mph" in uom:
            return value
    elif target == "in":
        if "mm" in uom:
            return value / 25.4
        if "kg_m-2" in uom:  # Water-equivalent depth: 1 kg/m² = 1 mm water.
            return value / 25.4
        if "cm" in uom:
            return value / 2.54
        if "in" in uom:
            return value
    elif target == "F":
        if "degc" in uom or "celsius" in uom:
            return value * 9 / 5 + 32
        if "degf" in uom or "fahrenheit" in uom:
            return value
    return value


def target_unit_for_field(field_name: str) -> tuple[str | None, str | None]:
    normalized = field_name.lower()
    if normalized in {"windspeed", "windgust"}:
        return "mph", "mph"
    if normalized in {"iceaccumulation", "snowfallamount"}:
        return "in", "in"
    if normalized == "temperature":
        return "F", "°F"
    return None, None
