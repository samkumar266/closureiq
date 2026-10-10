# Thresholds and where they come from

The engine reads these values from `api/engine/policy.yaml` (policy version `policy-2026-10-10.1`). This page explains them in plain words. Checked on 2026-10-10.

**What the statuses mean**

- **Verified:** the number was read from the cited page on the check date.
- **Confirm:** typical value. Read the cited page, or the local office page, before the pitch.
- **Assumption:** a team choice. We say so out loud in the pitch.

| ID | Hazard | Input | Cutoff | Effect | Source | Status |
|---|---|---|---|---|---|---|
| T1 | All | NWS alert tier | Warning | Allows delay, dismissal or closure | [NWS definitions](https://weather.gov/dtx/wwa_defs): a Warning is issued when a hazardous event is occurring or has a very high probability of occurrence | Verified |
| T2 | All | NWS severity field | Severe or Extreme | Allows dismissal and closure | [OASIS CAP v1.2](https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.html): Severe is a significant threat to life or property | Assumption (field meanings verified, cutoff is ours) |
| T3 | All | NWS certainty field | Likely or Observed | Needed for any posture above unscheduled leave or telework | [OASIS CAP v1.2](https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.html): Likely is p above about 50% | Assumption (field meanings verified, cutoff is ours) |
| T4 | Thunderstorm and wind | Forecast wind gust | 58 mph or more | Numeric trigger | NWS [Kansas City](https://www.weather.gov/eax/eaxwwacriteria) and [St. Louis](https://www.weather.gov/lsx/criteria): 58 mph (50 kt) gusts | Verified for Kansas City and St. Louis. Confirm Omaha |
| T5 | Thunderstorm and wind | Sustained wind | 40 mph or more for 1 hour | Numeric trigger | NWS [Kansas City](https://www.weather.gov/eax/eaxwwacriteria) and [St. Louis](https://www.weather.gov/lsx/criteria): High Wind Warning | Verified for Kansas City and St. Louis. Confirm Omaha |
| T6 | Winter storm | Ice accumulation | 0.25 in or more | Numeric trigger | NWS [Kansas City](https://www.weather.gov/eax/eaxwwacriteria2), [St. Louis](https://www.weather.gov/lsx/criteria) and [Omaha](https://www.weather.gov/oax/winter-products): Ice Storm Warning at 1/4 inch | Verified |
| T7 | Flood | Gauge stage | 32 ft (minor flood) | Numeric trigger | [NWPS gauge KCDM7](https://api.water.noaa.gov/nwps/v1/gauges/KCDM7) | Verified |
| T8 | Flood | Gauge stage | 35 ft (moderate flood) | Counts as severity Extreme | [NWPS gauge KCDM7](https://api.water.noaa.gov/nwps/v1/gauges/KCDM7) | Verified stage. Treating it as Extreme is our choice |
| T9 | Flood | Gauge stage | 29 ft (action stage) | Raises monitoring only | [NWPS gauge KCDM7](https://api.water.noaa.gov/nwps/v1/gauges/KCDM7) | Verified |
| T10 | All | Clearing buffer | 60 min after the hazard ends | Sets `delay_until` | Team choice | Assumption |
| T11 | All | Commute buffer and notification lead | 45 min and 90 min | Sets the decision deadline | Team choice, stored in the facility profile | Assumption |
| T12 | Winter storm | Forecast snowfall | 5 in or more | Numeric trigger (new, proposed) | NWS [Kansas City](https://www.weather.gov/eax/eaxwwacriteria2) and [St. Louis](https://www.weather.gov/lsx/criteria): 5 in. Omaha: 5 to 6 in by location | Confirm Omaha |

The river gauge applies only to the Kansas City facility. The other two facilities have no gauge in the demo.

## Changes and open items

- **T12 is new.** The architecture doc left the snowfall cutoff out on purpose, because a cutoff needs a source. Kansas City and St. Louis both use 5 inches, so it is sourced now. Samanth decides whether the engine uses it.
- **Omaha pages.** The Omaha office's wind criteria page would not load, so T4 and T5 are verified for two of the three offices only. Check [weather.gov/oax](https://www.weather.gov/oax) before the pitch, or say that Kansas City values are used for all three.
- **T1 source.** The cited definitions page belongs to the Detroit/Pontiac office. The wording is NWS-wide, but a national page would be a cleaner citation if one turns up.
- **Kansas City note on T5.** The office says its High Wind Warning covers winds not directly associated with thunderstorms. Our engine groups thunderstorm and non-thunderstorm wind together, which is a simplification.
- **Not in this file yet.** The drafted employee messages per group and posture belong to the notification builder (HAC-40).

## Say this in the pitch

- The five postures and their order are modeled on OPM operating-status categories. They are our assumption, not USDA policy.
- Every number the system shows cites a published NWS or NOAA source, except T2, T3, T8 (the Extreme label), T10 and T11, which are marked as our choices.
- The engine is deterministic, so the same evidence always gives the same recommendation.
