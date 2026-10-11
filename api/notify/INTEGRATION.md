# Wiring `api/notify` into the API (for Badri)

Owner of `api/notify` and `api/clock.py`: Suraj. Owner of the code this touches (`api/app`, `api/store`, `api/main.py`): Badri.

**Fastest path:** `git apply api/notify/badri_integration.patch`, then delete your dev DB (the notifications table changes), then run `deploy/smoke_test.sh`. The patch is the exact code below. It was applied to a copy of `main` at commit 4ae3892 and tested there: all 160 pytest tests and all 29 smoke checks passed. Read the sections below if the patch no longer applies cleanly.

`api/notify` is pure: no database, no clock reads, no network (except `email_sender.py`). You pass in times, rosters and a seeded `random.Random`, and you persist the rows it returns. `api/app/notify_wiring.py` (in the patch) is the only file that touches the Store.

---

## 1. What `api/notify` gives you

| Function | Input | Output |
|---|---|---|
| `package.build_preview(evaluation, profile, roster, posture=None, *, now_sim)` | recommendation dict, facility profile, roster rows (contract shape, `mocks/seed/`), sim time | Contract notification object with `preview: true`, null ids, empty deliveries and escalation |
| `package.build_package(..., notification_id, approval_id, standing_policy, preview=False)` | same | Real notification object |
| `service.notify(key, outbox, evaluation, profile, roster, *, send_email_fn, posture, approval_id, notification_id, now_sim, rng, next_delivery_id, next_timer_id, standing_policy=None, storm=False)` | `key = service.idempotency_key(evaluation_id, "approval" \| "shelter_in_place")`; `outbox` is dict-like | `(result, created)`. `result = {"notification", "plan", "timers", "posture", "email"}`. If `key` is already in `outbox`, returns the stored one with `created=False` and **sends nothing** |
| `escalation.schedule_approval_timers(evaluation, profile, now_sim, next_id, shelter_in_place=False)` | | Timer rows: backup after W, or urgent primary+backup now |
| `escalation.fire_due(timers, now_sim, ctx, next_id, on_fire=None)` | pending timer rows; `ctx = {"evaluation", "roster", "recipient_status_at"}` | `(fired_rows, new_rows, actions)`. Fires in (due, id) order. `on_fire(timer, action)` runs after each one |
| `escalation.cancel_on_decision(timers, evaluation_id, now_sim)` | | Rows it cancelled |
| `escalation.escalation_view(timers, tz_name)` | timer rows | Contract `escalation[]`: `{step, label, due_sim, fired_at_sim}` |
| `standing_policy.should_auto_send(evaluation, now_sim)` | | `True` only for a Tornado Warning (active or imminent) or a Warning with onset in the next 30 min. A `safety_instruction` alone never sends |
| `email_sender.send_email(subject, text)` | | `{ok, mode: "resend" \| "log_only", provider_ref, error}`. Never raises. Always sends to `DEMO_EMAIL_TO` |
| `simulator.recipient_status_from_deliveries(rows)` | stored delivery rows | `{employee_id: acknowledged \| delivered \| unreachable \| pending}` |
| `api/clock.py`: `SystemClock`, `SimulatedClock`, `clock_from_config(store.clock_config())` | | Same math and the same `{mode, now_sim, now_wall, speed}` shape as your store clock. Use `clock.jump(30)` if you ever want a server-side jump |

**Timer rows** match your `timers` table: `{id, kind, due_at_sim, payload, fired_at_sim, cancelled_at_sim, created_at_sim}`. There are two families:

- **Escalation kinds:** `manager_no_response_to_backup`, `urgent_primary_and_backup`, `backup_silent_unresolved`, `unacknowledged_to_supervisors`, `shelter_notify_approver`. These show in `escalation[]`.
- **`delivery_status`:** one row per planned delivery status change. Firing a `queued` row means "create the delivery row". Firing any other row means "append this status with `status_at_sim = due_at_sim`".

Because both families live in the same table and fire in due order, fast-forward replays deliveries and escalations in the right order.

**Real email:** one per notification. It goes to the first included person's email channel and is redirected to `DEMO_EMAIL_TO`. That delivery has `real: true` only if Resend actually accepted it. In log-only mode it has `real: false`, so the UI never claims a send that did not happen. If Resend fails, that person fails over to their next channel.

---

## 2. Schema change (`api/store/database.py`)

In `notifications`, change one line and add one column:

```sql
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id),   -- was: NOT NULL UNIQUE
    approval_id TEXT REFERENCES approvals(id),
    idempotency_key TEXT NOT NULL UNIQUE,                     -- new
```

Why: one evaluation can have both a shelter-in-place send (`eval_0042:shelter_in_place`) and a later approved send (`eval_0042:approval`). The UNIQUE constraint moves to `idempotency_key`, so a double approve still cannot insert twice.

`CREATE TABLE IF NOT EXISTS` will not change an existing file. Back up and delete the dev DB once:
`cp data/closureiq.db data/backup-$(date +%H%M).db && rm data/closureiq.db`

The `timers`, `deliveries` and `delivery_status_history` tables are used as they are.

---

## 3. Store (`api/store/repository.py`)

**Replace** `append_notification`, `append_delivery` and `append_delivery_status` with these versions. Each adds optional parameters, so existing callers keep working:

```python
    def append_notification(self, *, evaluation_id: str, approval_id: str | None,
                            package: dict, ack_deadline: str | None = None,
                            next_update: str | None = None, standing_policy: str | None = None,
                            preview: bool = False, notification_id: str | None = None,
                            idempotency_key: str | None = None) -> dict:
        notification_id = notification_id or self._next_id("ntf")
        idempotency_key = idempotency_key or f"{evaluation_id}:{standing_policy or 'approval'}"
        wall = iso()
        sim = self.clock_now_sim()
        with self.db.connect() as con:
            con.execute(
                """INSERT INTO notifications
                (id,evaluation_id,approval_id,standing_policy,package_json,ack_deadline,next_update,preview,created_at_wall,created_at_sim,idempotency_key)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (notification_id, evaluation_id, approval_id, standing_policy, _json_dump(package),
                 ack_deadline, next_update, int(preview), wall, sim, idempotency_key),
            )
        return self.get_notification(notification_id)

    def append_delivery(self, *, notification_id: str, recipient_id: str, channel: str,
                        real: bool = False, status: str = "simulated", provider_ref: str | None = None,
                        delivery_id: str | None = None, at_sim: str | None = None) -> dict:
        delivery_id = delivery_id or self._next_id("dlv")
        wall = iso()
        sim = at_sim or self.clock_now_sim()
        with self.db.connect() as con:
            con.execute(
                "INSERT INTO deliveries(id,notification_id,recipient_id,channel,real,provider_ref,created_at_wall,created_at_sim) VALUES(?,?,?,?,?,?,?,?)",
                (delivery_id, notification_id, recipient_id, channel, int(real), provider_ref, wall, sim),
            )
        self.append_delivery_status(delivery_id, status, at_sim=at_sim)
        return self.get_delivery(delivery_id)

    def append_delivery_status(self, delivery_id: str, status: str, at_sim: str | None = None) -> dict:
        event_id = self._next_id("dse")
        wall = iso()
        sim = at_sim or self.clock_now_sim()
        with self.db.connect() as con:
            con.execute(
                "INSERT INTO delivery_status_history(event_id,delivery_id,status,status_at_wall,status_at_sim) VALUES(?,?,?,?,?)",
                (event_id, delivery_id, status, wall, sim),
            )
        return self.get_delivery(delivery_id)
```

**Add** these methods to `Store`:

```python
    def get_notification_by_key(self, idempotency_key: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute("SELECT id FROM notifications WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        return self.get_notification(row["id"]) if row else None

    def append_timer(self, row: dict) -> None:
        """Insert one timer row built by api/notify (it already has its id and due_at_sim)."""
        with self.db.connect() as con:
            con.execute(
                """INSERT INTO timers(id,kind,due_at_sim,payload_json,fired_at_sim,cancelled_at_sim,created_at_wall,created_at_sim)
                VALUES(?,?,?,?,?,?,?,?)""",
                (row["id"], row["kind"], row["due_at_sim"], _json_dump(row["payload"]), row.get("fired_at_sim"),
                 row.get("cancelled_at_sim"), iso(), row.get("created_at_sim") or self.clock_now_sim()),
            )

    @staticmethod
    def _timer_row(row) -> dict:
        record = dict(row)
        record["payload"] = _json_load(record.pop("payload_json"), {})
        return record

    def list_timers(self, evaluation_id: str | None = None, pending_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM timers"
        if pending_only:
            sql += " WHERE fired_at_sim IS NULL AND cancelled_at_sim IS NULL"
        with self.db.connect() as con:
            rows = [self._timer_row(r) for r in con.execute(sql + " ORDER BY rowid").fetchall()]
        if evaluation_id:
            rows = [r for r in rows if r["payload"].get("evaluation_id") == evaluation_id]
        return rows

    def mark_timer_fired(self, timer_id: str, at_sim: str) -> None:
        """The one allowed update: fired_at_sim is set once, plus an audit row."""
        with self.db.connect() as con:
            con.execute("UPDATE timers SET fired_at_sim=? WHERE id=? AND fired_at_sim IS NULL", (at_sim, timer_id))
        self.append_audit("timer.fired", {"timer_id": timer_id, "at_sim": at_sim})

    def mark_timer_cancelled(self, timer_id: str, at_sim: str) -> None:
        with self.db.connect() as con:
            con.execute("UPDATE timers SET cancelled_at_sim=? WHERE id=? AND cancelled_at_sim IS NULL AND fired_at_sim IS NULL",
                        (at_sim, timer_id))
        self.append_audit("timer.cancelled", {"timer_id": timer_id, "at_sim": at_sim})
```

---

## 4. New file `api/app/notify_wiring.py`

This file is in the patch; copy it from there (`git apply` creates it). It has these functions:

| Function | Call it from | What it does |
|---|---|---|
| `preview(store, record, facility, posture)` | GET package-preview | Returns the preview body |
| `on_decision(store, evaluation, facility, approval, final_posture)` | approve, override, reject (right after `append_approval`) | Cancels the manager-response timers. Unless the action is reject, it builds and sends the notification once and stores the notification, timers and audit rows. Returns the stored notification (or `None` on reject) |
| `on_evaluation_created(store, evaluation, facility)` | evaluate (right after `append_evaluation`) | Starts the manager-response timers. If `should_auto_send`, also does the shelter-in-place send with `approval_id: null` and `standing_policy: "shelter_in_place"` |
| `run_due_timers(store, evaluation_lookup)` | every 1 s, and at the end of POST /api/clock | Fires due timers in order and writes delivery rows and statuses. Returns `[(sse_event_name, data), ...]` for `delivery.updated` and `escalation.fired` |
| `escalation_for(store, evaluation_id, tz_name)` | GET /api/notifications/{id} | Returns the contract `escalation[]` |

Rosters come from `mocks/seed/roster_<facility_id>.json`. A facility with no seed roster (today that is `central-fl-service-center`) uses the KC roster as the template. The seeded random generator is `random.Random(f"{evaluation_id}:{kind}")`, so the same evaluation always simulates the same way. Storm mode is on when `NOTIFY_STORM_MODE=1`.

---

## 5. Route changes (`api/app/routes.py`)

1. Imports: replace `from api.app.notification_adapter import build_package, preview_response` with `from api.app import notify_wiring`.
2. **package-preview:** `return notify_wiring.preview(store, record, get_facility(record["facility_id"]), posture)`
3. **`_create_notification`** (used by approve and override): replace the body with:
   ```python
   facility = get_facility(evaluation["facility_id"])
   notification = notify_wiring.on_decision(store, evaluation, facility, approval, final_posture)
   return {"id": notification["id"]} if notification else None
   ```
   Your `already_decided` check stays. `on_decision` is a second guard: even if two requests got past that check, the UNIQUE `idempotency_key` plus `service.notify_once` send only once.
4. **reject:** after `append_approval(...)`, add `notify_wiring.on_decision(store, record["result"], get_facility(record["facility_id"]), approval, None)`. This cancels the timers and sends nothing.
5. **GET /api/notifications/{id}:** before the `return`, add `record["escalation"] = notify_wiring.escalation_for(store_from_request(request), record["evaluation_id"], timezone_name)`.
6. **POST /api/clock:** **this is a bug today.** `set_clock` is a plain `def` that calls `asyncio.create_task`, so every POST /api/clock returns 500 "no running event loop". Make it `async def`, then fire timers right away so a jump shows its effect in the same request:
   ```python
   @router.post("/clock")
   async def set_clock(body: ClockRequest, request: Request):
       ...validation unchanged...
       store = store_from_request(request)
       result = store.set_clock(body.mode, body.speed, body.set_to)
       asyncio.create_task(event_hub.publish("clock.changed", result))
       for name, data in notify_wiring.run_due_timers(store, lambda eid: store.get_evaluation(eid)["result"]):
           asyncio.create_task(event_hub.publish(name, data))
       return result
   ```
   **Jump ahead 30 minutes** = the frontend sends `{"mode": "simulated", "speed": 1, "set_to": now_sim + 30 min}`. The contract does not change.
7. **evaluate:** after `saved = evaluation["result"]`, add `notify_wiring.on_evaluation_created(store, saved, facility)`.
8. **ack:** no change needed. Your handler appends `acknowledged` once. Acknowledgment means *received*; never label it "understood" in the UI.

## 6. Worker (`api/main.py`)

Inside `lifespan`, next to `alerts_job`, add the job below. APScheduler is already in requirements.txt.

```python
            async def timers_job():
                from api.app import notify_wiring
                for name, data in notify_wiring.run_due_timers(store, lambda eid: store.get_evaluation(eid)["result"]):
                    await event_hub.publish(name, data)
```

Then register it:

```python
                scheduler.add_job(timers_job, "interval", seconds=1, id="notify-timers", max_instances=1, coalesce=True)
```

The fallback loop without APScheduler does not run timers. POST /api/clock still fires them, which is enough for the demo.

## 7. Environment (`.env.example` has the names; never commit values)

`EMAIL_PROVIDER=resend`, `EMAIL_PROVIDER_KEY`, `DEMO_EMAIL_TO`, `EMAIL_FROM` (optional) and `NOTIFY_STORM_MODE` (optional, `1` = storm). With no key or no `DEMO_EMAIL_TO`, email runs in log-only mode.

## 8. Check it

```bash
pytest                                    # all tests, including api/notify/tests
uvicorn api.main:app --port 8000          # in one terminal (use a fresh DB)
deploy/smoke_test.sh http://127.0.0.1:8000
```

You should see `Passed: 29  Failed: 0`. The smoke test writes data (it approves or overrides, then acknowledges and moves the clock), so do not run it on the demo DB just before the pitch.

## 9. Contract additions (in docs/contract.md)

Each `messages[]` item also has `variant` (`standard`, `large_print`, `spanish`) and `needs_translation` (bool). `package` also has `warnings[]`, where each item is `{type: "needs_translation" | "missing_parameters", message_id, group, variant, employee_ids, text}`. The UI shows the warnings next to the package before approval.
