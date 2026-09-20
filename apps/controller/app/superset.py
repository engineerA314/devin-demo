from typing import Any

import httpx
from fastapi import HTTPException

from .config import Settings


class SupersetGuestTokenClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def create_guest_token(self) -> str:
        if not self.settings.embedded_superset_configured:
            raise HTTPException(
                status_code=503,
                detail="Superset embedding is not configured. Set the SUPERSET_* values in .env.",
            )

        base_url = self.settings.superset_internal_url.rstrip("/")
        timeout = httpx.Timeout(15.0)

        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
                access_token = await self._login(client)
                csrf_token = await self._csrf_token(client, access_token)
                response = await client.post(
                    "/api/v1/security/guest_token/",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "X-CSRFToken": csrf_token,
                    },
                    json={
                        "resources": [
                            {
                                "type": "dashboard",
                                "id": self.settings.superset_dashboard_id,
                            }
                        ],
                        "rls": [],
                        "user": {
                            "username": "embedded-demo-user",
                            "first_name": "Acme",
                            "last_name": "Viewer",
                        },
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as error:
            detail = self._error_detail(error.response)
            raise HTTPException(
                status_code=502,
                detail=f"Superset rejected the guest token request: {detail}",
            ) from error
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Unable to reach Superset: {error}",
            ) from error

        token = response.json().get("token")
        if not token:
            raise HTTPException(
                status_code=502,
                detail="Superset returned a guest token response without a token.",
            )
        return str(token)

    async def _login(self, client: httpx.AsyncClient) -> str:
        response = await client.post(
            "/api/v1/security/login",
            json={
                "username": self.settings.superset_username,
                "password": self.settings.superset_password,
                "provider": "db",
                "refresh": True,
            },
        )
        response.raise_for_status()
        access_token = response.json().get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=502,
                detail="Superset login response did not contain an access token.",
            )
        return str(access_token)

    async def _csrf_token(
        self, client: httpx.AsyncClient, access_token: str
    ) -> str:
        response = await client.get(
            "/api/v1/security/csrf_token/",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        csrf_token = response.json().get("result")
        if not csrf_token:
            raise HTTPException(
                status_code=502,
                detail="Superset CSRF response did not contain a token.",
            )
        return str(csrf_token)

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            payload: Any = response.json()
        except ValueError:
            return response.text[:300] or f"HTTP {response.status_code}"
        if isinstance(payload, dict):
            return str(payload.get("message") or payload.get("detail") or payload)
        return str(payload)
