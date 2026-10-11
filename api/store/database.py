"""SQLite database setup with append-only protections for audit/evidence rows."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator


APPEND_ONLY_TABLES = (
    "evidence_snapshots", "evaluations", "approvals", "notifications",
    "deliveries", "delivery_status_history", "audit_log",
)


SCHEMA = r"""
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counters (
    prefix TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_snapshots (
    id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    fetched_at_wall TEXT NOT NULL,
    fetched_at_sim TEXT NOT NULL,
    http_status INTEGER,
    raw_payload TEXT NOT NULL,
    source_updated_at TEXT,
    ok INTEGER NOT NULL CHECK(ok IN (0,1)),
    error_text TEXT,
    data_mode TEXT NOT NULL CHECK(data_mode IN ('live','replay'))
);
CREATE INDEX IF NOT EXISTS ix_snapshots_facility_source_time
    ON evidence_snapshots(facility_id, source, fetched_at_wall DESC);
CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    evaluated_at_wall TEXT NOT NULL,
    evaluated_at_sim TEXT NOT NULL,
    data_mode TEXT NOT NULL CHECK(data_mode IN ('live','replay')),
    evidence_ids_json TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    result_json TEXT NOT NULL,
    posture TEXT NOT NULL,
    confidence TEXT NOT NULL,
    supersedes TEXT
);
CREATE INDEX IF NOT EXISTS ix_evaluations_facility_time
    ON evaluations(facility_id, evaluated_at_wall DESC);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL UNIQUE REFERENCES evaluations(id),
    action TEXT NOT NULL CHECK(action IN ('approve','reject','override')),
    final_posture TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT,
    acted_at_wall TEXT NOT NULL,
    acted_at_sim TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
    approval_id TEXT REFERENCES approvals(id),
    idempotency_key TEXT NOT NULL UNIQUE,
    standing_policy TEXT,
    package_json TEXT NOT NULL,
    ack_deadline TEXT,
    next_update TEXT,
    preview INTEGER NOT NULL DEFAULT 0 CHECK(preview IN (0,1)),
    created_at_wall TEXT NOT NULL,
    created_at_sim TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deliveries (
    id TEXT PRIMARY KEY,
    notification_id TEXT NOT NULL REFERENCES notifications(id),
    recipient_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    real INTEGER NOT NULL CHECK(real IN (0,1)),
    provider_ref TEXT,
    created_at_wall TEXT NOT NULL,
    created_at_sim TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_deliveries_notification ON deliveries(notification_id);
CREATE TABLE IF NOT EXISTS delivery_status_history (
    event_id TEXT PRIMARY KEY,
    delivery_id TEXT NOT NULL REFERENCES deliveries(id),
    status TEXT NOT NULL CHECK(status IN ('queued','sent','delivered','simulated','failed','acknowledged')),
    status_at_wall TEXT NOT NULL,
    status_at_sim TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_delivery_history_delivery_time
    ON delivery_status_history(delivery_id, status_at_wall);
CREATE TABLE IF NOT EXISTS timers (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    due_at_sim TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    fired_at_sim TEXT,
    cancelled_at_sim TEXT,
    created_at_wall TEXT NOT NULL,
    created_at_sim TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    at_wall TEXT NOT NULL,
    at_sim TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail_json TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as con:
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript(SCHEMA)
            for table in APPEND_ONLY_TABLES:
                # App code never mutates these rows; triggers also protect them from accidental SQL.
                con.executescript(f"""
                    CREATE TRIGGER IF NOT EXISTS {table}_no_update
                    BEFORE UPDATE ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;
                    CREATE TRIGGER IF NOT EXISTS {table}_no_delete
                    BEFORE DELETE ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;
                """)
