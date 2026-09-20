from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .config import Settings


class GitHubReadClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def list_incident_issues(self) -> list[dict[str, Any]]:
        batches = await asyncio.gather(
            *(
                self._list(
                    repository,
                    "issues",
                    {
                        "state": "open",
                        "per_page": 100,
                        "sort": "created",
                        "direction": "desc",
                    },
                )
                for repository in self.settings.allowed_repositories
            )
        )
        issues = [issue for batch in batches for issue in batch]
        managed_labels = {
            "incident-autopilot",
            "devin-ready",
            self.settings.github_managed_label.lower(),
        }
        return [
            issue
            for issue in issues
            if managed_labels
            & {
                str(label.get("name", "")).lower()
                for label in issue.get("labels", [])
            }
        ]

    async def list_pull_requests(self) -> list[dict[str, Any]]:
        batches = await asyncio.gather(
            *(
                self._list(
                    repository,
                    "pulls",
                    {
                        "state": "all",
                        "per_page": 100,
                        "sort": "created",
                        "direction": "desc",
                    },
                )
                for repository in self.settings.allowed_repositories
            )
        )
        return [pull for batch in batches for pull in batch]

    async def get_commit_checks(
        self, sha: str, repository: str | None = None
    ) -> dict[str, Any]:
        """Return one normalized CI verdict for a pull request head commit."""
        data = await self._get(
            repository or self.settings.github_repository,
            f"commits/{sha}/check-runs",
            {"per_page": 100},
        )
        return self.classify_checks(sha, data.get("check_runs") or [])

    @staticmethod
    def classify_checks(sha: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
        normalized = [
            {
                "name": str(check.get("name") or "Unnamed check"),
                "status": str(check.get("status") or "unknown"),
                "conclusion": check.get("conclusion"),
                "url": check.get("details_url") or check.get("html_url"),
                "completedAt": check.get("completed_at"),
            }
            for check in checks
        ]
        if not normalized:
            status = "not_configured"
        elif any(check["status"] != "completed" for check in normalized):
            status = "pending"
        elif any(
            check["conclusion"]
            in {
                "failure",
                "cancelled",
                "timed_out",
                "action_required",
                "startup_failure",
                "stale",
            }
            for check in normalized
        ):
            status = "failed"
        else:
            status = "passed"
        return {
            "headSha": sha,
            "status": status,
            "checks": normalized,
            "failedChecks": [
                check
                for check in normalized
                if check["conclusion"]
                in {
                    "failure",
                    "cancelled",
                    "timed_out",
                    "action_required",
                    "startup_failure",
                    "stale",
                }
            ],
        }

    async def _get(
        self, repository: str, resource: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        headers = self._headers()
        async with httpx.AsyncClient(
            base_url="https://api.github.com", headers=headers, timeout=20.0
        ) as client:
            response = await client.get(
                f"/repos/{repository}/{resource}", params=params
            )
            response.raise_for_status()
            return response.json()

    async def _list(
        self, repository: str, resource: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        headers = self._headers()

        async with httpx.AsyncClient(
            base_url="https://api.github.com", headers=headers, timeout=20.0
        ) as client:
            items: list[dict[str, Any]] = []
            page = 1
            while True:
                response = await client.get(
                    f"/repos/{repository}/{resource}",
                    params={**params, "page": page},
                )
                response.raise_for_status()
                batch = response.json()
                items.extend(batch)
                if len(batch) < int(params.get("per_page", 100)):
                    break
                page += 1
            if resource == "issues":
                items = [item for item in items if "pull_request" not in item]
            return [{**item, "_repository": repository} for item in items]

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"

        return headers
