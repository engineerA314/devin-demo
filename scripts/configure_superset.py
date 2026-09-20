#!/usr/bin/env python3
"""Enable a local Superset dashboard for SDK embedding.

This script is intentionally separate from the demo controller. It is a one-time
bootstrap command for the local Apache Superset fork: authenticate as the local
admin, enable embedding for the example dashboard, and write the resulting
embedded dashboard UUID into devin-demo/.env.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx


DEFAULT_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure the World Bank example dashboard for embedding."
    )
    parser.add_argument("--base-url", default="http://localhost:9001")
    parser.add_argument("--dashboard", default="world_health")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument(
        "--allowed-origin",
        action="append",
        dest="allowed_origins",
        help="Allowed parent origin. Repeat to allow more than one origin.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".env",
    )
    parser.add_argument(
        "--internal-url",
        help="Controller-facing URL; defaults to --base-url for local development.",
    )
    return parser.parse_args()


def error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    return str(payload.get("message") or payload) if isinstance(payload, dict) else str(payload)


def require_ok(response: httpx.Response, action: str) -> None:
    if response.is_success:
        return
    raise RuntimeError(
        f"{action} failed with HTTP {response.status_code}: {error_detail(response)}"
    )


def set_env_values(path: Path, values: dict[str, str]) -> None:
    existing = path.read_text().splitlines() if path.exists() else []
    remaining = dict(values)
    output: list[str] = []

    for line in existing:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in remaining and not line.lstrip().startswith("#"):
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)

    if remaining and output and output[-1] != "":
        output.append("")
    output.extend(f"{key}={value}" for key, value in remaining.items())
    path.write_text("\n".join(output).rstrip() + "\n")


def configure(args: argparse.Namespace) -> str:
    base_url = args.base_url.rstrip("/")
    allowed_origins = args.allowed_origins or list(DEFAULT_ORIGINS)

    with httpx.Client(base_url=base_url, timeout=30.0, follow_redirects=True) as client:
        login = client.post(
            "/api/v1/security/login",
            json={
                "username": args.username,
                "password": args.password,
                "provider": "db",
                "refresh": True,
            },
        )
        require_ok(login, "Superset login")
        access_token = login.json().get("access_token")
        if not access_token:
            raise RuntimeError("Superset login response did not include an access token")

        auth_headers = {"Authorization": f"Bearer {access_token}"}
        csrf = client.get("/api/v1/security/csrf_token/", headers=auth_headers)
        require_ok(csrf, "CSRF token request")
        csrf_token = csrf.json().get("result")
        if not csrf_token:
            raise RuntimeError("Superset CSRF response did not include a token")

        embedded = client.post(
            f"/api/v1/dashboard/{args.dashboard}/embedded",
            headers={**auth_headers, "X-CSRFToken": str(csrf_token)},
            json={"allowed_domains": allowed_origins},
        )
        require_ok(embedded, f"Enabling embedding for {args.dashboard}")

    result = embedded.json().get("result", {})
    dashboard_uuid = result.get("uuid")
    if not dashboard_uuid:
        raise RuntimeError("Superset embed response did not include a dashboard UUID")

    set_env_values(
        args.env_file,
        {
            "VITE_API_BASE_URL": "http://localhost:8000",
            "CORS_ORIGINS": ",".join(DEFAULT_ORIGINS),
            "SUPERSET_INTERNAL_URL": (args.internal_url or base_url).rstrip("/"),
            "SUPERSET_PUBLIC_URL": base_url,
            "SUPERSET_DASHBOARD_ID": str(dashboard_uuid),
            "SUPERSET_USERNAME": args.username,
            "SUPERSET_PASSWORD": args.password,
        },
    )
    return str(dashboard_uuid)


def main() -> int:
    args = parse_args()
    try:
        dashboard_uuid = configure(args)
    except (httpx.HTTPError, OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Embedded dashboard UUID: {dashboard_uuid}")
    print(f"Updated environment file: {args.env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
