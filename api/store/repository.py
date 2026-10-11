"""Repository layer. Evidence, evaluations, approvals and audit rows are append-only."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from api.store.database import Database


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_load(value: str | None, default=None):
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


class Store:
    def __init__(self, db_path: str | Path, default_data_mode: str = "live"):
        self.db = Database(db_path)
        self._ensure_defaults(default_data_mode)

    def _ensure_defaults(self, default_data_mode: str = "live") -> None:
        now = iso()
        with self.db.connect() as con:
            con.execute(
                "INSERT OR IGNORE INTO app_settings(key,value_json,updated_at) VALUES(?,?,?)",
                ("data_mode", _json_dump(default_data_mode if default_data_mode in {"live", "replay"} else "live"), now),
            )
            con.execute(
                "INSERT OR IGNORE INTO app_settings(key,value_json,updated_at) VALUES(?,?,?)",
                ("clock", _json_dump({"mode": "system", "speed": 1.0, "base_sim": now, "base_wall": now}), now),
            )
            con.execute(
                "INSERT OR IGNORE INTO app_settings(key,value_json,updated_at) VALUES(?,?,?)",
                ("last_poll_at", "null", now),
            )

    def _next_id(self, prefix: str) -> str:
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT value FROM counters WHERE prefix=?", (prefix,)).fetchone()
            value = (row["value"] if row else 0) + 1
            con.execute(
                "INSERT INTO counters(prefix,value) VALUES(?,?) ON CONFLICT(prefix) DO UPDATE SET value=excluded.value",
                (prefix, value),
            )
            con.commit()
        return f"{prefix}_{value:04d}"

    def _setting(self, key: str, default=None):
        with self.db.connect() as con:
            row = con.execute("SELECT value_json FROM app_settings WHERE key=?", (key,)).fetchone()
        return _json_load(row["value_json"], default) if row else default

    def _set_setting(self, key: str, value: Any) -> None:
        with self.db.connect() as con:
            con.execute(
                "INSERT INTO app_settings(key,value_json,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                (key, _json_dump(value), iso()),
            )

    def get_data_mode(self, fallback: str = "live") -> str:
        value = self._setting("data_mode", fallback)
        return value if value in {"live", "replay"} else fallback

    def set_data_mode(self, data_mode: str) -> None:
        self._set_setting("data_mode", data_mode)

    def set_last_poll_at(self, value: str) -> None:
        self._set_setting("last_poll_at", value)

    def get_last_poll_at(self) -> str | None:
        return self._setting("last_poll_at")

    def clock_config(self) -> dict:
        return self._setting("clock", {"mode": "system", "speed": 1.0, "base_sim": iso(), "base_wall": iso()})

    @staticmethod
    def _parse_time(value: str | None) -> datetime:
        try:
            parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return utc_now()

    def clock_now_sim(self) -> str:
        cfg = self.clock_config()
        wall_now = utc_now()
        if cfg.get("mode") != "simulated":
            return wall_now.isoformat()
        base_wall = self._parse_time(cfg.get("base_wall"))
        base_sim = self._parse_time(cfg.get("base_sim"))
        speed = max(0.0, float(cfg.get("speed", 1.0)))
        return (base_sim + timedelta(seconds=max(0.0, (wall_now - base_wall).total_seconds()) * speed)).isoformat()

    def set_clock(self, mode: str, speed: float = 1.0, set_to: str | None = None) -> dict:
        now = utc_now()
        sim = self._parse_time(set_to) if set_to else now
        cfg = {"mode": mode, "speed": float(speed), "base_sim": sim.isoformat(), "base_wall": now.isoformat()}
        self._set_setting("clock", cfg)
        self.append_audit("clock.changed", {"mode": mode, "speed": speed, "set_to": set_to})
        return self.get_clock()

    def get_clock(self) -> dict:
        cfg = self.clock_config()
        now_wall = utc_now()
        if cfg.get("mode") == "simulated":
            now_sim = self.clock_now_sim()
        else:
            now_sim = now_wall.isoformat()
        return {"mode": cfg.get("mode", "system"), "now_sim": now_sim,
                "now_wall": now_wall.isoformat(), "speed": float(cfg.get("speed", 1.0))}

    def append_snapshot(self, *, facility_id: str, source: str, url: str,
                        fetched_at_wall: str, fetched_at_sim: str, http_status: int | None,
                        raw_payload: str, source_updated_at: str | None, ok: bool,
                        error_text: str | None, data_mode: str) -> dict:
        snapshot_id = self._next_id("snap")
        with self.db.connect() as con:
            con.execute(
                """INSERT INTO evidence_snapshots
                (id,facility_id,source,url,fetched_at_wall,fetched_at_sim,http_status,raw_payload,
                 source_updated_at,ok,error_text,data_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (snapshot_id, facility_id, source, url, fetched_at_wall, fetched_at_sim,
                 http_status, raw_payload or "{}", source_updated_at, int(ok), error_text, data_mode),
            )
        return self.get_snapshot(snapshot_id)

    @staticmethod
    def _snapshot_row(row) -> dict:
        return {**dict(row), "ok": bool(row["ok"]), "raw_payload_json": _json_load(row["raw_payload"], {})}

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM evidence_snapshots WHERE id=?", (snapshot_id,)).fetchone()
        return self._snapshot_row(row) if row else None

    def latest_snapshot(self, facility_id: str, source: str, successful_only: bool = False) -> dict | None:
        where_ok = " AND ok=1" if successful_only else ""
        with self.db.connect() as con:
            row = con.execute(
                f"SELECT * FROM evidence_snapshots WHERE facility_id=? AND source=?{where_ok} ORDER BY rowid DESC LIMIT 1",
                (facility_id, source),
            ).fetchone()
        return self._snapshot_row(row) if row else None

    def latest_snapshots(self, facility_id: str) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                """SELECT s.* FROM evidence_snapshots s
                   JOIN (SELECT source, MAX(rowid) max_rowid FROM evidence_snapshots
                         WHERE facility_id=? GROUP BY source) latest ON latest.max_rowid=s.rowid
                   WHERE s.facility_id=? ORDER BY s.rowid""", (facility_id, facility_id)
            ).fetchall()
        return [self._snapshot_row(r) for r in rows]

    def snapshots_by_ids(self, snapshot_ids: list[str]) -> list[dict]:
        if not snapshot_ids:
            return []
        placeholders = ",".join("?" for _ in snapshot_ids)
        with self.db.connect() as con:
            rows = con.execute(f"SELECT * FROM evidence_snapshots WHERE id IN ({placeholders})", snapshot_ids).fetchall()
        by_id = {r["id"]: self._snapshot_row(r) for r in rows}
        return [by_id[sid] for sid in snapshot_ids if sid in by_id]

    def all_success_snapshots(self, facility_id: str) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                """SELECT s.* FROM evidence_snapshots s JOIN
                   (SELECT source, MAX(rowid) max_rowid FROM evidence_snapshots
                    WHERE facility_id=? AND ok=1 GROUP BY source) latest ON latest.max_rowid=s.rowid
                   WHERE s.facility_id=? ORDER BY s.rowid""", (facility_id, facility_id)
            ).fetchall()
        return [self._snapshot_row(r) for r in rows]

    def append_evaluation(self, *, facility_id: str, evaluated_at_wall: str,
                          evaluated_at_sim: str, data_mode: str, evidence_ids: list[str],
                          engine_version: str, policy_version: str, result: dict,
                          posture: str, confidence: str, supersedes: str | None) -> dict:
        evaluation_id = self._next_id("eval")
        result_copy = dict(result)
        result_copy["evaluation_id"] = evaluation_id
        result_copy["supersedes"] = supersedes
        result_copy["facility_id"] = facility_id
        result_copy.setdefault("evaluated_at", evaluated_at_wall)
        result_copy["data_mode"] = data_mode
        result_copy["hypothetical"] = False
        with self.db.connect() as con:
            con.execute(
                """INSERT INTO evaluations
                (id,facility_id,evaluated_at_wall,evaluated_at_sim,data_mode,evidence_ids_json,
                 engine_version,policy_version,result_json,posture,confidence,supersedes)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (evaluation_id, facility_id, evaluated_at_wall, evaluated_at_sim, data_mode,
                 _json_dump(evidence_ids), engine_version, policy_version, _json_dump(result_copy),
                 posture, confidence, supersedes),
            )
        return self.get_evaluation(evaluation_id)

    @staticmethod
    def _evaluation_row(row) -> dict:
        if not row:
            return None
        result = _json_load(row["result_json"], {})
        result.setdefault("evaluation_id", row["id"])
        result.setdefault("facility_id", row["facility_id"])
        result.setdefault("evaluated_at", row["evaluated_at_wall"])
        result.setdefault("data_mode", row["data_mode"])
        result.setdefault("hypothetical", False)
        return {"id": row["id"], "facility_id": row["facility_id"],
                "evaluated_at_wall": row["evaluated_at_wall"], "evaluated_at_sim": row["evaluated_at_sim"],
                "data_mode": row["data_mode"], "evidence_ids": _json_load(row["evidence_ids_json"], []),
                "engine_version": row["engine_version"], "policy_version": row["policy_version"],
                "posture": row["posture"], "confidence": row["confidence"],
                "supersedes": row["supersedes"], "result": result}

    def get_evaluation(self, evaluation_id: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM evaluations WHERE id=?", (evaluation_id,)).fetchone()
        return self._evaluation_row(row) if row else None

    def latest_evaluation(self, facility_id: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM evaluations WHERE facility_id=? ORDER BY rowid DESC LIMIT 1", (facility_id,)).fetchone()
        return self._evaluation_row(row) if row else None

    def list_evaluations(self, facility_id: str | None = None, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        with self.db.connect() as con:
            if facility_id:
                rows = con.execute("SELECT * FROM evaluations WHERE facility_id=? ORDER BY rowid DESC LIMIT ?", (facility_id, limit)).fetchall()
            else:
                rows = con.execute("SELECT * FROM evaluations ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return [self._evaluation_row(r) for r in rows]

    def append_approval(self, *, evaluation_id: str, action: str, final_posture: str,
                        actor: str, reason: str | None) -> dict:
        approval_id = self._next_id("apr")
        wall = iso()
        sim = self.clock_now_sim()
        with self.db.connect() as con:
            con.execute(
                "INSERT INTO approvals(id,evaluation_id,action,final_posture,actor,reason,acted_at_wall,acted_at_sim) VALUES(?,?,?,?,?,?,?,?)",
                (approval_id, evaluation_id, action, final_posture, actor, reason, wall, sim),
            )
        return self.get_approval_by_evaluation(evaluation_id)

    def get_approval_by_evaluation(self, evaluation_id: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM approvals WHERE evaluation_id=?", (evaluation_id,)).fetchone()
        return dict(row) if row else None


    def get_notification(self, notification_id: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
        if not row:
            return None
        record = dict(row)
        record["package"] = _json_load(record.pop("package_json"), {})
        record["preview"] = bool(record["preview"])
        record["deliveries"] = self.list_deliveries(notification_id)
        record["escalation"] = []
        return record

    def get_notification_by_evaluation(self, evaluation_id: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute("SELECT id FROM notifications WHERE evaluation_id=? ORDER BY rowid DESC LIMIT 1", (evaluation_id,)).fetchone()
        return self.get_notification(row["id"]) if row else None



    def get_delivery(self, delivery_id: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
            history = con.execute("SELECT * FROM delivery_status_history WHERE delivery_id=? ORDER BY rowid", (delivery_id,)).fetchall()
        if not row:
            return None
        result = dict(row)
        result["real"] = bool(result["real"])
        result["status_history"] = [dict(r) for r in history]
        if history:
            latest = history[-1]
            result["status"] = latest["status"]
            result["status_at_wall"] = latest["status_at_wall"]
            result["status_at_sim"] = latest["status_at_sim"]
        else:
            result["status"] = None
            result["status_at_wall"] = None
            result["status_at_sim"] = None
        return result

    def list_deliveries(self, notification_id: str) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute("SELECT id FROM deliveries WHERE notification_id=? ORDER BY rowid", (notification_id,)).fetchall()
        return [self.get_delivery(r["id"]) for r in rows]

    def append_audit(self, kind: str, detail: dict) -> dict:
        audit_id = self._next_id("aud")
        row = {"id": audit_id, "at_wall": iso(), "at_sim": self.clock_now_sim(), "kind": kind, "detail": detail}
        with self.db.connect() as con:
            con.execute("INSERT INTO audit_log(id,at_wall,at_sim,kind,detail_json) VALUES(?,?,?,?,?)",
                        (row["id"], row["at_wall"], row["at_sim"], kind, _json_dump(detail)))
        return row

    def list_audit(self, evaluation_id: str | None = None, limit: int = 500) -> list[dict]:
        limit = max(1, min(int(limit), 2000))
        with self.db.connect() as con:
            rows = con.execute("SELECT * FROM audit_log ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        rows = list(reversed(rows))
        records = []
        for row in rows:
            detail = _json_load(row["detail_json"], {})
            if evaluation_id and detail.get("evaluation_id") != evaluation_id and detail.get("based_on") != evaluation_id:
                continue
            records.append({"id": row["id"], "at_wall": row["at_wall"], "at_sim": row["at_sim"], "kind": row["kind"], "detail": detail})
        return records

    def record_for_evaluation(self, evaluation_id: str) -> dict | None:
        evaluation = self.get_evaluation(evaluation_id)
        if not evaluation:
            return None
        chain: list[str] = []
        current = evaluation
        while current:
            chain.append(current["id"])
            previous = current.get("supersedes")
            current = self.get_evaluation(previous) if previous else None
        chain.reverse()
        evidence = self.snapshots_by_ids(evaluation.get("evidence_ids", []))
        approval = self.get_approval_by_evaluation(evaluation_id)
        notification = self.get_notification_by_evaluation(evaluation_id)
        deliveries = notification["deliveries"] if notification else []
        timers = []
        with self.db.connect() as con:
            timer_rows = con.execute("SELECT * FROM timers ORDER BY rowid").fetchall()
        timers = [dict(r) for r in timer_rows if _json_load(r["payload_json"], {}).get("evaluation_id") == evaluation_id]
        audit_log = self.list_audit(evaluation_id)
        return {"evaluation": evaluation["result"], "chain": chain,
                "evidence": [{"snapshot_id": s["id"], "source": s["source"], "url": s["url"],
                              "fetched_at_wall": s["fetched_at_wall"], "fetched_at_sim": s["fetched_at_sim"],
                              "http_status": s["http_status"], "ok": s["ok"],
                              "raw_payload": s["raw_payload_json"], "error": s["error_text"]} for s in evidence],
                "approval": approval, "notification": notification, "deliveries": deliveries,
                "timers": timers, "audit_log": audit_log}

    def all_evidence_for_facility(self, facility_id: str) -> list[dict]:
        return self.all_success_snapshots(facility_id)

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

    # ---- notify integration (pasted from api/notify/INTEGRATION.md) ----

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
