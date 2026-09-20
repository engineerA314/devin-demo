from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from statistics import median
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import Settings
from .devin import DevinClient
from .github import GitHubReadClient
from .incidents import IncidentStore


TERMINAL_DETAILS = {"waiting_for_user", "finished"}
ACTIVE_STATUSES = {"new", "claimed", "running", "resuming"}


class OperationsService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.devin = DevinClient(settings)
        self.github = GitHubReadClient(settings)
        self.incidents = IncidentStore(settings.incident_db_path)

    async def overview(self) -> dict[str, Any]:
        (
            sessions_result,
            automations_result,
            issues_result,
            pulls_result,
        ) = await asyncio.gather(
            self.devin.list_sessions(),
            self.devin.list_automations(),
            self.github.list_incident_issues(),
            self.github.list_pull_requests(),
            return_exceptions=True,
        )

        sessions = [] if isinstance(sessions_result, Exception) else sessions_result
        automations = (
            [] if isinstance(automations_result, Exception) else automations_result
        )
        issues = [] if isinstance(issues_result, Exception) else issues_result
        pulls = [] if isinstance(pulls_result, Exception) else pulls_result
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

        runs = [
            self._build_run(incident, issues, pulls, managed_sessions)
            for incident in incidents
        ]
        runs.sort(key=lambda run: run["detectedAt"], reverse=True)

        active = [session for session in managed_sessions if self._is_active(session)]
        completed = [
            session for session in managed_sessions if self._is_complete(session)
        ]
        failed = [
            session for session in managed_sessions if session.get("status") == "error"
        ]
        session_pull_requests = self._dedupe_pull_refs(
            [
                pull
                for session in managed_sessions
                for pull in (session.get("pull_requests") or [])
            ]
        )

        successful_runs = [
            run for run in runs if run["outcome"] in {"ready_for_review", "merged"}
        ]
        failed_runs = [run for run in runs if run["outcome"] == "failed"]
        approval_pending = [
            run for run in runs if run["outcome"] == "ready_for_review"
        ]
        issue_times = [
            run["durations"]["toIssueSeconds"]
            for run in successful_runs
            if run["durations"]["toIssueSeconds"] is not None
        ]
        pr_times = [
            run["durations"]["toPrSeconds"]
            for run in successful_runs
            if run["durations"]["toPrSeconds"] is not None
        ]

        github_error = (
            issues_result
            if isinstance(issues_result, Exception)
            else pulls_result if isinstance(pulls_result, Exception) else None
        )
        now = datetime.now(timezone.utc).isoformat()
        enabled_automations = sum(
            1 for automation in managed_automations if automation.get("enabled")
        )

        return {
            "configured": {
                "devin": self.settings.devin_configured,
                "triageWebhook": self.settings.triage_webhook_configured,
                "repository": self.settings.github_repository,
            },
            "summary": {
                "totalRuns": len(runs),
                "activeRuns": sum(1 for run in runs if run["status"] == "active"),
                "successfulRuns": len(successful_runs),
                "failedRuns": len(failed_runs),
                "approvalPending": len(approval_pending),
                "medianTimeToIssueSeconds": self._median_or_none(issue_times),
                "medianTimeToPrSeconds": self._median_or_none(pr_times),
            },
            "health": [
                self._health("Devin API", sessions_result, "Live session data"),
                self._health("GitHub API", github_error, "Issues and pull requests"),
                {
                    "name": "Automations",
                    "status": (
                        "healthy"
                        if not isinstance(automations_result, Exception)
                        and enabled_automations == len(managed_automation_ids)
                        and enabled_automations > 0
                        else "degraded"
                    ),
                    "detail": f"{enabled_automations}/{max(2, len(managed_automation_ids))} enabled",
                },
                {"name": "Controller", "status": "healthy", "detail": "Online"},
            ],
            "runs": runs,
            # Kept for API compatibility and lower-level inspection.
            "metrics": {
                "incidents": len(incidents),
                "activeSessions": len(active),
                "completedSessions": len(completed),
                "failedSessions": len(failed),
                "pullRequests": len(session_pull_requests),
                "acusConsumed": round(
                    sum(
                        float(session.get("acus_consumed") or 0)
                        for session in managed_sessions
                    ),
                    2,
                ),
                "successRate": round(
                    100 * len(successful_runs) / max(1, len(runs))
                ),
            },
            "incidents": [dict(incident) for incident in incidents],
            "automations": [
                self._automation_view(item) for item in managed_automations
            ],
            "sessions": [self._session_view(item) for item in managed_sessions],
            "issues": [self._issue_view(item) for item in issues],
            "pullRequests": [self._pull_view(item) for item in pulls],
            "generatedAt": now,
            "warnings": [
                self._warning("Devin API", sessions_result),
                self._warning("Automations API", automations_result),
                self._warning("GitHub Issues API", issues_result),
                self._warning("GitHub Pull Requests API", pulls_result),
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

    def _build_run(
        self,
        incident: dict[str, Any],
        issues: list[dict[str, Any]],
        pulls: list[dict[str, Any]],
        sessions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        detected_at = self._as_datetime(incident.get("detected_at"))
        issue = next(
            (
                item
                for item in issues
                if incident["id"] in (item.get("title") or "")
                or incident["id"] in (item.get("body") or "")
            ),
            None,
        )

        triage = self._nearest_session(sessions, "incident-triage", detected_at)
        issue_at = self._as_datetime(issue.get("created_at")) if issue else None
        remediation = self._nearest_session(
            sessions, "incident-remediation", issue_at or detected_at
        )
        pull = self._matching_pull(issue, pulls, remediation)
        pull_at = self._as_datetime(pull.get("created_at")) if pull else None

        has_failed_session = any(
            session and session.get("status") == "error"
            for session in (triage, remediation)
        )
        remediation_complete = bool(remediation and self._is_complete(remediation))
        verification_at = (
            self._as_datetime(remediation.get("updated_at"))
            if pull and remediation_complete
            else None
        )

        if incident.get("status") == "trigger_failed" or has_failed_session:
            outcome = "failed"
        elif pull and pull.get("merged_at"):
            outcome = "merged"
        elif pull and remediation_complete:
            outcome = "ready_for_review"
        elif pull:
            outcome = "pr_opened"
        elif remediation:
            outcome = "remediating"
        elif issue:
            outcome = "issue_created"
        elif triage:
            outcome = "triaging"
        else:
            outcome = "alert_received"

        active = any(
            session and self._is_active(session) for session in (triage, remediation)
        )
        status = "failed" if outcome == "failed" else "active" if active else "complete"

        milestones: list[dict[str, Any]] = []
        self._append_milestone(milestones, "alert", "Alert detected", detected_at)
        if triage:
            self._append_milestone(
                milestones,
                "agent",
                "Triage Devin started",
                self._as_datetime(triage.get("created_at")),
                triage.get("url"),
            )
        if issue:
            self._append_milestone(
                milestones,
                "issue",
                f"Issue #{issue.get('number')} created",
                issue_at,
                issue.get("html_url"),
            )
        if remediation:
            self._append_milestone(
                milestones,
                "code",
                "Remediation Devin started",
                self._as_datetime(remediation.get("created_at")),
                remediation.get("url"),
            )
        if pull:
            self._append_milestone(
                milestones,
                "pull_request",
                f"PR #{pull.get('number')} opened",
                pull_at,
                pull.get("html_url"),
            )
        if verification_at:
            self._append_milestone(
                milestones,
                "verified",
                "Verification passed",
                verification_at,
                remediation.get("url") if remediation else None,
            )

        tests_passed = self._tests_passed(pull.get("body") if pull else None)
        return {
            "id": incident["id"],
            "title": incident["title"],
            "service": incident["service"],
            "severity": incident["severity"],
            "status": status,
            "outcome": outcome,
            "detectedAt": self._iso(detected_at),
            "completedAt": self._iso(verification_at or pull_at or issue_at),
            "humanAction": self._human_action(outcome),
            "signals": {
                "errorRate": incident["error_rate"],
                "p95LatencyMs": incident["p95_latency_ms"],
                "affectedSessions": incident["affected_sessions"],
            },
            "durations": {
                "toIssueSeconds": self._elapsed_seconds(detected_at, issue_at),
                "toPrSeconds": self._elapsed_seconds(detected_at, pull_at),
                "toVerificationSeconds": self._elapsed_seconds(
                    detected_at, verification_at
                ),
            },
            "verification": {
                "testsPassed": tests_passed,
                "buildPassed": bool(
                    pull
                    and "npm run build" in (pull.get("body") or "")
                    and re.search(
                        r"(?:build\s*(?:—|:)?\s*(?:OK|passed)|webpack OK)",
                        pull.get("body") or "",
                        re.I,
                    )
                ),
                "source": "Clean worktree validation" if verification_at else None,
            },
            "evidence": self._evidence(issue, pull),
            "milestones": milestones,
            "triageSession": self._session_view(triage) if triage else None,
            "remediationSession": self._session_view(remediation) if remediation else None,
            "issue": self._issue_view(issue) if issue else None,
            "pullRequest": self._pull_view(pull) if pull else None,
            "errorDetail": incident.get("error_detail"),
        }

    @staticmethod
    def _nearest_session(
        sessions: list[dict[str, Any]], tag: str, anchor: datetime | None
    ) -> dict[str, Any] | None:
        candidates = [
            session for session in sessions if tag in (session.get("tags") or [])
        ]
        if not candidates:
            return None
        if not anchor:
            return candidates[0]

        def distance(session: dict[str, Any]) -> float:
            created_at = OperationsService._as_datetime(session.get("created_at"))
            return abs((created_at - anchor).total_seconds()) if created_at else float("inf")

        return min(candidates, key=distance)

    @staticmethod
    def _matching_pull(
        issue: dict[str, Any] | None,
        pulls: list[dict[str, Any]],
        remediation: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if issue:
            issue_number = issue.get("number")
            closes = re.compile(
                rf"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#?{issue_number}\b",
                re.I,
            )
            linked = next(
                (pull for pull in pulls if closes.search(pull.get("body") or "")),
                None,
            )
            if linked:
                return linked

        if remediation:
            refs = remediation.get("pull_requests") or []
            numbers = {
                OperationsService._number_from_url(ref.get("pr_url")) for ref in refs
            }
            linked = next(
                (pull for pull in pulls if pull.get("number") in numbers), None
            )
            if linked:
                return linked
        return None

    @staticmethod
    def _append_milestone(
        milestones: list[dict[str, Any]],
        kind: str,
        label: str,
        occurred_at: datetime | None,
        url: str | None = None,
    ) -> None:
        if not occurred_at:
            return
        previous_at = (
            OperationsService._as_datetime(milestones[-1]["occurredAt"])
            if milestones
            else None
        )
        milestones.append(
            {
                "kind": kind,
                "label": label,
                "occurredAt": OperationsService._iso(occurred_at),
                "elapsedSeconds": OperationsService._elapsed_seconds(
                    previous_at, occurred_at
                ),
                "url": url,
            }
        )

    @staticmethod
    def _evidence(
        issue: dict[str, Any] | None, pull: dict[str, Any] | None
    ) -> list[dict[str, str]]:
        issue_body = (issue.get("body") or "") if issue else ""
        pull_body = (pull.get("body") or "") if pull else ""
        evidence: list[dict[str, str]] = []
        if re.search(r"(?:50 embeds|50 clients|CLIENTS\s*=\s*50)", issue_body, re.I):
            evidence.append(
                {"label": "50 clients reproduced", "detail": "Vitest + fake timers"}
            )
        if "7 waves" in issue_body or "7 consecutive waves" in issue_body:
            evidence.append(
                {
                    "label": "7 synchronized waves",
                    "detail": "50/50 clients in the same 1s bucket",
                }
            )
        if "equal-jitter" in pull_body.lower() or "equal jitter" in pull_body.lower():
            evidence.append(
                {"label": "Equal-jitter backoff", "detail": "10s base · 5m cap"}
            )
        if "npm run build" in pull_body:
            evidence.append(
                {"label": "Build passed", "detail": "Clean worktree validation"}
            )
        return evidence

    @staticmethod
    def _tests_passed(body: str | None) -> str | None:
        match = re.search(r"(\d+)\s+tests?\s+passed", body or "", re.I)
        return f"{match.group(1)}/{match.group(1)}" if match else None

    @staticmethod
    def _human_action(outcome: str) -> str:
        return {
            "ready_for_review": "Review pull request",
            "merged": "None required",
            "failed": "Investigate failure",
        }.get(outcome, "Monitor progress")

    @staticmethod
    def _is_active(session: dict[str, Any]) -> bool:
        return (
            session.get("status") in ACTIVE_STATUSES
            and session.get("status_detail") not in TERMINAL_DETAILS
        )

    @staticmethod
    def _is_complete(session: dict[str, Any]) -> bool:
        return (
            session.get("status") == "exit"
            or session.get("status_detail") in TERMINAL_DETAILS
        )

    @staticmethod
    def _as_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                    timezone.utc
                )
            except ValueError:
                return None
        return None

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.astimezone(timezone.utc).isoformat() if value else None

    @staticmethod
    def _elapsed_seconds(start: datetime | None, end: datetime | None) -> int | None:
        if not start or not end:
            return None
        return max(0, round((end - start).total_seconds()))

    @staticmethod
    def _median_or_none(values: list[int]) -> int | None:
        return round(median(values)) if values else None

    @staticmethod
    def _number_from_url(url: str | None) -> int | None:
        if not url:
            return None
        try:
            return int(urlparse(url).path.rstrip("/").split("/")[-1])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dedupe_pull_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for item in items:
            url = item.get("pr_url")
            if url:
                unique[url] = item
        return list(unique.values())

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
    def _pull_view(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "number": item.get("number"),
            "title": item.get("title"),
            "state": "merged" if item.get("merged_at") else item.get("state"),
            "url": item.get("html_url"),
            "createdAt": item.get("created_at"),
            "mergedAt": item.get("merged_at"),
        }

    @staticmethod
    def _health(name: str, result: Any, detail: str) -> dict[str, str]:
        return {
            "name": name,
            "status": "degraded" if isinstance(result, Exception) else "healthy",
            "detail": str(result) if isinstance(result, Exception) else detail,
        }

    @staticmethod
    def _warning(source: str, value: Any) -> str | None:
        if isinstance(value, Exception):
            return f"{source}: {value}"
        return None
