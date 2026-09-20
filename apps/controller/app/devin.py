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

    async def list_sessions(self, first: int = 50) -> list[dict[str, Any]]:
        if not self.settings.devin_configured:
            return []
        data = await self._get(
            f"/v3/organizations/{self.settings.devin_org_id}/sessions",
            params={"first": first},
        )
        return data.get("items", [])

    async def list_automations(self) -> list[dict[str, Any]]:
        if not self.settings.devin_configured:
            return []
        data = await self._get(
            f"/v3/organizations/{self.settings.devin_org_id}/automations",
            params={"first": 50},
        )
        return data.get("items", [])

    async def trigger_triage(self, payload: dict[str, Any]) -> None:
        if not self.settings.triage_webhook_configured:
            raise RuntimeError(
                "The native Devin triage automation has not been provisioned yet."
            )
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.settings.devin_triage_webhook_url,
                headers={
                    "X-Webhook-Secret": self.settings.devin_triage_webhook_secret,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()

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
