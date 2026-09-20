from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DISPATCH_LEASE = timedelta(minutes=2)
MAX_DISPATCH_ATTEMPTS = 3


class IncidentStore:
    """Durable workflow state for alerts, issues, sessions, and pull requests.

    SQLite runs in WAL mode and dispatch claims use ``BEGIN IMMEDIATE``. A unique
    external event ID makes alert and GitHub webhook retries idempotent, while
    explicit session and artifact IDs keep concurrent runs isolated.
    """

    def __init__(self, database_path: str, default_repository: str = "") -> None:
        self.database_path = Path(database_path)
        self.default_repository = default_repository
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_alert(self, alert: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        now = self._iso_now()
        run_id = f"INC-{uuid4().hex[:8].upper()}"
        detected_at = alert.get("occurred_at") or now
        values = (
            run_id,
            alert["event_id"],
            "alert",
            alert.get("source", "custom"),
            alert["repository"],
            alert["title"],
            alert.get("service") or "unknown-service",
            alert.get("severity") or "SEV-3",
            "alert_received",
            detected_at,
            now,
            self._dump(alert.get("signals") or []),
            self._dump(alert.get("evidence") or {}),
            self._dump(alert.get("metadata") or {}),
            self._dump(alert),
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO workflow_runs (
                    id, external_event_id, source_type, source_name, repository,
                    title, service, severity, state, detected_at, updated_at,
                    signals_json, evidence_json, metadata_json, raw_event_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            created = cursor.rowcount == 1
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE external_event_id = ?",
                (alert["event_id"],),
            ).fetchone()
        return self._row(row), created

    def upsert_issue(
        self,
        issue: dict[str, Any],
        repository: str,
        linked_run_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        number = int(issue["number"])
        created_at = issue.get("created_at") or self._iso_now()
        issue_url = issue.get("html_url") or issue.get("url")
        labels = [
            label.get("name") if isinstance(label, dict) else str(label)
            for label in issue.get("labels", [])
        ]

        existing = self.get_by_issue(repository, number)
        if existing:
            self.bind_issue(existing["id"], issue)
            return self.get(existing["id"]), False

        linked_run = self.get(linked_run_id) if linked_run_id else None
        if (
            linked_run
            and linked_run["repository"] == repository
            and linked_run.get("issue_number") in {None, number}
        ):
            self.bind_issue(linked_run_id, issue)
            return self.get(linked_run_id), False

        external_event_id = f"github:{repository}:issue:{number}"
        run_id = f"ISS-{number}-{uuid4().hex[:5].upper()}"
        now = self._iso_now()
        metadata = {
            "labels": labels,
            "issue_state": issue.get("state"),
            "issue_body": issue.get("body") or "",
        }
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO workflow_runs (
                    id, external_event_id, source_type, source_name, repository,
                    title, service, severity, state, detected_at, updated_at,
                    signals_json, evidence_json, metadata_json, raw_event_json,
                    issue_number, issue_url, issue_created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    external_event_id,
                    "issue",
                    "github",
                    repository,
                    issue.get("title") or f"GitHub issue #{number}",
                    repository,
                    self._severity_from_labels(labels),
                    "issue_created",
                    created_at,
                    now,
                    "[]",
                    self._dump({"issue_body": issue.get("body") or ""}),
                    self._dump(metadata),
                    self._dump(issue),
                    number,
                    issue_url,
                    created_at,
                ),
            )
            created = cursor.rowcount == 1
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE external_event_id = ?",
                (external_event_id,),
            ).fetchone()
        run = self._row(row)
        self.add_event(
            run["id"],
            f"issue:{repository}:{number}",
            "issue_linked",
            {"number": number, "url": issue_url},
            created_at,
        )
        return run, created

    def claim_dispatch(self, run_id: str, stage: str) -> bool:
        if stage not in {"triage", "remediation"}:
            raise ValueError(f"Unknown dispatch stage: {stage}")
        session_column = f"{stage}_session_id"
        status_column = f"{stage}_dispatch_status"
        attempts_column = f"{stage}_attempts"
        now = datetime.now(timezone.utc)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"SELECT {session_column}, {status_column}, {attempts_column}, updated_at "
                "FROM workflow_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if not row or row[session_column]:
                connection.rollback()
                return False
            attempts = int(row[attempts_column] or 0)
            leased_at = self._as_datetime(row["updated_at"])
            lease_active = (
                row[status_column] == "dispatching"
                and leased_at is not None
                and now - leased_at < DISPATCH_LEASE
            )
            if lease_active or attempts >= MAX_DISPATCH_ATTEMPTS:
                connection.rollback()
                return False
            connection.execute(
                f"""
                UPDATE workflow_runs
                SET {status_column} = 'dispatching',
                    {attempts_column} = {attempts_column} + 1,
                    state = ?, error_detail = NULL, updated_at = ?
                WHERE id = ?
                """,
                (f"{stage}_dispatching", now.isoformat(), run_id),
            )
            connection.commit()
            return True
        finally:
            connection.close()

    def bind_session(
        self, run_id: str, stage: str, session: dict[str, Any]
    ) -> None:
        if stage not in {"triage", "remediation"}:
            raise ValueError(f"Unknown session stage: {stage}")
        session_id = session.get("session_id") or session.get("id")
        if not session_id:
            raise ValueError("Session response did not include a session ID")
        now = self._iso_now()
        state = "triaging" if stage == "triage" else "remediating"
        with self._connect() as connection:
            connection.execute(
                f"""
                UPDATE workflow_runs
                SET {stage}_session_id = ?, {stage}_session_url = ?,
                    {stage}_dispatch_status = 'dispatched', state = ?,
                    error_detail = NULL, updated_at = ?
                WHERE id = ?
                """,
                (session_id, session.get("url"), state, now, run_id),
            )
        self.add_event(
            run_id,
            f"session:{stage}:{session_id}",
            f"{stage}_session_started",
            {"session_id": session_id, "url": session.get("url")},
            self._timestamp_to_iso(session.get("created_at")) or now,
        )

    def mark_dispatch_failed(self, run_id: str, stage: str, detail: str) -> None:
        if stage not in {"triage", "remediation"}:
            raise ValueError(f"Unknown dispatch stage: {stage}")
        now = self._iso_now()
        with self._connect() as connection:
            connection.execute(
                f"""
                UPDATE workflow_runs
                SET {stage}_dispatch_status = 'failed', state = 'dispatch_failed',
                    error_detail = ?, updated_at = ? WHERE id = ?
                """,
                (detail[:2000], now, run_id),
            )
        self.add_event(
            run_id,
            f"dispatch-failed:{run_id}:{stage}:{now}",
            f"{stage}_dispatch_failed",
            {"detail": detail[:500]},
            now,
        )

    def bind_issue(self, run_id: str, issue: dict[str, Any]) -> None:
        number = int(issue["number"])
        url = issue.get("html_url") or issue.get("url")
        created_at = issue.get("created_at") or self._iso_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE workflow_runs SET issue_number = ?, issue_url = ?,
                    issue_created_at = ?, state = 'issue_created', updated_at = ?
                WHERE id = ?
                """,
                (number, url, created_at, self._iso_now(), run_id),
            )
        self.add_event(
            run_id,
            f"issue:{self.get(run_id)['repository']}:{number}",
            "issue_linked",
            {"number": number, "url": url},
            created_at,
        )

    def bind_pull_request(self, run_id: str, pull: dict[str, Any]) -> None:
        number = int(pull["number"])
        url = pull.get("html_url") or pull.get("url")
        created_at = pull.get("created_at") or self._iso_now()
        state = "merged" if pull.get("merged_at") else "pull_request_opened"
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE workflow_runs SET pull_request_number = ?,
                    pull_request_url = ?, pull_request_created_at = ?, state = ?,
                    updated_at = ? WHERE id = ?
                """,
                (number, url, created_at, state, self._iso_now(), run_id),
            )
        self.add_event(
            run_id,
            f"pull-request:{self.get(run_id)['repository']}:{number}",
            "pull_request_linked",
            {"number": number, "url": url},
            created_at,
        )

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._row(row) if row else None

    def get_by_issue(self, repository: str, number: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM workflow_runs
                WHERE repository = ? AND issue_number = ?
                """,
                (repository, number),
            ).fetchone()
        return self._row(row) if row else None

    def list(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_runs ORDER BY detected_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_type, payload_json, occurred_at
                FROM workflow_events WHERE run_id = ? ORDER BY occurred_at
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "payload": self._load(row["payload_json"], {}),
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]

    def add_event(
        self,
        run_id: str,
        event_key: str,
        event_type: str,
        payload: dict[str, Any],
        occurred_at: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO workflow_events (
                    run_id, event_key, event_type, payload_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_key,
                    event_type,
                    self._dump(payload),
                    occurred_at or self._iso_now(),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id TEXT PRIMARY KEY,
                    external_event_id TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    title TEXT NOT NULL,
                    service TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    state TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    signals_json TEXT NOT NULL DEFAULT '[]',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    raw_event_json TEXT NOT NULL DEFAULT '{}',
                    triage_session_id TEXT,
                    triage_session_url TEXT,
                    triage_dispatch_status TEXT NOT NULL DEFAULT 'pending',
                    triage_attempts INTEGER NOT NULL DEFAULT 0,
                    issue_number INTEGER,
                    issue_url TEXT,
                    issue_created_at TEXT,
                    remediation_session_id TEXT,
                    remediation_session_url TEXT,
                    remediation_dispatch_status TEXT NOT NULL DEFAULT 'pending',
                    remediation_attempts INTEGER NOT NULL DEFAULT 0,
                    pull_request_number INTEGER,
                    pull_request_url TEXT,
                    pull_request_created_at TEXT,
                    error_detail TEXT,
                    UNIQUE(repository, issue_number)
                );

                CREATE TABLE IF NOT EXISTS workflow_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
                    event_key TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS workflow_runs_updated_idx
                    ON workflow_runs(updated_at);
                CREATE INDEX IF NOT EXISTS workflow_events_run_idx
                    ON workflow_events(run_id, occurred_at);
                """
            )
            self._migrate_legacy_incidents(connection)
            self._repair_legacy_repositories(connection)

    def _migrate_legacy_incidents(self, connection: sqlite3.Connection) -> None:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='incidents'"
        ).fetchone()
        if not exists:
            return
        rows = connection.execute("SELECT * FROM incidents").fetchall()
        for row in rows:
            incident = dict(row)
            signals = [
                {
                    "key": "error_rate",
                    "label": "Error rate",
                    "value": incident["error_rate"],
                    "unit": "%",
                },
                {
                    "key": "p95_latency_ms",
                    "label": "p95 latency",
                    "value": incident["p95_latency_ms"],
                    "unit": "ms",
                },
                {
                    "key": "affected_sessions",
                    "label": "Affected sessions",
                    "value": incident["affected_sessions"],
                    "unit": None,
                },
            ]
            connection.execute(
                """
                INSERT OR IGNORE INTO workflow_runs (
                    id, external_event_id, source_type, source_name, repository,
                    title, service, severity, state, detected_at, updated_at,
                    signals_json, evidence_json, metadata_json, raw_event_json,
                    error_detail
                ) VALUES (?, ?, 'alert', 'legacy-demo', ?, ?, ?, ?, ?, ?, ?, ?,
                    '{}', '{}', '{}', ?)
                """,
                (
                    incident["id"],
                    f"legacy:{incident['id']}",
                    self.default_repository,
                    incident["title"],
                    incident["service"],
                    incident["severity"],
                    incident["status"],
                    incident["detected_at"],
                    incident["updated_at"],
                    self._dump(signals),
                    incident.get("error_detail"),
                ),
            )

    def _repair_legacy_repositories(self, connection: sqlite3.Connection) -> None:
        if not self.default_repository:
            return
        legacy_rows = connection.execute(
            "SELECT * FROM workflow_runs WHERE repository = ''"
        ).fetchall()
        for legacy_row in legacy_rows:
            legacy = dict(legacy_row)
            conflict = None
            if legacy.get("issue_number") is not None:
                conflict = connection.execute(
                    """
                    SELECT * FROM workflow_runs
                    WHERE repository = ? AND issue_number = ? AND id != ?
                    """,
                    (
                        self.default_repository,
                        legacy["issue_number"],
                        legacy["id"],
                    ),
                ).fetchone()
            if conflict is None:
                conflict = connection.execute(
                    """
                    SELECT * FROM workflow_runs
                    WHERE repository = ? AND source_type = 'issue'
                      AND raw_event_json LIKE ? AND id != ?
                    """,
                    (
                        self.default_repository,
                        f"%{legacy['id']}%",
                        legacy["id"],
                    ),
                ).fetchone()
            if conflict:
                duplicate = dict(conflict)
                connection.execute(
                    """
                    UPDATE workflow_runs SET
                        triage_session_id = COALESCE(triage_session_id, ?),
                        triage_session_url = COALESCE(triage_session_url, ?),
                        remediation_session_id = COALESCE(remediation_session_id, ?),
                        remediation_session_url = COALESCE(remediation_session_url, ?),
                        issue_number = COALESCE(issue_number, ?),
                        issue_url = COALESCE(issue_url, ?),
                        issue_created_at = COALESCE(issue_created_at, ?),
                        pull_request_number = COALESCE(pull_request_number, ?),
                        pull_request_url = COALESCE(pull_request_url, ?),
                        pull_request_created_at = COALESCE(pull_request_created_at, ?)
                    WHERE id = ?
                    """,
                    (
                        duplicate.get("triage_session_id"),
                        duplicate.get("triage_session_url"),
                        duplicate.get("remediation_session_id"),
                        duplicate.get("remediation_session_url"),
                        duplicate.get("issue_number"),
                        duplicate.get("issue_url"),
                        duplicate.get("issue_created_at"),
                        duplicate.get("pull_request_number"),
                        duplicate.get("pull_request_url"),
                        duplicate.get("pull_request_created_at"),
                        legacy["id"],
                    ),
                )
                connection.execute(
                    "DELETE FROM workflow_runs WHERE id = ?", (duplicate["id"],)
                )
            connection.execute(
                "UPDATE workflow_runs SET repository = ? WHERE id = ?",
                (self.default_repository, legacy["id"]),
            )

    @classmethod
    def _row(cls, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            raise KeyError("Workflow run was not found")
        value = dict(row)
        value["signals"] = cls._load(value.pop("signals_json"), [])
        value["evidence"] = cls._load(value.pop("evidence_json"), {})
        value["metadata"] = cls._load(value.pop("metadata_json"), {})
        value["raw_event"] = cls._load(value.pop("raw_event_json"), {})
        return value

    @staticmethod
    def _dump(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _load(value: str | None, fallback: Any) -> Any:
        if not value:
            return fallback
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback

    @staticmethod
    def _severity_from_labels(labels: list[str]) -> str:
        normalized = {label.lower() for label in labels}
        for severity in ("sev0", "sev1", "sev2", "sev3", "sev4"):
            if severity in normalized:
                return severity.upper().replace("SEV", "SEV-")
        return "SEV-3"

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _as_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        except ValueError:
            return None

    @staticmethod
    def _timestamp_to_iso(value: Any) -> str | None:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        return value if isinstance(value, str) else None
