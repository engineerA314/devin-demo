from __future__ import annotations

from typing import Any

import httpx

from .config import Settings


class DevinClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.devin_api_key}",
            "Accept": "application/json",
        }

    async def check_connection(self) -> None:
        """Reject invalid credentials before the controller accepts incidents."""
        if not self.settings.devin_configured:
            raise RuntimeError("Devin API credentials are not configured.")
        await self._get(
            f"/v3/organizations/{self.settings.devin_org_id}/sessions",
            params={"first": 1},
        )

    async def list_sessions(self, first: int = 50) -> list[dict[str, Any]]:
        if not self.settings.devin_configured:
            return []
        items: list[dict[str, Any]] = []
        after: str | None = None
        while True:
            params: dict[str, Any] = {"first": min(first, 200)}
            if after:
                params["after"] = after
            data = await self._get(
                f"/v3/organizations/{self.settings.devin_org_id}/sessions",
                params=params,
            )
            items.extend(data.get("items", []))
            if not data.get("has_next_page") or not data.get("end_cursor"):
                return items
            after = data["end_cursor"]

    async def create_session(
        self,
        *,
        prompt: str,
        title: str,
        tags: list[str],
        max_acu_limit: int,
        structured_output_schema: dict[str, Any],
        session_links: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.devin_configured:
            raise RuntimeError("Devin API credentials are not configured.")
        payload: dict[str, Any] = {
            "prompt": prompt,
            "title": title,
            "tags": tags,
            "max_acu_limit": max_acu_limit,
            "bypass_approval": False,
            "resumable": True,
            "structured_output_required": True,
            "structured_output_schema": structured_output_schema,
        }
        if session_links:
            payload["session_links"] = session_links
        return await self._post(
            f"/v3/organizations/{self.settings.devin_org_id}/sessions",
            payload,
        )

    async def list_session_messages(self, session_id: str) -> list[dict[str, Any]]:
        if not self.settings.devin_configured:
            return []
        data = await self._get(
            f"/v3/organizations/{self.settings.devin_org_id}/sessions/"
            f"{session_id}/messages",
            params={"first": 200},
        )
        return data.get("items", [])

    async def send_message(self, session_id: str, message: str) -> dict[str, Any]:
        """Resume an existing remediation session with new CI evidence."""
        if not self.settings.devin_configured:
            raise RuntimeError("Devin API credentials are not configured.")
        return await self._post(
            f"/v3/organizations/{self.settings.devin_org_id}/sessions/"
            f"{session_id}/messages",
            {"message": message},
        )

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        base_url = self.settings.devin_api_base_url.rstrip("/")
        async with httpx.AsyncClient(
            base_url=base_url, headers=self.headers, timeout=30.0
        ) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        base_url = self.settings.devin_api_base_url.rstrip("/")
        async with httpx.AsyncClient(
            base_url=base_url, headers=self.headers, timeout=30.0
        ) as client:
            response = await client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
