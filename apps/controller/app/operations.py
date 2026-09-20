from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import Settings
from .devin import DevinClient
from .github import GitHubReadClient
from .incidents import IncidentStore


class OperationsService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.devin = DevinClient(settings)
        self.github = GitHubReadClient(settings)
        self.incidents = IncidentStore(settings.incident_db_path)

    async def overview(self) -> dict[str, Any]:
        sessions_result, automations_result, issues_result = await asyncio.gather(
            self.devin.list_sessions(),
            self.devin.list_automations(),
            self.github.list_incident_issues(),
            return_exceptions=True,
        )

        sessions = [] if isinstance(sessions_result, Exception) else sessions_result
        automations = (
            [] if isinstance(automations_result, Exception) else automations_result
        )
        issues = [] if isinstance(issues_result, Exception) else issues_result
        incidents = self.incidents.list()

        managed_automation_ids = {
            value
            for value in (
                self.settings.devin_triage_automation_id,
                self.settings.devin_remediation_automation_id,
            )
            if value
        }
        managed_sessions = [
            session
            for session in sessions
            if session.get("automation_id") in managed_automation_ids
            or set(session.get("tags") or [])
            & {"incident-triage", "incident-remediation"}
        ]
        managed_automations = [
            automation
            for automation in automations
            if automation.get("automation_id") in managed_automation_ids
            or automation.get("id") in managed_automation_ids
            or automation.get("name")
            in {"Superset Incident Triage", "Superset Issue Remediation"}
        ]

        active_statuses = {"new", "claimed", "running", "resuming"}
        active = [
            s
            for s in managed_sessions
            if s.get("status") in active_statuses
            and s.get("status_detail") not in {"waiting_for_user", "finished"}
        ]
        completed = [
            s
            for s in managed_sessions
            if s.get("status") == "exit"
            or s.get("status_detail") in {"waiting_for_user", "finished"}
        ]
        failed = [s for s in managed_sessions if s.get("status") == "error"]
        pull_requests = [
            pr
            for session in managed_sessions
            for pr in (session.get("pull_requests") or [])
        ]

        incident_views = [dict(incident) for incident in incidents]
        remediation_active = any(
            "incident-remediation" in (session.get("tags") or [])
            and session in active
            for session in managed_sessions
        )
        for incident in incident_views:
            matching_issue = any(incident["id"] in (issue.get("title") or "") for issue in issues)
            if pull_requests:
                incident["status"] = "pr_opened"
            elif remediation_active:
                incident["status"] = "remediating"
            elif matching_issue:
                incident["status"] = "issue_created"

        return {
            "configured": {
                "devin": self.settings.devin_configured,
                "triageWebhook": self.settings.triage_webhook_configured,
                "repository": self.settings.github_repository,
            },
            "metrics": {
                "incidents": len(incidents),
                "activeSessions": len(active),
                "completedSessions": len(completed),
                "failedSessions": len(failed),
                "pullRequests": len(pull_requests),
                "acusConsumed": round(
                    sum(float(s.get("acus_consumed") or 0) for s in managed_sessions),
                    2,
                ),
                "successRate": round(
                    100 * len(completed) / max(1, len(completed) + len(failed))
                ),
            },
            "incidents": incident_views,
            "automations": [self._automation_view(item) for item in managed_automations],
            "sessions": [self._session_view(item) for item in managed_sessions],
            "issues": [self._issue_view(item) for item in issues],
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "warnings": [
                self._warning("Devin API", sessions_result),
                self._warning("Automations API", automations_result),
                self._warning("GitHub API", issues_result),
            ],
        }

    async def trigger_demo_incident(self) -> dict[str, Any]:
        incident = self.incidents.create_demo_incident()
        payload = {
            "event_type": "monitor.alert.triggered",
            "incident": incident,
            "monitor": {
                "name": "Embedded guest token refresh failure rate",
                "query": "service:superset-embedded route:/guest-token status:error",
                "threshold": {"error_rate_percent": 5, "window_minutes": 5},
            },
            "evidence": {
                "summary": (
                    "After a transient guest-token outage, recovering clients retry in "
                    "synchronized waves. Token endpoint latency and 5xx responses remain "
                    "elevated after the dependency recovers."
                ),
                "expected": (
                    "Clients should spread retries so recovery traffic remains below the "
                    "token service capacity."
                ),
                "repository": self.settings.github_repository,
            },
        }
        try:
            await self.devin.trigger_triage(payload)
            self.incidents.mark_triggered(incident["id"])
            incident["status"] = "triage_queued"
        except (RuntimeError, httpx.HTTPError) as error:
            self.incidents.mark_failed(incident["id"], str(error))
            incident["status"] = "trigger_failed"
            incident["error_detail"] = str(error)
        return incident

    @staticmethod
    def _automation_view(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("automation_id") or item.get("id"),
            "name": item.get("name"),
            "enabled": item.get("enabled"),
            "lastInvocation": item.get("last_invocation"),
        }

    @staticmethod
    def _session_view(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item.get("session_id"),
            "title": item.get("title"),
            "status": item.get("status"),
            "statusDetail": item.get("status_detail"),
            "url": item.get("url"),
            "tags": item.get("tags") or [],
            "acusConsumed": item.get("acus_consumed") or 0,
            "pullRequests": item.get("pull_requests") or [],
            "createdAt": item.get("created_at"),
            "updatedAt": item.get("updated_at"),
            "automationId": item.get("automation_id"),
        }

    @staticmethod
    def _issue_view(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "number": item.get("number"),
            "title": item.get("title"),
            "state": item.get("state"),
            "url": item.get("html_url"),
            "labels": [label.get("name") for label in item.get("labels", [])],
            "createdAt": item.get("created_at"),
        }

    @staticmethod
    def _warning(source: str, value: Any) -> str | None:
        if isinstance(value, Exception):
            return f"{source}: {value}"
        return None
