# ClosureIQ API contract

Status: draft v1 (Saturday 1:40 PM). Owner: Suraj. Source: the architecture doc (API contract, Recommendation object, Decision record, Notification package).

Frontend (Kavya) and agent (Samanth) code against this file and the fixtures in `mocks/` from the start. Backend (Badri) and engine (Samanth) must match it exactly.

**Changing the contract:** post one line in #all-hackmidwest, edit this file, then change the code. Never the other way round.

## Conventions

- JSON everywhere, `snake_case` keys, base path `/api`.
- Times are ISO 8601 with an offset (for example `2026-10-16T04:45:00-05:00`). Parse them, never compare them as strings. Show them in the facility's local time.
- Ids are strings with a prefix: `eval_0042` (evaluation), `snap_0412` (evidence snapshot), `apr_0006` (approval), `ntf_0003` (notification package), `dlv_0019` (delivery), `wif_0001` (what-if), `e_014` (employee).
- No authentication. The approver types a name once and the UI sends it as `actor`.
- Postures (the only five values): `normal_operations`, `delayed_arrival`, `early_dismissal`, `unscheduled_leave_or_telework`, `closure`.
- Confidence levels: `high`, `medium`, `low`. Alert tiers: `none`, `advisory`, `watch`, `warning`.
- A field that may be empty is `null`, never missing.

## Endpoints

Lane: **A** = Badri (ingest, app) with Samanth (engine), **B** = Badri (store, approvals), Suraj (notify, clock), **D** = Samanth (agent).

| Method and path | Purpose | Lane |
|---|---|---|
| GET `/api/health` | `{ ok, data_mode, clock: { mode, now_sim, now_wall }, last_poll_at }` | A |
| GET `/api/facilities` | The three facilities with their current posture. Sorted by highest alert tier, then posture severity. See `mocks/facilities.json` | A |
| GET `/api/facilities/{id}` | Facility profile (below) | A |
| GET `/api/facilities/{id}/roster` | Employees with group and contact channels (below) | A |
| GET `/api/facilities/{id}/status` | Latest evaluation plus freshness of each source (below) | A |
| POST `/api/facilities/{id}/evaluate` | Poll sources and run the engine now. Returns the new recommendation. `503 source_unavailable` if no source answers | A |
| GET `/api/evaluations?facility_id=&limit=` | History, newest first. Each item is a full recommendation | A |
| GET `/api/evaluations/{id}` | One recommendation object | A |
| GET `/api/evaluations/{id}/record` | Full decision record (below) | B |
| POST `/api/evaluations/{id}/replay` | Re-runs stored evidence. Returns `{ identical, diff }` | B |
| POST `/api/evaluations/{id}/what-if` | Body `{ overrides }`. Returns a HYPOTHETICAL recommendation. Writes only an audit row | A |
| GET `/api/evaluations/{id}/package-preview?posture=` | Notification package preview before approval. `posture` is optional and lets the approver preview an override. **Added to the contract** | B |
| POST `/api/evaluations/{id}/approve` | Body `{ actor }` | B |
| POST `/api/evaluations/{id}/reject` | Body `{ actor, reason }` | B |
| POST `/api/evaluations/{id}/override` | Body `{ actor, posture, reason }` | B |
| GET `/api/notifications/{id}` | Package, deliveries and escalation (below) | B |
| POST `/api/deliveries/{id}/ack` | Simulates a recipient acknowledging. Body `{}`. Returns the delivery | B |
| GET `/api/thresholds` | Thresholds T1 to T11 (below) | A |
| GET `/api/clock` | `{ mode, now_sim, now_wall, speed }` | B |
| POST `/api/clock` | Body `{ mode, speed, set_to }`. `mode` is `system` or `simulated`. Returns the clock | B |
| POST `/api/mode` | Body `{ data_mode }`, `live` or `replay`. Returns `{ data_mode }`. Writes an audit row | A |
| POST `/api/agent/chat` | Body `{ facility_id, evaluation_id, message }`. Streams the answer as SSE (below) | D |
| GET `/api/events` | Server-sent events for the whole UI (below) | A |

## The recommendation object

The dashboard renders this object and nothing else. Fixtures in `mocks/` are the reference: `normal.json`, `delayed_arrival.json`, `early_dismissal.json`, `unscheduled_leave.json`, `closure.json`, `degraded_low_confidence.json`.

| Field | Type | Notes |
|---|---|---|
| `hypothetical` | bool | `false` on real evaluations. `true` only inside a what-if result |
| `evaluation_id` | string | `eval_NNNN` |
| `supersedes` | string or null | Previous evaluation for this facility |
| `facility_id` | string | |
| `evaluated_at` | time | |
| `policy_version` | string | For example `policy-2026-10-10.1` |
| `data_mode` | `live` or `replay` | Show a REPLAY badge when `replay` |
| `posture` | posture | The posture after hysteresis |
| `raw_posture` | posture | What the engine computed before hysteresis |
| `held_by_hysteresis` | bool | `true` when a downgrade is held back (needs two evaluations 15 minutes apart) |
| `parameters` | object | Depends on posture, see below |
| `safety_instruction` | string or null | For example shelter in place |
| `decision_deadline` | time or null | `null` when no decision is needed |
| `confidence` | `{ level, reasons[] }` | Show the level and every reason. Never a percentage |
| `inputs[]` | array | Every input used, see below |
| `thresholds_crossed[]` | array | Each has `id`, `input_id`, `cutoff`, `actual`. Numeric ones also have `unit`, `margin`, `anchor`, `anchor_url` |
| `thresholds_not_crossed[]` | array | Numeric ones have `distance` to the cutoff |
| `missing_evidence[]` | array | Objects `{ source, reason, last_good_snapshot_id, last_good_age_minutes, max_age_minutes }`. Empty when nothing is missing |
| `flip_list[]` | array | `{ change, resulting_posture, note? }`. What would change the call |
| `rationale` | string | Paste-ready paragraph, generated from the fields above |

**`parameters` by posture**

| Posture | Keys |
|---|---|
| `normal_operations` | `monitoring` (`normal` or `elevated`), `next_update` |
| `delayed_arrival` | `delay_until`, `next_update` |
| `early_dismissal` | `dismiss_at`, `next_update` |
| `unscheduled_leave_or_telework` | `next_update` |
| `closure` | `closed_from`, `closed_until`, `next_update` |

**`inputs[]` item:** `id` (`in_1`), `role` (`drove` or `context`), `source`, `label`, `value` (number or object), `unit` (when numeric), `onset` and `ends` (alerts only), `fetched_at`, `snapshot_id`, `stale` (bool). Every number on screen shows its source and `fetched_at`. A `context` input proves a signal was checked and ruled out.

**Rules the UI must follow**

- Posture is a coloured chip plus text, never colour alone.
- If `confidence.level` is `low` or `missing_evidence` is not empty, show a loud banner naming the source and its age. Never show a calm green posture next to a failed source.
- `decision_deadline` null means no countdown.
- Anchor text and `anchor_url` come from `api/engine/policy.yaml` (HAC-36). `anchor_url` is `null` only for team-choice thresholds (T10, T11). Render the link only when present.

## Other shapes

**Facility profile** (`GET /api/facilities/{id}`)

```json
{
  "facility_id": "kc-service-center",
  "name": "Kansas City Service Center",
  "location": { "lat": 39.0997, "lon": -94.5786, "timezone": "America/Chicago" },
  "hours": { "open": "07:30", "close": "16:00" },
  "arrival_window": { "start": "07:00", "end": "08:30" },
  "departure_window": { "start": "15:00", "end": "16:30" },
  "commute_buffer_min": 45,
  "notification_lead_min": 90,
  "earliest_departure": "06:15",
  "assembly_point": "North parking lot",
  "manager_id": "e_001", "backup_manager_id": "e_002", "on_call_id": "e_003",
  "gauge": { "usgs_site": "06893000", "nwps_id": "KCDM7" },
  "policy_version": "policy-2026-10-10.1"
}
```

`gauge` is `null` for facilities without one.

**Roster** (`GET /api/facilities/{id}/roster`): `{ "employees": [ { employee_id, name, group, assignment_type, shift_start, shift_end, work_status_today, essential, telework_eligible, commute_county, channels[], comm_needs[], supervisor_id } ] }`. Names are synthetic. `group` is one of `essential`, `onsite_telework_eligible`, `onsite_not_telework_eligible`, `already_teleworking`, `detail_elsewhere`, `on_leave_or_off`, `contractor`. `comm_needs` holds flags only, never reasons.

**Status** (`GET /api/facilities/{id}/status`)

```json
{
  "facility_id": "kc-service-center",
  "evaluation": { "...": "recommendation object" },
  "approval": null,
  "notification_id": null,
  "sources": [
    { "source": "NWS alerts", "status": "fresh", "fetched_at": "2026-10-15T20:29:15-05:00", "age_seconds": 45, "max_age_seconds": 600 }
  ]
}
```

`status` is `fresh`, `stale` or `missing`. `approval` is the approval object once someone has decided, otherwise `null`.

**Facility list item** (`GET /api/facilities`): `facility_id`, `name`, `location`, `highest_alert_tier`, `source_health` (`ok`, `degraded` or `missing`), `data_mode`, `current` (`evaluation_id`, `posture`, `confidence`, `evaluated_at`, `decision_deadline`, `headline`, `approval_status`). `approval_status` is `not_required`, `pending`, `approved`, `rejected`, `overridden` or `unresolved`.

**Thresholds** (`GET /api/thresholds`): `{ "policy_version": "...", "thresholds": [ { id, hazard, input, cutoff, unit, effect, anchor, anchor_url, status } ] }` where `status` is `verified`, `confirm` or `assumption`.

**Approve** (reject and override return the same shape):

```json
// POST /api/evaluations/eval_0042/approve   { "actor": "Dana (Safety Officer)" }
{
  "approval": { "id": "apr_0006", "evaluation_id": "eval_0042", "action": "approve",
                "final_posture": "delayed_arrival", "actor": "Dana (Safety Officer)",
                "reason": null, "acted_at_wall": "2026-10-11T03:12:44-05:00" },
  "notification_id": "ntf_0003"
}
```

A second approve returns `409 already_decided` with the existing approval as the body. `reject` needs `reason`. `override` needs `posture` and `reason`.

**Notification package** (`package-preview` returns the same shape with `notification_id`, `approval_id` and `ack_deadline` possibly null, and `"preview": true`; `GET /api/notifications/{id}` returns the real one):

```json
{
  "notification_id": "ntf_0003", "evaluation_id": "eval_0012", "approval_id": "apr_0006",
  "standing_policy": null, "preview": false,
  "ack_deadline": "2027-01-14T05:05:00-06:00", "next_update": "2027-01-14T07:30:00-06:00",
  "package": {
    "recipients": [
      { "employee_id": "e_014", "included": true, "group": "onsite_telework_eligible",
        "reason": "Assigned onsite today; posture is delayed arrival",
        "message_id": "m_1", "channel_plan": ["email", "sms"] },
      { "employee_id": "e_022", "included": false, "group": "already_teleworking",
        "reason": "Already teleworking; no change to work arrangement" }
    ],
    "messages": [ { "id": "m_1", "group": "onsite_telework_eligible", "text": "..." } ]
  },
  "deliveries": [
    { "delivery_id": "dlv_0019", "recipient_id": "e_014", "channel": "email", "real": true,
      "status": "delivered", "status_at_wall": "2027-01-14T03:21:05-06:00" }
  ],
  "escalation": [
    { "step": "unacknowledged_to_supervisors", "label": "Supervisors told who has not acknowledged",
      "due_sim": "2027-01-14T03:41:00-06:00", "fired_at_sim": null }
  ]
}
```

Delivery `status`: `queued`, `sent`, `delivered`, `simulated`, `failed`, `acknowledged`. `real` is `true` only for email. A shelter-in-place standing-policy send has `approval_id: null` and `standing_policy: "shelter_in_place"`.

**What-if**

```json
// POST /api/evaluations/eval_0042/what-if
{ "overrides": { "in_2": 0.2 } }
// 200
{ "hypothetical": true, "whatif_id": "wif_0001", "based_on": "eval_0042",
  "result": { "...": "recommendation object with hypothetical: true" },
  "changed_fields": ["posture", "confidence", "decision_deadline"] }
```

`overrides` maps an input id to a new value, or to `null` to remove that input. A what-if can never be approved.

**Record** (`GET /api/evaluations/{id}/record`): `{ evaluation, chain[] (evaluation ids oldest first), evidence[] ({ snapshot_id, source, url, fetched_at_wall, fetched_at_sim, http_status, ok, raw_payload }), approval, notification, deliveries[] (each with status_history[] of { status, at_wall, at_sim }), timers[], audit_log[] }`.

**Replay:** `{ "identical": true, "diff": [] }` or `{ "identical": false, "diff": [ { "path": "posture", "stored": "...", "replayed": "..." } ] }`. A replay never writes an evaluation.

## Server-sent events

One stream, `GET /api/events`, with `event:` names and JSON `data:`. The frontend opens it once and routes by event name. On every reconnect it refetches `GET /api/facilities`.

| Event | Data | When |
|---|---|---|
| `evaluation.created` | `{ facility_id, evaluation_id, posture, confidence, changed }` | After every evaluation |
| `approval.recorded` | `{ evaluation_id, action, final_posture }` | After approve, reject or override |
| `delivery.updated` | `{ delivery_id, notification_id, status }` | Each delivery status change |
| `escalation.fired` | `{ notification_id, step, next_due_sim }` | When a timer fires |
| `clock.changed` | `{ mode, now_sim, speed }` | Clock changes |
| `mode.changed` | `{ data_mode }` | Data mode switch |
| `source.degraded` | `{ facility_id, source, reason }` | A source fails or goes stale |

## Agent chat stream

`POST /api/agent/chat` answers with SSE:

```
event: tool
data: {"name": "get_evaluation", "args": {"evaluation_id": "eval_0042"}}

event: token
data: {"text": "The posture is delayed arrival because..."}

event: done
data: {"evaluation_id": "eval_0042", "validated": true, "whatif_id": null}
```

`tool` events drive the small tool-call chips under each answer (**added to the contract**). If the number check rejects the answer, the stream sends `event: replaced` with the engine's own rationale and `done` carries `validated: false`. If the model is down the endpoint returns `503 agent_unavailable` and the UI shows "agent offline".

## Errors

Every error is `{ "error": { "code": "...", "message": "...", "detail": {} } }` with a matching status.

| Status | Code | Meaning |
|---|---|---|
| 400 | `bad_request` | Missing field, or reason missing on reject or override |
| 404 | `not_found` | Unknown facility, evaluation, notification or delivery |
| 409 | `stale_evaluation` | A newer evaluation exists. `detail.latest_id` says which. The UI refreshes and asks again |
| 409 | `already_decided` | An approval exists. The body is the existing approval, so a double click is harmless |
| 422 | `invalid_posture` | Override posture is not one of the five |
| 503 | `source_unavailable` | No source answered. A Low-confidence evaluation is still written, in `detail.evaluation_id` |
| 503 | `agent_unavailable` | The model API is down |

## Choices made while writing this file

The architecture doc is inconsistent in a few places. These are the values to use:

- Evaluation ids are `eval_NNNN` and snapshot ids are `snap_NNNN`. (The doc's example also used `ev_` for evaluations.)
- The notification package is identified by `ntf_NNNN`. There is no separate `pk_` or `dc_` id.
- The chat endpoint is `/api/agent/chat`.
- Elevated monitoring after a Watch is `posture: normal_operations` with `parameters.monitoring: "elevated"`. There is no sixth posture.
- Times use the facility's local offset in responses, not `Z`.

## Fixtures

`mocks/` holds one recommendation JSON per scenario plus `facilities.json` for the Watchlist. Each file is an independent, synthetic scenario, so evaluation dates differ between files. They are not recordings of real alerts. Real recorded payloads for `DATA_MODE=replay` are captured later. Still to come: roster (HAC-18), package preview and notification (HAC-40), status.
