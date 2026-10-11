"""Contract-shaped threshold catalogue. Numeric local-office criteria remain confirm/assumption."""
POLICY_VERSION = "policy-2026-10-10.1"
THRESHOLDS = [
    {"id": "T1", "hazard": "all", "input": "NWS alert tier", "cutoff": "warning", "unit": None,
     "effect": "Allows delay, dismissal or closure", "anchor": "NWS warning definition", "anchor_url": None, "status": "confirm"},
    {"id": "T2", "hazard": "all", "input": "NWS severity", "cutoff": "Severe or Extreme", "unit": None,
     "effect": "Allows dismissal and closure", "anchor": "NWS alert severity field", "anchor_url": None, "status": "confirm"},
    {"id": "T3", "hazard": "all", "input": "NWS certainty", "cutoff": "Likely or Observed", "unit": None,
     "effect": "Required for posture above unscheduled leave/telework", "anchor": "NWS alert certainty field", "anchor_url": None, "status": "confirm"},
    {"id": "T4", "hazard": "thunderstorm and wind", "input": "Forecast wind gust", "cutoff": 58, "unit": "mph",
     "effect": "Numeric trigger", "anchor": "Typical NWS severe-thunderstorm wind criterion", "anchor_url": None, "status": "confirm"},
    {"id": "T5", "hazard": "thunderstorm and wind", "input": "Sustained wind for 1 hour", "cutoff": 40, "unit": "mph",
     "effect": "Numeric trigger", "anchor": "Typical NWS high-wind warning criterion; offices vary", "anchor_url": None, "status": "confirm"},
    {"id": "T6", "hazard": "winter storm", "input": "Ice accumulation", "cutoff": 0.25, "unit": "in",
     "effect": "Numeric trigger", "anchor": "Typical NWS ice-storm warning criterion", "anchor_url": None, "status": "confirm"},
    {"id": "T7", "hazard": "flood", "input": "Gauge stage", "cutoff": 32, "unit": "ft",
     "effect": "Numeric trigger at KCDM7", "anchor": "NWS flood category for gauge KCDM7", "anchor_url": None, "status": "verified"},
    {"id": "T8", "hazard": "flood", "input": "Gauge stage", "cutoff": 35, "unit": "ft",
     "effect": "Counts as extreme severity at KCDM7", "anchor": "NWS flood category for gauge KCDM7", "anchor_url": None, "status": "verified"},
    {"id": "T9", "hazard": "flood", "input": "Gauge stage", "cutoff": 29, "unit": "ft",
     "effect": "Raises monitoring only", "anchor": "NWS action stage for gauge KCDM7", "anchor_url": None, "status": "verified"},
    {"id": "T10", "hazard": "all", "input": "Clearing buffer", "cutoff": 60, "unit": "min",
     "effect": "Sets delay_until", "anchor": "Team choice", "anchor_url": None, "status": "assumption"},
    {"id": "T11", "hazard": "all", "input": "Commute buffer / notification lead", "cutoff": {"commute_buffer_min": 45, "notification_lead_min": 90}, "unit": "min",
     "effect": "Sets decision deadline", "anchor": "Team choice in facility profile", "anchor_url": None, "status": "assumption"},
]


def thresholds_response() -> dict:
    return {"policy_version": POLICY_VERSION, "thresholds": THRESHOLDS}
