"""Verify the external prerequisites for a live end-to-end demo."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import Settings


@dataclass
class Check:
    state: str
    name: str
    detail: str


def main() -> None:
    settings = Settings()
    checks: list[Check] = []
    failed = False

    if settings.devin_configured:
        try:
            response = httpx.get(
                (
                    f"{settings.devin_api_base_url.rstrip('/')}"
                    f"/v3/organizations/{settings.devin_org_id}/sessions"
                ),
                params={"first": 1},
                headers={
                    "Authorization": f"Bearer {settings.devin_api_key}",
                    "Accept": "application/json",
                },
                timeout=20.0,
            )
            response.raise_for_status()
            checks.append(Check("PASS", "Devin Cloud", "session API is reachable"))
        except httpx.HTTPError as error:
            failed = True
            checks.append(Check("FAIL", "Devin Cloud", _http_error(error)))
    else:
        failed = True
        checks.append(
            Check(
                "FAIL",
                "Devin Cloud",
                "set DEVIN_API_KEY and DEVIN_ORG_ID in .env",
            )
        )

    github_headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token:
        github_headers["Authorization"] = f"Bearer {settings.github_token}"
    try:
        response = httpx.get(
            f"https://api.github.com/repos/{settings.github_repository}",
            headers=github_headers,
            timeout=20.0,
        )
        response.raise_for_status()
        visibility = "private" if response.json().get("private") else "public"
        checks.append(
            Check(
                "PASS",
                "GitHub repository",
                f"{settings.github_repository} is reachable ({visibility})",
            )
        )
    except httpx.HTTPError as error:
        failed = True
        checks.append(Check("FAIL", "GitHub repository", _http_error(error)))

    if settings.github_token:
        checks.append(
            Check(
                "PASS",
                "Issue reconciliation",
                f"authenticated polling every {settings.effective_reconcile_seconds}s",
            )
        )
    else:
        checks.append(
            Check(
                "WARN",
                "Issue reconciliation",
                (
                    "anonymous polling works for a public fork every "
                    f"{settings.effective_reconcile_seconds}s; add GITHUB_TOKEN "
                    "for private forks and faster detection"
                ),
            )
        )

    checks.append(
        Check(
            "PASS" if settings.github_webhook_secret else "INFO",
            "GitHub event delivery",
            (
                "signed webhook enabled with polling recovery"
                if settings.github_webhook_secret
                else "polling mode; GITHUB_WEBHOOK_SECRET is not required"
            ),
        )
    )

    for check in checks:
        print(f"[{check.state:<4}] {check.name}: {check.detail}")
    if failed:
        raise SystemExit(1)
    print("\nLive alert dispatch is ready. Open http://localhost:3000/incident-simulator")


def _http_error(error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}; check credentials and repository access"
    return f"unreachable: {error.__class__.__name__}"


if __name__ == "__main__":
    main()
