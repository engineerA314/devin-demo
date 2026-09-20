from typing import Any

import httpx

from .config import Settings


class GitHubReadClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def list_incident_issues(self) -> list[dict[str, Any]]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"

        async with httpx.AsyncClient(
            base_url="https://api.github.com", headers=headers, timeout=20.0
        ) as client:
            response = await client.get(
                f"/repos/{self.settings.github_repository}/issues",
                params={
                    "state": "all",
                    "labels": "incident-autopilot",
                    "per_page": 30,
                },
            )
            response.raise_for_status()
            return [item for item in response.json() if "pull_request" not in item]
