from typing import Any

import httpx

from .config import Settings


class GitHubReadClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def list_incident_issues(self) -> list[dict[str, Any]]:
        issues = await self._list(
            "issues",
            {
                "state": "all",
                "per_page": 100,
                "sort": "created",
                "direction": "desc",
            },
        )
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
        return await self._list(
            "pulls",
            {"state": "all", "per_page": 100, "sort": "created", "direction": "desc"},
        )

    async def _list(
        self, resource: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"

        async with httpx.AsyncClient(
            base_url="https://api.github.com", headers=headers, timeout=20.0
        ) as client:
            items: list[dict[str, Any]] = []
            page = 1
            while True:
                response = await client.get(
                    f"/repos/{self.settings.github_repository}/{resource}",
                    params={**params, "page": page},
                )
                response.raise_for_status()
                batch = response.json()
                items.extend(batch)
                if len(batch) < int(params.get("per_page", 100)):
                    break
                page += 1
            if resource == "issues":
                return [item for item in items if "pull_request" not in item]
            return items
