> Exported from the ClosureIQ architecture doc on 2026-10-10. Diagrams are shown as [embed] placeholders. The doc is the source of truth if the two differ.

# ClosureIQ: MVP Architecture (Hack Midwest 2026)
 · 
## MVP scope
The demo must show one facility getting a live, explainable closure recommendation from real NWS data, a manager approving it, a notification package going out, and a record that replays identically. Everything else is cut or simulated.
In the MVP
- Live NWS alerts and gridpoint forecast for one facility template placed at three locations, so something is always under a real alert.
- Three hazards: severe thunderstorm and wind, winter storm, flood.
- One supplementary signal beyond NWS (chosen in the data layer section).
- A deterministic policy engine with a sourced thresholds table. It outputs one of five postures plus parameters, such as delay until 10:00.
- A recommendation card with inputs, source and timestamp for each, thresholds crossed and by how much, confidence, what would change it, and a paste-ready rationale.
- A Strands agent that explains the result and runs what-if scenarios by calling the engine.
- Approve, reject or override, with a required reason on override.
- A notification package with who is in or out and why, drafted messages and channel routing.
- A delivery simulator with acknowledgments, one escalation path and a simulated clock.
- An append-only decision record with a replay button.
Deliberately out
- Real SMS and voice. Carrier registration and trial-account limits can eat hours, so email is the only real channel, if any.
- Escalation beyond primary manager to backup manager.
- Flood-exposure mapping, clock-in data and employee home addresses.
- Real authentication. Demo roles are enough.
- More facility types or hazards.
Where each official deliverable lives
| Official deliverable | Section |
| 1. Working system on live NWS data | Data layer |
| 2. Recommendation with reasoning | Policy engine, Recommendation object |
| 3. Notification package | Notification package |
| 4. Decision record | Decision record |
| 5. Threshold defensibility | Policy engine (thresholds table) |
## System overview
ClosureIQ is one loop: fetch live evidence, store it untouched, decide with fixed rules, let a person approve, notify and escalate, and record everything. The picture shows where each piece lives; the numbered walkthrough follows one assessment from first fetch to final record.
[embed]
Read it left to right: sources feed the poller, the poller feeds the store, the store feeds the engine, and only a human approval reaches the notification stage.
### One live assessment, step by step
- Fetch. The poller (APScheduler) calls the NWS alerts, hourly forecast and grid-data endpoints for the facility's latitude and longitude, plus the USGS stream gauge and the NWPS flood categories. In REPLAY mode it reads recorded payloads from mocks/ instead.
- Store. Every response, including failures and empty results, is written untouched to evidence_snapshots with its fetch time (wall and simulated) and the source's own update time.
- Normalize. Small parsers turn the stored payloads into one typed evidence object: alert tier and onset, forecast values for the commute window, gauge height against the flood categories, and the age of each input.
- Decide. The policy engine, a pure function, takes the evidence, facility profile, roster, thresholds and the current time. It returns the posture, which thresholds were crossed and by how much, the confidence with reasons, what would flip the call, the decision deadline and a template-built rationale. Hysteresis compares it with the previous evaluation so the posture does not flicker.
- Publish. The evaluation is appended to evaluations and pushed over SSE. The Watchlist re-sorts and the facility screen updates without a refresh.
- Explain on request. The Strands agent can read the evaluation and its evidence through read-only tools, answer questions and run what-if scenarios through the same engine. It cannot change a posture, approve or send anything, and a validator checks that every number in its answer appears in the evaluation.
- Approve. The Approver sees the recommendation, the evidence and the notification preview, then approves, rejects or overrides (reason required for the last two). An approval is tied to one evaluation id; if a newer evaluation has appeared, the API answers 409 stale_evaluation and the screen asks for another look.
- Notify. Approval builds the notification package: recipients by group, message text, channel routing. Email goes out for real; SMS, push and calls go through the delivery simulator. Escalation timers are inserted for anyone who does not acknowledge.
- Escalate. A scheduler checks the timers table every second against the simulated clock. When a timer is due, the manager and supervisors get the list of people who have not acknowledged, with the option to resend by another channel; if the manager has not responded to the recommendation, the backup manager is notified. The tracker updates over SSE.
- Record. Every step above is a row in the decision record. Replay re-runs the stored evidence through the engine and shows that the result is identical.
### Four rules that shape every other section
- Rules decide, the model explains. The posture comes from a rule table with named thresholds. The language model reads the result; it never produces it.
- Nothing defaults to normal. A missing or stale source lowers confidence and says so on screen. It never quietly reports that all is well.
- Every number carries its source and time. The UI, the notification and the record all show where a value came from and how old it is.
- Two clocks. Evidence freshness uses real time. Escalation and deadlines use a simulated clock that can run fast, so the 3-minute demo can show a full escalation.
## Tech stack and repo layout
One Python backend and one React frontend keep the stack small enough for four people in about 20 hours. Python is forced by the Strands SDK, so ingestion, the engine and the agent share one language.
| Layer | Choice | Why |
| Backend | Python 3.11+, FastAPI | Strands is a Python SDK; FastAPI gives typed endpoints and free OpenAPI docs |
| Policy engine | Plain Python functions, no I/O | Deterministic, unit-testable, replayable |
| Database | SQLite, append-only tables | One file, no setup, easy to reset before the demo |
| Jobs | APScheduler inside the API process | Polling and escalation timers, driven by a swappable clock |
| Live updates | Server-Sent Events | One-way push to the dashboard, simpler than WebSockets |
| Frontend | React, Vite, TypeScript, Tailwind | Fast to scaffold, no server rendering needed |
| Agent | Strands Agents SDK | Eligible for the AWS challenge; model provider picked from the credits sponsors hand out |
| Email | One provider through SMTP or an API key | The only real channel; everything else is simulated |
Run the demo from one laptop on a phone hotspot. Deploying to a public URL is optional.
```
/frontend            React app: dashboard, approval, notifications, record
/api
  /app               FastAPI routers and wiring
  /ingest            NWS and supplementary clients, raw snapshot storage
  /engine            deterministic policy engine, thresholds.yaml, replay
  /notify            recipient resolver, templates, simulator, escalation
  /store             SQLite models and append-only helpers
  clock.py           real clock and simulated clock
/ai                  Strands agent and its tool wrappers
/mocks               synthetic facilities and roster, recorded real payloads
/docs                contract.md, thresholds.md, this architecture
```
Four lanes, so no two people edit the same files
| Lane | Folders | Owns |
| A. Data and engine | api/ingest, api/engine | NWS and USGS clients, snapshots, thresholds, posture logic, replay |
| B. Notify and record | api/notify, api/store | roster, recipient rules, templates, simulator, escalation, clock, database |
| C. Frontend | frontend | dashboard, recommendation card, approval, notification view, record timeline, chat panel |
| D. Agent and integration | ai, docs, wiring in api/app | Strands agent, contract, seed data, demo script (Suraj, per AGENTS.md) |
Who owns what (set Saturday 12:07 PM). The lanes above were regrouped by person. Badri owns api/ingest, api/store and api/app. Samanth owns api/engine and ai. Suraj owns api/notify, docs, mocks and the deploy scripts. Kavya owns frontend. Linear holds the task list, one issue per piece, each linking back to a section of this document. Lanes talk to each other only through the functions and endpoints in the API contract section.
## Data layer
Every poll is stored raw with its fetch time before anything reads it, and the engine only ever sees normalized evidence built from those stored snapshots. That is what makes the record replayable.
| Source | Endpoint | Key | Poll | Status |
| NWS alerts | api.weather.gov/alerts/active?point=lat,lon | None; User-Agent header required | 60 s | User-Agent and no key confirmed in NWS docs; the point filter and field names need a first-call check |
| NWS forecast grid | api.weather.gov/points/lat,lon, then its forecastGridData URL | Same | 15 min | Flow confirmed in NWS docs; field names need a first-call check |
| USGS stream gauge (supplementary) | waterservices.usgs.gov/nwis/iv/?format=json&sites=06893000&parameterCd=00065,00060 | None | 15 min | Worked today with no key: 15.11 ft and 72,000 cfs at 11:30 CDT |
| NWS flood categories | api.water.noaa.gov/nwps/v1/gauges/KCDM7 | None | Once, cache 24 h | Worked today: action 29 ft, minor 32, moderate 35, major 49 |
The supplementary signal is the USGS gauge, which is a different agency from NWS. The engine compares its reading to NWS flood categories, so a flood decision carries a measured value and a sourced cutoff. Today the Kansas City reading sits 13.89 ft below action stage, which shows up as a margin, not a crossing.
Normalization rules
- Keep only alerts with status Actual. Drop Test and Exercise.
- Treat messageType Update as a replacement of the alert it references, and Cancel as removal.
- Use ends for the alert end time and fall back to expires when ends is null. Onset can be in the future.
- Map each event name to a hazard class (thunderstorm and wind, winter storm, flood) and a tier: advisory, watch or warning. Severity alone does not tell a watch from a warning.
- Convert units in one place, ingest/units.py. Forecast grid values arrive in metric units and validTime is an ISO interval such as 2026-10-10T17:00:00+00:00/PT3H.
- Store a poll that finds nothing as a snapshot with an empty result. Absence of alerts is evidence too.
Failure ladder (never silently default to normal)
- On an error or timeout, retry once after 5 seconds. NWS asks clients to retry after a rate limit clears, typically within 5 seconds.
- If the retry fails, use the last good snapshot if it is fresh enough: 10 minutes for alerts, 3 hours for forecast, 2 hours for gauges (starting values, tune them).
- Past that limit the source is marked MISSING. The engine still answers, but with Low confidence and the gap listed under missing evidence.
Modes and facility locations
- DATA_MODE=live calls the real APIs. DATA_MODE=replay serves recorded real payloads from /mocks and shows a visible REPLAY badge in the UI. Replay is only the fallback for bad venue Wi-Fi.
- The same facility template is placed at three locations. The facility picker sorts them by highest active alert tier, so the demo opens on one with a real alert.
First 15 minutes: confirm the NWS details
My fetch tool is blocked by api.weather.gov, so these field names come from the NWS and CAP specifications and are not yet checked here. Run these three calls from a team laptop and fix the contract if anything differs.
```
curl -H "User-Agent: ClosureIQ (<team contact email>)" "https://api.weather.gov/alerts/active?point=39.0997,-94.5786"
curl -H "User-Agent: ClosureIQ (<team contact email>)" "https://api.weather.gov/points/39.0997,-94.5786"
curl -H "User-Agent: ClosureIQ (<team contact email>)" "<forecastGridData URL from the previous call>"
```
Check that each alert has id, event, status, messageType, severity, certainty, urgency, onset, expires, ends, references and geocode, and that the grid has windGust, windSpeed, iceAccumulation, snowfallAmount and temperature.
## Facility and roster model
Everything about the facility and its people is synthetic, generated by one seeded script so the demo repeats exactly and no real personal data appears anywhere. The model holds only what the engine and the notifier use.
Facility profile (one template, placed at three locations)
| Field | Example | Used by |
| facility_id, name | kc-service-center | Dashboard |
| lat, lon, timezone | 39.0997, -94.5786, America/Chicago | Ingest, timing |
| hours | Open 07:30, close 16:00 local | Posture timing |
| arrival window | 07:00 to 08:30 | Delay logic |
| commute buffer (min) | 45 | Decision deadline |
| notification lead time (min) | 90 | Decision deadline |
| manager, backup, on-call | employee ids | Approval, escalation |
| gauge | USGS site 06893000, NWPS id KCDM7 | Flood evaluator |
| policy_version | policy-2026-10-10.1 | Decision record |
Employee
| Field | Meaning |
| employee_id, synthetic name | Generated, never real |
| assignment_type | assigned, detail_in, detail_out or contractor. Separates the building roster from the employee roster |
| shift_start, shift_end | Local times, so overnight and early shifts get the right lead time |
| work_status_today | onsite, telework, leave or off |
| essential | Reports regardless of posture |
| telework_eligible | False means they must report or take leave |
| commute_county | A coarse area, not a home address |
| channels | Ordered list, such as email then sms. Only email can really send |
| comm_needs | Flags only (alternate format, language). The underlying reason is never stored or shown to the manager |
| supervisor_id | Receives the escalation for non-acknowledgment |
Seed roster: 25 people, built so every notification branch has someone in it
- 4 essential staff, 3 on detail elsewhere, 2 detailed in from another office.
- 3 already teleworking, 2 on leave, 3 not telework-eligible, 2 contractors.
- 2 with communication-need flags, 2 on early or late shifts, 2 commuting from a different county.
People can fall in more than one group. The point is that the recipient list for any posture has visible reasons to include or exclude each person.
Policy file
A versioned policy.yaml defines the five postures, who is told what under each, and the lead times. It is modeled on OPM operating-status categories and is an assumption, not real USDA policy. Say so out loud in the pitch.
## Policy engine
The engine is a pure function: evidence, facility profile and policy version in, one recommendation out. Identical inputs always give identical output, which is what makes replay and audit possible.
Pipeline
- Normalize stored snapshots into evidence items: source, value, unit, valid time and snapshot id.
- Run one evaluator per hazard class. Each returns a tier, a time interval, every threshold crossed with the margin, and the distance to the next threshold.
- Rank hazards by restrictiveness and take the worst. Mildest first: normal, delayed arrival, early dismissal, unscheduled leave or telework, closure. This order is a team assumption set in policy.yaml.
- Apply timing to set the posture's parameters.
- Compute the decision deadline, confidence and the flip list.
- Fill the rationale template from those values.
Posture table (worst hazard wins; a numeric trigger means any of T4 to T7 below is crossed)
| Worst hazard | Overlaps | Posture | Parameters |
| Warning, severity Severe or Extreme, certainty Likely or Observed, numeric trigger crossed | Arrival window only | Delayed arrival | delay_until = hazard end + 60 min |
| Same | Departure window only | Early dismissal | dismiss_at = hazard onset - commute buffer |
| Same | Arrival and departure windows | Closure | Closed open to close; next update time |
| Same | Mid-day only, neither window | Normal operations plus safety instruction | Shelter in place until the hazard ends |
| Warning, but severity Moderate or lower, certainty Possible, or no numeric trigger | Any | Unscheduled leave or telework | Until the next update |
| Watch | Any | Normal operations, elevated monitoring | Re-evaluate in 60 min |
| Advisory or no alert | Any | Normal operations | None |
Timing
- The arrival window comes from shift starts, for example 07:00 to 08:30. The departure window runs from 60 minutes before close to 30 minutes after.
- Decision deadline = earliest affected employee's departure time - notification lead time. With a 07:00 shift, a 45 minute commute buffer and a 90 minute lead time, the deadline is 04:45.
- The dashboard counts down to the deadline, and the escalation timers in the notification section run from it.
- A Tornado Warning, or any Warning with onset within 30 minutes, adds a shelter-in-place safety instruction and shortens the approval window to 10 minutes. A pre-approved standing policy may send that one notice without approval. Nothing else is ever automatic.
Stability
- Upgrades apply at once. Downgrades need two consecutive evaluations 15 minutes apart, so a gust value hovering at a cutoff does not flip the recommendation.
- Each evaluation records the one it supersedes. Nothing is overwritten.
Confidence
- High: every required source is fresh, NWS certainty is Likely or Observed, and onset is under 12 hours away.
- Medium: one source is stale, certainty is Possible, or onset is 12 to 36 hours away.
- Low: any required source is missing, certainty is Unlikely or Unknown, or onset is over 36 hours away.
These are starting rules, not tuned numbers. The UI shows the category and the reason, never a percentage.
What would change it
For each numeric input, the engine reruns itself with the value moved just past the next threshold up and down, and reports the resulting posture. It also reports tier changes, such as a Watch upgraded to a Warning. This is deterministic, so the agent only explains it.
Rationale text
The paste-ready paragraph is a template filled from engine values, so it cannot contain a number the engine did not produce.
Thresholds and where they come from
Status says what to do before the pitch. Verified means checked against a live source today. Confirm means read the cited document and copy the exact wording into thresholds.md. Assumption means a team choice, and we say so.
| ID | Hazard | Input | Cutoff | Effect | Anchor | Status |
| T1 | All | NWS alert tier | Warning | Allows delay, dismissal or closure | NWS defines a warning as hazardous weather occurring or imminent | Confirm and cite the NWS page |
| T2 | All | NWS severity field | Severe or Extreme | Allows dismissal and closure | NWS alert severity field | Confirm on first call |
| T3 | All | NWS certainty field | Likely or Observed | Needed for any posture above unscheduled telework | NWS alert certainty field | Confirm on first call |
| T4 | Thunderstorm and wind | Forecast wind gust | 58 mph or more | Numeric trigger | NWS severe thunderstorm wind criterion | Confirm |
| T5 | Thunderstorm and wind | Sustained wind | 40 mph or more for 1 hour | Numeric trigger | Typical NWS High Wind Warning criterion; offices vary | Confirm local office |
| T6 | Winter storm | Ice accumulation | 0.25 in or more | Numeric trigger | Typical NWS Ice Storm Warning criterion | Confirm local office |
| T7 | Flood | Gauge stage | Minor flood stage (32 ft at KCDM7) | Numeric trigger | NWS flood category for the gauge, from NWPS | Verified for KCDM7 |
| T8 | Flood | Gauge stage | Moderate flood stage (35 ft at KCDM7) | Counts as severity Extreme | Same | Verified for KCDM7 |
| T9 | Flood | Gauge stage | Action stage (29 ft at KCDM7) | Raises monitoring only | Same | Verified for KCDM7 |
| T10 | All | Clearing buffer | 60 min after hazard end | Sets delay_until | Team choice | Assumption |
| T11 | All | Commute buffer 45 min, notification lead 90 min | Fixed values | Sets the decision deadline | Team choice in the facility profile | Assumption |
A snowfall cutoff is missing on purpose. Add it from the local forecast office's criteria. A cutoff without an anchor does not ship. thresholds.yaml stores the anchor text and URL beside each value, and the dashboard shows the anchor next to every crossing.
## Recommendation object
The dashboard renders this one object and nothing else, so what the manager sees is exactly what the record stores. The values below are illustrative, not live data.
```json
{
  "evaluation_id": "ev_0007",
  "supersedes": "ev_0006",
  "facility_id": "kc-service-center",
  "evaluated_at": "2027-01-14T09:20:00Z",
  "policy_version": "policy-2026-10-10.1",
  "data_mode": "live",
  "posture": "delayed_arrival",
  "parameters": { "delay_until": "2027-01-14T10:00:00-06:00", "next_update": "2027-01-14T07:30:00-06:00" },
  "safety_instruction": null,
  "decision_deadline": "2027-01-14T04:45:00-06:00",
  "confidence": { "level": "high", "reasons": ["all sources fresh", "certainty Likely", "onset under 12 h away"] },
  "inputs": [
    { "id": "in_1", "role": "drove", "source": "NWS alert", "label": "Ice Storm Warning",
      "value": { "severity": "Severe", "certainty": "Likely", "urgency": "Expected" },
      "onset": "2027-01-14T05:00:00-06:00", "ends": "2027-01-14T09:00:00-06:00",
      "fetched_at": "2027-01-14T09:19:12Z", "snapshot_id": "snap_0412", "stale": false },
    { "id": "in_2", "role": "drove", "source": "NWS forecast grid", "label": "Forecast ice accumulation",
      "value": 0.4, "unit": "in", "fetched_at": "2027-01-14T09:15:03Z", "snapshot_id": "snap_0409", "stale": false },
    { "id": "in_3", "role": "context", "source": "USGS gauge 06893000", "label": "Missouri River stage",
      "value": 11.2, "unit": "ft", "fetched_at": "2027-01-14T09:15:40Z", "snapshot_id": "snap_0410", "stale": false }
  ],
  "thresholds_crossed": [
    { "id": "T1", "input_id": "in_1", "cutoff": "Warning", "actual": "Warning" },
    { "id": "T2", "input_id": "in_1", "cutoff": "Severe or Extreme", "actual": "Severe" },
    { "id": "T3", "input_id": "in_1", "cutoff": "Likely or Observed", "actual": "Likely" },
    { "id": "T6", "input_id": "in_2", "cutoff": 0.25, "actual": 0.4, "unit": "in", "margin": 0.15,
      "anchor": "Typical NWS Ice Storm Warning criterion", "anchor_url": "<from thresholds.yaml>" }
  ],
  "thresholds_not_crossed": [
    { "id": "T9", "input_id": "in_3", "cutoff": 29, "actual": 11.2, "unit": "ft", "distance": 17.8 }
  ],
  "missing_evidence": [],
  "flip_list": [
    { "change": "Forecast ice falls below 0.25 in", "resulting_posture": "unscheduled_leave_or_telework" },
    { "change": "Warning is downgraded to a Watch", "resulting_posture": "normal_operations_elevated_monitoring" },
    { "change": "Hazard runs past 15:00", "resulting_posture": "closure" }
  ],
  "rationale": "Recommend a delayed arrival until 10:00 AM on January 14. An Ice Storm Warning (severity Severe, certainty Likely) covers 5:00 to 9:00 AM, and forecast ice of 0.4 in exceeds the 0.25 in cutoff by 0.15 in during the arrival window. The Missouri River gauge was checked at 11.2 ft, 17.8 ft below action stage, and is not a factor. Confidence is high. A decision is needed by 4:45 AM."
}
```
Rules for the object
- All times are ISO 8601 with an offset. They are stored in UTC and shown in the facility's local time.
- Every input carries a snapshot_id, so any number traces back to the stored raw payload.
- role is drove or context. A context item proves a signal was checked and ruled out, which is how the supplementary gauge shows up even when the hazard is not a flood.
- Every crossed threshold shows actual, cutoff and margin in the same unit, plus its anchor.
- The rationale is generated from these fields. The agent may reword it, but its numbers are checked against this object.
## Strands agent
The agent explains and explores; it never decides. It reads evaluations through a small set of tools and can rerun the engine on hypothetical inputs, but it has no tool that approves, sends or edits anything.
Setup
- Create it with from strands import Agent. The default model provider is Amazon Bedrock. To use another provider, pass a model object, such as AnthropicModel from strands.models.anthropic. The Strands quickstart also shows OpenAI, Gemini and Ollama.
- Decide the provider at kickoff, based on the credits the sponsors hand out.
- Call it as agent(prompt) and read the reply with str(result).
- Tools are plain Python functions with Strands' tool decorator. Confirm the import and the tools= argument on the Strands custom-tools page before writing them.
```python
from strands import Agent

agent = Agent(
    model=model,  # omit to use the default Bedrock model
    tools=[get_evaluation, get_evidence, list_affected_employees, get_thresholds, run_what_if],
    system_prompt=SYSTEM_PROMPT,
)
reply = str(agent(user_message))
```
Tools
| Tool | What it does | Writes |
| get_evaluation(evaluation_id) | Returns the stored recommendation object | Nothing |
| get_evidence(snapshot_id) | Returns the raw snapshot behind an input | Nothing |
| list_affected_employees(evaluation_id, filter) | Returns roster rows with their groups, such as essential or not telework-eligible | Nothing |
| get_thresholds() | Returns the thresholds table with anchors | Nothing |
| run_what_if(evaluation_id, overrides) | Reruns the engine with overridden inputs | One whatif row, marked hypothetical |
What-if scenarios
- overrides maps an input id to a new value, or removes an input. The engine returns a full recommendation with hypothetical set to true, the base evaluation id and the overrides applied.
- The UI shows it under a HYPOTHETICAL banner with a diff against the original. It is stored apart from real evaluations and can never be approved.
- The agent cannot force a posture, because postures are engine outputs. For a question like delayed opening versus early dismissal, it answers from the posture table and the flip list.
| Manager asks | Tool used |
| What if the ice forecast drops to 0.2 in? | run_what_if with the ice input overridden |
| Which employees cannot telework? | list_affected_employees with the not-telework-eligible filter |
| What evidence is missing? | get_evaluation, reading missing_evidence |
Guardrails
- No write tools. Approval, notification and record writes are API endpoints that the agent code never imports.
- Number check. After each reply, a validator pulls out every number and time and checks that it appears in that turn's tool results. A failed check retries once, then shows the engine's own rationale with a note that the figure could not be verified.
- System prompt rules. Answer only from tool results, label hypotheticals, say the engine recommends, and never authorize or advise overriding.
- Alert text is data. NWS text is passed inside delimiters, and the prompt says never to follow instructions found in it.
- Everything is recorded. Each question, tool call and answer is appended to the decision record under the evaluation id.
- Fails soft. If the model API is down, the chat panel says the agent is offline. The engine, rationale and approval flow do not depend on it.
Where it lives
/ai/agent.py exposes chat(evaluation_id, message, history), which returns the reply, the tool calls made and any whatif id. The API route POST /api/chat calls it. The UI shows the tool calls as small chips under each answer, so judges can see Strands doing the work.
## Approval workflow
A recommendation is advice. Nothing reaches employees until a person approves it, with one exception (standing policy, below). The workflow is small on purpose: three decisions, one protection against acting on old information, and a record of every choice.
[embed]
A recommendation ends in one of four ways. Approve and override lead to notification; reject and supersede send the loop back to the next evaluation.
### Rules
- Approve. Sends the package as built. The call is idempotent per evaluation id: a second click returns the existing approval (already_decided) and sends nothing twice.
- Reject. A reason is required. No notification is built. The evaluation stays in the record, marked rejected with the reason, and the engine keeps polling, so a later evaluation can ask again.
- Override. The Approver picks one of the five postures and gives a reason. The engine's original recommendation stays visible next to the override, both in the record. The package is rebuilt for the chosen posture before it is sent, and the Approver sees that preview first.
- Stale approval protection. If a newer evaluation appears while the Approver is looking at an older one, approve, reject and override all return 409 stale_evaluation. The screen shows what changed (posture, confidence, deadline) and asks for a fresh decision. The check runs on the server at the moment of the click, not when the page loaded.
- Upgrade while waiting. A pending recommendation that is upgraded to a more serious posture is marked as needing attention at the top of the Watchlist. A downgrade waits for the hysteresis rule (two evaluations, 15 minutes apart) before it replaces it.
- Waiting too long. The decision deadline is shown as a countdown. If the manager has not responded, the backup manager is notified after a window of (deadline minus now) divided by 4, held between 5 and 30 minutes. If a Tornado Warning is active or the deadline is under 30 minutes away, primary and backup are notified at the same time. If the backup is silent too, the evaluation is marked UNRESOLVED (see Escalation). For the demo these notices are simulated and labelled.
- Identity. No login for the hackathon. The Approver types a name once; it is sent as actor and recorded. Say plainly in the pitch that real sign-in would replace this.
### Standing policy: the one automatic send
Shelter-in-place is the only notice that can go out without waiting for a person, because delay itself is the danger. It is allowed only under a pre-approved standing policy, and only for a Tornado Warning or any Warning with onset within 30 minutes (the rule in the Policy engine section). It uses a fixed short message to everyone on site. The record shows it with approval_id = null and standing_policy = "shelter_in_place", and the Approver is told straight away so they can follow up. Every other posture waits for approval.
## Notification package, delivery and escalation
After approval, the system builds one package per decision: a reason for every person included or excluded, one drafted message per group, and a channel plan for each recipient. Exclusions, not quiet hours, keep people from being woken for nothing.
Who is told what
The cell text is a summary. The actual wording comes from human-written templates in policy.yaml, so leave and telework instructions follow policy and are never invented by the AI.
| Group | Delayed arrival | Early dismissal | Unscheduled leave or telework | Closure |
| Essential | Reporting unchanged; safe-travel note | Same | Same | Same |
| Onsite, telework-eligible | Arrive by the new time, or telework | Leave at the stated time | Telework, or leave per policy text | Do not report; telework or leave per policy text |
| Onsite, not telework-eligible | Arrive by the new time | Leave at the stated time | Report unless the supervisor says otherwise, per policy text | Do not report; leave per policy text |
| Already teleworking | Excluded: no change | Excluded: no change | Excluded: no change | Informational closure notice only |
| Detail elsewhere, on leave, off today | Excluded, with the reason shown | Same | Same | Same |
| Detail in from another office | Treated as assigned | Same | Same | Same |
| Contractor | Told the site status; work status goes through the contract lead | Same | Same | Same |
Message template fields
Every message states what is happening, whether it applies to this person, what to do, the effective period, when the next update comes, and how to acknowledge. It also states the default if no update arrives, because silence is not an all-clear. A comm_needs flag selects the alternate-format or language variant. If a variant template is missing, the package shows a needs-translation warning instead of silently sending English.
```json
{
  "package_id": "pk_0003", "evaluation_id": "ev_0007", "decision_id": "dc_0003",
  "ack_deadline": "2027-01-14T05:05:00-06:00", "next_update": "2027-01-14T07:30:00-06:00",
  "recipients": [
    { "employee_id": "e_014", "included": true, "group": "onsite_telework_eligible",
      "reason": "Assigned onsite today; posture is delayed arrival",
      "message_id": "m_1", "channel_plan": ["email", "sms"] },
    { "employee_id": "e_022", "included": false, "group": "already_teleworking",
      "reason": "Already teleworking; no change to work arrangement" }
  ],
  "messages": [ { "id": "m_1", "group": "onsite_telework_eligible", "text": "..." } ]
}
```
Delivery simulator
- Each notification moves through queued, sent, delivered or failed, then acknowledged. The simulator advances the states on the clock, with a delivery delay and a failure rate per channel.
- A storm mode raises failure rates. A failed message moves to the next channel in the person's list, because unacknowledged is not the same as unreachable.
- Only email can really send. The UI labels every notification real or simulated.
- An employee phone panel lets the presenter acknowledge people one at a time, or click Simulate responses to acknowledge most of them. Acknowledgment means received. The UI never says understood.
- Approval is idempotent, keyed on the evaluation id, and notification rows are unique per evaluation, employee and attempt. A double click cannot send twice.
Escalation
Two chains run from timers stored in the database. All windows live in policy.yaml, and the numbers below are starting values.
| Trigger | Window | Action |
| Employees have not acknowledged | min(20 min after send, departure time - 10 min) | Manager and the employees' supervisors get a list with each person's contact status and options to resend by another channel or call |
| Manager has not responded to a recommendation | W = (deadline - now) / 4, held between 5 and 30 min | Notify the backup manager or duty officer |
| Urgent event, such as shelter in place, or under 30 min to the deadline | None | Notify primary and backup at the same time |
| Backup silent and the deadline is near | One more window W | Mark the evaluation UNRESOLVED and notify the next authority |
A default operational action runs only under an explicit, pre-approved standing policy. In the MVP that is the shelter-in-place notice alone. The agent can never create a fallback decision.
Simulated clock
- A Clock interface has a system implementation and a simulated one that supports fast-forward. Every timer is a database row with a due time, polled by one worker each second, so a fast-forward fires the right timers in order.
- The presenter can jump ahead 30 minutes to show missed acknowledgments and manager escalation inside the 3-minute pitch.
- Evidence freshness always uses the real clock. Only notification and escalation timers use the simulated one, so a fast-forward never makes live data look stale.
- Every record event stores both the wall time and the simulated time.
## Decision record
The record is the answer to "why did the system say that, and what did it know at the time?" Every row is written once and never updated or deleted. A change of mind is a new row that points at the old one.
### Tables
| Table | One row per | Key columns |
| evidence_snapshots | Fetch of one source for one facility (NWS alerts, NWS hourly forecast, NWS grid data, USGS gauge, NWPS categories) | id (ev_0007), facility_id, source, url, fetched_at_wall, fetched_at_sim, http_status, raw_payload (JSON text, untouched), source_updated_at, ok |
| evaluations | Run of the policy engine | id (eval_0042), facility_id, evaluated_at_wall, evaluated_at_sim, data_mode, evidence_ids (JSON list), engine_version, policy_version (for example policy-2026-10-10.1), result (full recommendation JSON), posture, confidence, supersedes (previous evaluation id or null) |
| approvals | Human action on an evaluation | id, evaluation_id, action (approve, reject, override), final_posture, actor, reason (required for reject and override), acted_at_wall, acted_at_sim |
| notifications | Notification package built from an approval (or from standing policy) | id, evaluation_id, approval_id, package (JSON), created_at_* |
| deliveries | One message to one recipient on one channel | id, notification_id, recipient_id, channel, status (queued, sent, simulated, failed, acknowledged), status_at_*, provider_ref |
| timers | Escalation or re-evaluation that should fire later | id, kind, due_at_sim, payload, fired_at, cancelled_at |
| audit_log | Anything else worth knowing (mode switches, clock jumps, what-if runs, validator rejections) | id, at_wall, at_sim, kind, detail |
Two rules keep this honest. First, the application never issues UPDATE or DELETE on these tables (enforce with a thin append() helper in api/store.py; there is no other write path). Second, timers is the one exception: fired_at and cancelled_at are set once, and each change also writes an audit_log row.
### What gets stored when the data is bad
- Failed or empty fetch. Still write an evidence_snapshots row with ok = false, the HTTP status or exception text, and an empty payload. The engine reads this as "missing" and drops confidence; the record shows the gap instead of hiding it.
- Poll with nothing new. Write the snapshot anyway (ok = true, alert list empty). "No active alerts at 03:10" is evidence, and a judge may ask what the system saw before the storm.
- No change in result. Still write an evaluation, with supersedes pointing at the previous one. The chain eval_0040 → 0041 → 0042 shows the system kept watching.
- Hysteresis hold. A downgrade that is held back records the engine's raw posture next to the held posture (result.raw_posture, result.held_by_hysteresis = true), so the record explains why the posture did not move.
### Two clocks on every row
Every row carries *_wall (real time, ISO 8601 with offset) and *_sim (the simulated clock). In normal operation they are equal. When the demo clock is accelerated, wall time shows when it really happened and sim time shows when the scenario says it happened. Evidence freshness is judged on wall time only; escalation and deadlines run on sim time (see Notification package, delivery and escalation).
### Replay
Replay is the proof that the recommendation is a function of its inputs.
- The UI shows a Replay button on any evaluation.
- POST /api/evaluations/{id}/replay loads the evaluation's evidence_ids, parses each stored raw_payload with the same normalizers used live, and calls engine.evaluate() with the stored roster, policy version and now = evaluated_at_wall.
- The API compares the new result with the stored result field by field and returns { "identical": true, "diff": [] } or the differing paths.
- A replay never writes an evaluation. It writes one audit_log row (kind = replay).
The replay can only be identical if the engine is deterministic: no datetime.now(), no randomness, and no network calls inside engine/. The clock and the evidence come in as arguments. A unit test that replays every seeded scenario and asserts identical is worth writing early; it catches accidental impurity at once.
### Replay data mode
DATA_MODE=replay serves recorded NWS and USGS payloads from mocks/ instead of calling the network. The same code path writes the same rows, with data_mode = replay on each evaluation, and the UI shows a REPLAY badge on every screen. Recorded payloads are real captures taken during the event (save them with a small script on Saturday while a real alert is active), not hand-written JSON. Never show replay data unlabelled.
### Export
GET /api/evaluations/{id}/record returns one JSON document: the evaluation, its evidence snapshots (with raw payloads), the approval, the notification package and every delivery with status history. The Decision record screen renders it, and a Download JSON button saves it. This is the artifact a judge can keep.
### Retention
Nothing is purged during the event. The SQLite file lives at data/closureiq.db, git-ignored. Back it up before the final demo (cp data/closureiq.db data/backup-$(date +%H%M).db) so a bad migration at 7:30 AM cannot cost the history.
## API contract
This section is the first draft of docs/contract.md. Suraj owns it. Lanes C (frontend) and D (agent) code against it from hour 1 using fixtures in mocks/; lanes A and B must match it exactly. Any change is a one-line message in the team chat and an edit to the file before the code changes.
Conventions: JSON everywhere, snake_case keys, ISO 8601 timestamps with offset, ids as strings (eval_0042, ev_0007, ntf_0003, dlv_0019). Base path /api. No authentication for the hackathon; the Approver identity is a name chosen in the UI and sent as actor.
### Endpoints
| Method and path | Purpose | Lane |
| GET /api/health | { ok, data_mode, clock: { mode, now_sim, now_wall }, last_poll_at } | A |
| GET /api/facilities | The three facility locations with current posture and highest alert tier (drives the picker) | A |
| GET /api/facilities/{id} | Facility profile: name, lat/lon, shift pattern, earliest departure, notification lead time, assembly point | A |
| GET /api/facilities/{id}/roster | Employees with group, commute mode, county, contact channels | A |
| GET /api/facilities/{id}/status | Latest evaluation plus freshness of each evidence source | A |
| POST /api/facilities/{id}/evaluate | Poll sources and run the engine now. Returns the new evaluation | A |
| GET /api/evaluations?facility_id=&limit= | History, newest first | A |
| GET /api/evaluations/{id} | One recommendation object (see Recommendation object) | A |
| GET /api/evaluations/{id}/record | Full decision record (see Decision record) | B |
| POST /api/evaluations/{id}/replay | Re-run stored evidence; returns { identical, diff } | B |
| POST /api/evaluations/{id}/what-if | Body { overrides }; returns a HYPOTHETICAL recommendation; writes only an audit_log row | A |
| POST /api/evaluations/{id}/approve | Body { actor }. Builds and queues the notification package | B |
| POST /api/evaluations/{id}/reject | Body { actor, reason } | B |
| POST /api/evaluations/{id}/override | Body { actor, posture, reason } | B |
| GET /api/notifications/{id} | Package and deliveries with status | B |
| POST /api/deliveries/{id}/ack | Simulates a recipient acknowledging; body {} | B |
| GET /api/thresholds | Current thresholds T1 to T11 with status (verified, confirm, assumption) and source | A |
| GET /api/clock and POST /api/clock | Read the clock, or change it. Body for POST: mode (system or simulated), speed, set_to | B |
| POST /api/mode | Switch data mode. Body: { data_mode } with live or replay; writes an audit_log row | A |
| POST /api/agent/chat | Body { facility_id, evaluation_id, message }; streams the answer as SSE | D |
| GET /api/events | Server-sent events for the whole UI (below) | A |
### Server-sent events
One stream, GET /api/events, with event: names and JSON data:. The frontend opens it once and routes by event name; on any reconnect it refetches GET /api/facilities so nothing is missed.
| Event | Data | When |
| evaluation.created | { facility_id, evaluation_id, posture, confidence, changed } | After every evaluation |
| approval.recorded | { evaluation_id, action, final_posture } | After approve, reject or override |
| delivery.updated | { delivery_id, notification_id, status } | Each delivery status change |
| escalation.fired | { notification_id, step, next_due_sim } | When a timer fires |
| clock.changed | { mode, now_sim, speed } | Clock changes |
| mode.changed | { data_mode } | Data mode switch |
| source.degraded | { facility_id, source, reason } | A source fails or goes stale |
### Key request and response shapes
Approve (also the shape of reject and override responses):
```json
// POST /api/evaluations/eval_0042/approve   { "actor": "Dana (Safety Officer)" }
{
  "approval": { "id": "apr_0006", "evaluation_id": "eval_0042", "action": "approve",
                "final_posture": "delayed_arrival", "actor": "Dana (Safety Officer)",
                "acted_at_wall": "2026-10-11T03:12:44-05:00" },
  "notification_id": "ntf_0003"
}
```
What-if:
```json
// POST /api/evaluations/eval_0042/what-if
{ "overrides": { "alert_severity": "Severe", "hours_to_onset": 2 } }
// -> 200
{ "hypothetical": true, "based_on": "eval_0042", "result": { /* recommendation object */ },
  "changed_fields": ["posture", "confidence", "decision_deadline"] }
```
Agent chat (SSE):
```
event: token
data: {"text": "The posture is delayed arrival because..."}

event: done
data: {"evaluation_id": "eval_0042", "validated": true}
```
If the number-check validator rejects the answer, the stream sends event: replaced with the safe template text instead, and done carries validated: false.
### Errors
Every error is { "error": { "code": "...", "message": "...", "detail": {} } } with a matching status.
| Status | Code | Meaning |
| 400 | bad_request | Missing field, or reason missing on reject or override |
| 404 | not_found | Unknown facility, evaluation or delivery |
| 409 | stale_evaluation | The evaluation has been superseded by a newer one; detail.latest_id says which. The UI refreshes and asks the Approver to look again |
| 409 | already_decided | An approval exists for this evaluation; the response body is the existing approval, so a double click is harmless (idempotent) |
| 422 | invalid_posture | Override posture not one of the five postures |
| 503 | source_unavailable | evaluate could not reach any source; an evaluation with Low confidence is still written and returned in detail.evaluation_id |
### Fixtures
Lane A commits one recommendation JSON per scenario to mocks/ in the first two hours: normal.json, delayed_arrival.json, early_dismissal.json, unscheduled_leave.json, closure.json, degraded_low_confidence.json. Lane C builds every screen from these before the real API exists, and the same files drive the REPLAY mode.
## Frontend screens and the 3-minute demo
The pitch is live app only. No slides, no extra material. So the app itself has to tell the story, in order, without anyone explaining a menu. Lane C builds five screens plus a small demo control strip.
### Screens
| # | Screen | What is on it | Data it needs |
| 1 | Watchlist (home) | The three facility cards sorted by alert tier. Each shows current posture chip, confidence, next decision deadline, and a source-health dot. Top bar: DATA mode badge (LIVE or REPLAY), clock (with SIMULATED tag when accelerated) | GET /api/facilities, SSE |
| 2 | Facility decision | Posture banner with one-line reason. Left: the evidence list (source, timestamp, age, value) and the threshold crossed with the margin. Right: confidence with its reasons, "what would change this" flip list, and the rationale paragraph. Below: affected employees by group | GET /api/facilities/{id}/status, GET /api/evaluations/{id}, roster |
| 3 | Approval panel (drawer on screen 2) | Approve, Reject, Override buttons. Reject and Override require a reason. Shows the notification package preview (recipients by group, message text, channel routing) before the Approver commits | approve, reject, override, package preview from the recommendation |
| 4 | Delivery tracker | One row per recipient and channel with status chips that change live. Escalation steps as a timeline with the next due time. A Simulate acknowledge button on each row | GET /api/notifications/{id}, SSE delivery.updated, escalation.fired |
| 5 | Decision record | Evaluation chain, evidence snapshots with raw payload viewer, approval, package, deliveries. Replay button showing "identical" result. Download JSON | /record, /replay |
Two supporting pieces sit on screen 2 rather than getting their own pages: an Ask panel (agent chat with what-if prompts such as "what if the warning is upgraded to Severe?", answers marked HYPOTHETICAL) and a Demo controls strip (data mode toggle, clock speed 1x/60x/600x, jump-to-scenario). Hide Demo controls behind a ?demo=1 query parameter so the product looks clean by default and the presenter has them when needed.
### Design rules that matter under time pressure
- Posture is always shown as a coloured chip plus text, never colour alone. Five postures, five fixed colours defined once in frontend/src/theme.ts.
- Every number in the UI that came from evidence shows its source and age on hover or inline. This is the "inputs with source and timestamp" deliverable made visible.
- Degraded state is loud: a banner with the source name and age, and the confidence chip turns to Low. The UI never shows a calm green posture next to a failed source.
- No loading spinners longer than 2 seconds on the demo path. The server returns the last stored evaluation immediately and the SSE stream pushes the fresh one.
- Build with Tailwind utility classes and one component library (shadcn/ui or similar). Do not hand-design.
### The 3-minute demo path
Rehearse this at least three times, with a stopwatch, on the real machine and projector resolution. Every step uses a feature that already exists in the screens above.
| Time | Do | Say (the point being made) |
| 0:00 to 0:20 | Open Watchlist. Point at the three facilities, sorted with the live alert on top | "Facility managers get a weather alert and still have to decide: delay, release early, telework or close. This ranks the places that need a decision now." |
| 0:20 to 1:00 | Click the top facility. Walk the banner, then the evidence list and the threshold line | "Recommendation is delayed arrival. Here is the live NWS alert, its timestamp, the threshold it crossed and by how much. The posture comes from a rule table, not a language model." |
| 1:00 to 1:25 | Show confidence reasons and the flip list. Ask the agent the what-if question | "Medium confidence because the forecast and the gauge disagree. These are the three things that would change the call. The assistant explains; it cannot change the decision." |
| 1:25 to 2:00 | Open Approval. Show the package preview. Approve | "The Approver stays in control. On approval the system builds the notification package: who, what to say, which channel." |
| 2:00 to 2:30 | Delivery tracker. Switch clock to 600x. Let an escalation fire; acknowledge a few rows | "Anyone who has not acknowledged goes on a list for the manager and supervisors, who can resend by another channel; a silent manager triggers the backup. The clock is accelerated for the demo; the timers are real." |
| 2:30 to 2:50 | Decision record. Press Replay. Show "identical" | "Every input is stored raw. Replaying the evidence gives the same answer. That is the audit trail." |
| 2:50 to 3:00 | Back to Watchlist | "Narrow and deep: one facility profile, three hazards, live NWS data. Thank you." |
Two spare beats if time runs short: skip the what-if (1:00 to 1:25) and the replay (2:30 to 2:50). Both are optional; the approve-to-escalation story is the core.
### Failure plans for the demo
- No live alert in the region at 9:00 AM. Watchlist already has three locations chosen so at least one usually has an active alert. If none do, flip to REPLAY (badge visible, say so), using the real capture saved on Saturday.
- NWS slow or down. The source-health dot goes amber, confidence drops to Low, and the app still works from the last stored evidence. Say "this is the degraded path" and continue; do not hide it.
- Email not arriving. Email is the only real channel, so send one to a team inbox earlier in the demo path and show it landing, but keep the delivery tracker the main visual. Do not depend on the inbox refreshing in front of judges.
- Projector resolution. Test at 1280x720 and zoom the browser to 125%. Keep the demo on one browser window with ?demo=1.
### Before walking up
- Back up data/closureiq.db and run a clean seed.
- Reset clock to system time, data mode to LIVE.
- Run one full evaluate and approve cycle to warm caches and confirm email works, then reset the facility so the demo starts fresh.
- Close every other tab and notification source on the demo laptop.
- Have the second teammate's laptop on the same build as a fallback.
## Build plan to 8:00 AM Sunday
Fixed points: 7:00 PM Saturday project checkpoint (content not yet known; ask a volunteer what to bring), Sunday 8:00 AM hard deadline for commits, 9:00 AM demos. The times below assume the team is building from about noon Saturday. Owners: Badri on data, store and API; Kavya on frontend and wiring; Samanth on the policy engine, then the Strands agent; Suraj on contract, Akamai Cloud, thresholds and seed data, then notification and delivery. Phase 1 ends at the 7 PM checkpoint, Phase 2 at the 8 AM deadline. The table's lane columns are the folders; the Linear issues are the per-person task list.
### Timeline
| When | Goal | Lane A: data and engine | Lane B: notify and record | Lane C: frontend | Lane D: agent and integration |
| Sat noon to 1:30 PM | Skeleton. Everyone runs the empty app | Repo layout, FastAPI hello, SQLite append() helper, confirm the three NWS calls with curl and paste real samples into mocks/ | Table creation, clock module (system and simulated) | Vite app, routing, theme, SSE hook, Watchlist built from a fixture | Commit docs/contract.md and the six scenario fixtures; update AGENTS.md ownership; .env.example |
| 1:30 to 4:00 PM | Engine runs on stored data | Normalizers for alerts, hourly forecast, gauge; thresholds table; posture rules; confidence; flip list | Notification package builder from a recommendation | Facility decision screen from fixtures | Agent skeleton with get_evaluation and get_evidence; first end-to-end call |
| 4:00 to 7:00 PM | Checkpoint demo: live evaluation to screen | Live polling for 3 locations, evaluation written and pushed over SSE | Approve, reject, override endpoints with the 409 rules | Approval drawer and package preview wired to real endpoints | Wire SSE, fix contract mismatches, record the first demo capture |
| 7:00 to 10:00 PM | Notification and escalation | Hysteresis and failure ladder; unit tests for each of the five postures | Delivery simulator, email send, timers and escalation, delivery tracker API | Delivery tracker screen, Demo controls strip | Agent what-if tool, number-check validator, Ask panel |
| 10:00 PM to 1:00 AM | Decision record and replay | Determinism test: replay all fixtures, assert identical | Record export, replay endpoint, audit_log entries | Decision record screen, Replay button, REPLAY and degraded banners | Full-flow rehearsal #1 against live data; log every bug in Linear |
| 1:00 to 3:00 AM | Feature freeze at 3:00 AM. Finish, then stop adding | Threshold review: mark each T1 to T11 as verified, confirm or assumption in the UI | Failure paths: bounced email, failed delivery, no-ack escalation | Polish, empty states, projector test | Save real replay captures if a live alert is active; rehearsal #2 |
| 3:00 to 6:00 AM | Harden, then rest in shifts | Bug fixes only | Bug fixes only | Bug fixes only | Two people sleep 3:00 to 5:00 AM while two work; swap at 5:00 |
| 6:00 to 7:30 AM | Rehearse and lock | One full demo run with the stopwatch (twice) | Reset DB, seed, back up | Test at 1280x720 | Final README: how to run, which challenge boxes are ticked, tools used |
| 7:30 to 8:00 AM | Final push | Only commit what has been tested on the demo laptop. Last commit by 7:50. Nothing after 8:00 |  |  |  |
### Rules for the team
- Contract first. The skeleton hour ends only when every lane can fetch a fixture through its own code path.
- Commit small and often, on main or short-lived branches; merge to main only code that runs. A broken main after midnight is the biggest risk on this list.
- Integration slot every 3 hours (4 PM, 7 PM, 10 PM, 1 AM): ten minutes, everyone pulls main and runs the whole flow. Suraj calls it.
- After 8:00 AM, no commits at all. That includes README fixes. Check git log at 7:55.
- Stay in your folder. If lane C needs an API change, ask the contract owner; do not edit api/ from the frontend lane, even through an AI tool.
- Dependencies: any new package gets named in the team chat or PR description.
### Cut list (drop from the bottom first)
If time slips, remove things in this order. Each cut leaves a working story.
- Third location (keep two).
- Flood hazard and the USGS gauge (keep thunderstorm/wind and winter storm). The gauge was the supplementary-signal demo, so if cut, use the NWS hourly forecast as the secondary signal and say so.
- Override action (keep approve and reject).
- What-if tool and the Ask panel (the agent still writes the explanation).
- Agent chat entirely (keep the template rationale; the AWS Strands challenge box then has to be unticked).
- Email (keep the simulator; label everything SIMULATED).
- Escalation timers (keep the first send and the delivery tracker).
Do not cut: live NWS evidence with timestamps, the threshold and margin, confidence with flip list, approval, the notification package, the decision record. Those are the USDA deliverables.
### Fallbacks
| Risk | Fallback |
| NWS field names differ from the guess | The three curl calls in the first 90 minutes; fix the normalizer once, everything else follows |
| Bedrock access or credentials not ready | Switch the Strands model provider via strands.models.* (OpenAI, Anthropic, Ollama); the agent code does not change |
| Email provider blocks sending | Use a mail relay that works with one API key (Resend, SMTP via a throwaway Gmail app password); if neither works by 10 PM, label email as simulated |
| SQLite locked under polling plus UI | One writer thread; WAL mode (PRAGMA journal_mode=WAL) |
| Clock simulation bugs | Keep evidence freshness on the real clock and only escalation on the simulated one; if the simulation will not behave, drop to 1x and use "Fire next escalation now" button |
| Team member cannot finish a lane | Cut list above; Sam reassigns at the next integration slot |
### Done means
A teammate who has never seen the app can open it on a clean laptop, follow the README to run it, and complete the 3-minute demo path without anything being explained to them.
## Sources and what is still unverified
Pages opened while writing this document:
- Hack Midwest: schedule, rules, judging, sponsor challenges.
- NWS API documentation: no key, User-Agent header required, /points/{lat},{lon} returns the forecast URLs.
- USGS instantaneous values service and a live call to https://waterservices.usgs.gov/nwis/iv/?format=json&sites=06893000&parameterCd=00065,00060: works without a key.
- NWPS gauge API: returned flood categories (action 29, minor 32, moderate 35, major 49 ft) without a key.
- Strands Agents SDK quickstart and model providers.
- The USDA AI Challenge text ("Closure Call") as pasted by the team.
Not verified, and the first thing to confirm on Saturday (see "First 15 minutes: confirm the NWS details" in the Data layer section): the exact NWS alert property names, the point filter on the alerts endpoint, the gridpoint field names, and how the Strands tool decorator is used. The thresholds marked Confirm or Assumption in the Policy engine section stay unverified until someone reads the cited source and copies the wording into thresholds.md. Escalation windows and confidence rules are starting values, not tuned numbers.