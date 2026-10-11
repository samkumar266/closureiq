"""Minimal append-only SQLite storage used by the API boundary."""

from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from pathlib import Path
from typing import Any

from .engine import FacilityPolicy, InputEvidence, Recommendation


class SQLiteStore:
    """Store evaluations, evidence snapshots, and audit events without updates."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    facility_id TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    facility_policy_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    evaluation_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    FOREIGN KEY (evaluation_id) REFERENCES evaluations(evaluation_id)
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    detail_json TEXT NOT NULL
                );
                """
            )
            connection.commit()

    def save_evaluation(
        self,
        recommendation: Recommendation,
        evidence: list[InputEvidence],
        facility: FacilityPolicy,
    ) -> None:
        """Append a real evaluation and its evidence snapshots.

        Hypothetical recommendations are rejected here so callers cannot
        accidentally persist a what-if through the normal evaluation path.
        """
        ensure_real_recommendation(recommendation)
        if recommendation.facility_id != facility.facility_id:
            raise ValueError("facility does not match recommendation")
        with closing(self._connect()) as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO evaluations
                    (evaluation_id, facility_id, result_json, facility_policy_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        recommendation.evaluation_id,
                        recommendation.facility_id,
                        _json(recommendation.model_dump(mode="json")),
                        _json(facility.model_dump(mode="json")),
                        recommendation.evaluated_at.isoformat(),
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO evidence_snapshots
                    (snapshot_id, evaluation_id, source, evidence_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (
                            item.snapshot_id,
                            recommendation.evaluation_id,
                            item.source,
                            _json(item.model_dump(mode="json")),
                        )
                        for item in evidence
                    ],
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def get_evaluation(
        self, evaluation_id: str
    ) -> tuple[Recommendation, FacilityPolicy] | None:
        """Load a recommendation and its policy profile by ID."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT result_json, facility_policy_json
                FROM evaluations WHERE evaluation_id = ?
                """,
                (evaluation_id,),
            ).fetchone()
        if row is None:
            return None
        return (
            Recommendation.model_validate(json.loads(row["result_json"])),
            FacilityPolicy.model_validate(json.loads(row["facility_policy_json"])),
        )

    def get_evidence(self, evaluation_id: str) -> list[InputEvidence]:
        """Load the immutable evidence snapshots associated with an evaluation."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT evidence_json FROM evidence_snapshots
                WHERE evaluation_id = ? ORDER BY rowid
                """,
                (evaluation_id,),
            ).fetchall()
        return [
            InputEvidence.model_validate(json.loads(row["evidence_json"]))
            for row in rows
        ]

    def get_evidence_snapshot(self, snapshot_id: str) -> InputEvidence | None:
        """Read one immutable evidence snapshot by its documented ID."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT evidence_json FROM evidence_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        if row is None:
            return None
        return InputEvidence.model_validate(json.loads(row["evidence_json"]))

    def list_affected_employees(
        self, evaluation_id: str, employee_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Read the seeded facility roster without changing persisted records."""
        stored = self.get_evaluation(evaluation_id)
        if stored is None:
            raise ValueError("evaluation was not found")
        facility_id = stored[0].facility_id
        roster_path = Path(__file__).parent.parent / "mocks" / "seed" / f"roster_{facility_id}.json"
        if not roster_path.exists():
            raise ValueError(f"roster is unavailable for facility {facility_id}")
        payload = json.loads(roster_path.read_text(encoding="utf-8"))
        employees = payload.get("employees")
        if not isinstance(employees, list):
            raise ValueError("roster data is malformed")
        if not employee_filter:
            return employees
        normalized = employee_filter.lower().replace("_", "-").replace(" ", "-")
        return [
            employee
            for employee in employees
            if isinstance(employee, dict)
            and (
                str(employee.get("group", "")).lower().replace("_", "-") == normalized
                or (
                    normalized == "essential"
                    and employee.get("essential") is True
                )
                or (
                    normalized == "not-telework-eligible"
                    and employee.get("telework_eligible") is False
                )
            )
        ]

    def append(self, kind: str, detail: dict[str, Any]) -> int:
        """Append one audit event; this is the only general-purpose write helper."""
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "INSERT INTO audit_log (kind, detail_json) VALUES (?, ?)",
                (kind, _json(detail)),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def audit_entries(self) -> list[dict[str, Any]]:
        """Return audit rows for verification and record readers."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT audit_id, kind, detail_json FROM audit_log ORDER BY audit_id"
            ).fetchall()
        return [
            {
                "audit_id": row["audit_id"],
                "kind": row["kind"],
                "detail": json.loads(row["detail_json"]),
            }
            for row in rows
        ]

    def evaluation_count(self) -> int:
        """Return the number of persisted normal evaluations."""
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM evaluations").fetchone()
        return int(row["count"])

    def next_whatif_id(self) -> str:
        """Allocate the next documented what-if identifier."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) + 1 AS next_id "
                "FROM audit_log WHERE kind = 'whatif'"
            ).fetchone()
        return f"wif_{int(row['next_id']):04d}"


def ensure_real_recommendation(recommendation: Recommendation) -> None:
    """Reject hypothetical results at persistence and approval boundaries."""
    if recommendation.hypothetical:
        raise ValueError("hypothetical recommendations cannot be persisted or approved")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
