from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class IncidentStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_demo_incident(self) -> dict[str, Any]:
        incident_id = f"INC-{uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        incident = {
            "id": incident_id,
            "title": "Embedded analytics authentication recovery degraded",
            "service": "superset-embedded",
            "severity": "SEV-2",
            "status": "triggering",
            "detected_at": now,
            "updated_at": now,
            "error_rate": 18.7,
            "p95_latency_ms": 4280,
            "affected_sessions": 1264,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO incidents (
                    id, title, service, severity, status, detected_at, updated_at,
                    error_rate, p95_latency_ms, affected_sessions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident["id"],
                    incident["title"],
                    incident["service"],
                    incident["severity"],
                    incident["status"],
                    incident["detected_at"],
                    incident["updated_at"],
                    incident["error_rate"],
                    incident["p95_latency_ms"],
                    incident["affected_sessions"],
                ),
            )
        return incident

    def mark_triggered(self, incident_id: str) -> None:
        self._update_status(incident_id, "triage_queued")

    def mark_failed(self, incident_id: str, detail: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE incidents SET status = ?, error_detail = ?, updated_at = ? WHERE id = ?",
                ("trigger_failed", detail[:1000], now, incident_id),
            )

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM incidents ORDER BY detected_at DESC LIMIT 30"
            ).fetchall()
        return [dict(row) for row in rows]

    def _update_status(self, incident_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, incident_id),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    service TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_rate REAL NOT NULL,
                    p95_latency_ms INTEGER NOT NULL,
                    affected_sessions INTEGER NOT NULL,
                    error_detail TEXT
                )
                """
            )
