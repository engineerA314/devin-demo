#!/usr/bin/env python3
"""Add the Superset fork to Devin's reusable Cloud environment."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx


BLUEPRINT = """initialize: |
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip uv
  .venv/bin/uv pip install --python .venv/bin/python -r requirements/base.txt
  .venv/bin/uv pip install --python .venv/bin/python pytest==7.4.4 pytest-asyncio==0.23.8 pytest-mock==3.10.0 freezegun==1.5.1 flask-testing==0.8.1 parameterized==0.9.0 ruff
  cd superset-embedded-sdk
  npm ci

maintenance: |
  test -x .venv/bin/pytest
  .venv/bin/python -c "import superset, pytest, pytest_mock"
  test -d superset-embedded-sdk/node_modules

knowledge:
  - name: Superset backend environment
    contents: Source .venv/bin/activate before running Python commands. The editable Superset base requirements and focused test dependencies are preinstalled, including pytest.
  - name: Superset backend focused tests
    contents: source .venv/bin/activate && pytest tests/unit_tests/common/test_query_context_processor.py
  - name: Embedded SDK unit tests
    contents: cd superset-embedded-sdk && npm test
  - name: Embedded SDK typecheck and build
    contents: cd superset-embedded-sdk && npm run build
  - name: Incident investigation scope
    contents: Select focused tests for the suspected component. Reproduce the failure by executing a test or deterministic script before reporting a code defect; source inspection alone is insufficient.
"""


def main() -> None:
    env = os.environ
    org_id = env.get("DEVIN_ORG_ID", "")
    api_key = env.get("DEVIN_API_KEY", "")
    repository = env.get("GITHUB_REPOSITORY", "engineerA314/superset")
    if not org_id or not api_key:
        raise SystemExit("DEVIN_ORG_ID and DEVIN_API_KEY must be set in .env")

    client = httpx.Client(
        base_url="https://api.devin.ai",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        timeout=60.0,
    )
    base = f"/v3beta1/organizations/{org_id}/snapshot-setup"
    blueprints = client.get(f"{base}/blueprints")
    blueprints.raise_for_status()
    blueprint_items = blueprints.json().get("data", blueprints.json().get("items", []))
    existing = next(
        (
            item
            for item in blueprint_items
            if item.get("repo_name") == repository
        ),
        None,
    )
    if existing:
        print(f"Using existing environment blueprint for {repository}")
        blueprint_id = existing["blueprint_id"]
        update = client.patch(
            f"{base}/blueprints/{blueprint_id}", json={"contents": BLUEPRINT}
        )
        update.raise_for_status()
        print("Updated the Superset full-stack environment blueprint")
    else:
        response = client.post(
            f"{base}/blueprints",
            json={"repo_name": repository, "contents": BLUEPRINT},
        )
        if response.status_code == 409:
            # The beta endpoint can persist the blueprint and still return a
            # conflict when repository defaults are created concurrently.
            refreshed = client.get(f"{base}/blueprints")
            refreshed.raise_for_status()
            refreshed_items = refreshed.json().get(
                "data", refreshed.json().get("items", [])
            )
            existing = next(
                (
                    item
                    for item in refreshed_items
                    if item.get("repo_name") == repository
                ),
                None,
            )
            if not existing:
                raise RuntimeError(
                    "Devin reported a blueprint conflict, but the repository "
                    "blueprint could not be recovered"
                )
            update = client.patch(
                f"{base}/blueprints/{existing['blueprint_id']}",
                json={"contents": BLUEPRINT},
            )
            update.raise_for_status()
            print(f"Recovered and updated environment blueprint for {repository}")
        elif response.is_error:
            raise RuntimeError(
                f"Unable to create environment blueprint: "
                f"HTTP {response.status_code} {response.text}"
            )
        else:
            existing = response.json()
            print(f"Created environment blueprint for {repository}")

    build = client.post(f"{base}/builds", json={})
    if build.status_code == 409:
        print("An environment build is already running")
        return
    build.raise_for_status()
    build_data: dict[str, Any] = build.json()
    build_id = build_data.get("build_id")
    if not build_id:
        raise RuntimeError("Build response did not include build_id")
    print(f"Started environment build {build_id}")

    for _ in range(60):
        status_response = client.get(f"{base}/builds/{build_id}")
        status_response.raise_for_status()
        status = status_response.json().get("status")
        print(f"Environment build: {status}")
        if status in {"succeeded", "failed", "cancelled"}:
            if status != "succeeded":
                raise RuntimeError(f"Environment build finished with status {status}")
            return
        time.sleep(10)
    raise RuntimeError("Environment build did not finish within 10 minutes")


if __name__ == "__main__":
    main()
