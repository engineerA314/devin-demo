#!/usr/bin/env python3
"""Provision the native Devin automations used by the demo.

The script is deliberately API driven so the setup itself is reproducible. It
captures the one-time webhook secret in the ignored root .env file without
printing it to the terminal.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
TRIAGE_NAME = "Superset Incident Triage"
REMEDIATION_NAME = "Superset Issue Remediation"


def read_env() -> dict[str, str]:
    values = dict(os.environ)
    if not ENV_FILE.exists():
        return values
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def update_env(updates: dict[str, str]) -> None:
    text = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    lines = text.splitlines()
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
                continue
        output.append(line)
    if output and output[-1] != "":
        output.append("")
    output.extend(f"{key}={value}" for key, value in remaining.items())
    ENV_FILE.write_text("\n".join(output).rstrip() + "\n")


class DevinAutomationProvisioner:
    def __init__(self, env: dict[str, str]) -> None:
        self.org_id = env.get("DEVIN_ORG_ID", "")
        self.api_key = env.get("DEVIN_API_KEY", "")
        self.repository = env.get("GITHUB_REPOSITORY", "engineerA314/superset")
        if not self.org_id or not self.api_key:
            raise SystemExit("DEVIN_ORG_ID and DEVIN_API_KEY must be set in .env")
        self.client = httpx.Client(
            base_url="https://api.devin.ai",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def provision(self) -> dict[str, str]:
        existing = {item["name"]: item for item in self._list_automations()}
        updates: dict[str, str] = {}

        triage = existing.get(TRIAGE_NAME)
        if triage is None:
            triage = self._create(self._triage_payload())
            webhook = next(
                trigger.get("webhook")
                for trigger in triage.get("triggers", [])
                if trigger.get("event_type") == "webhook:incoming"
            )
            if not webhook or not webhook.get("secret"):
                raise RuntimeError("Devin did not return the new webhook secret")
            updates["DEVIN_TRIAGE_WEBHOOK_URL"] = webhook["url"]
            updates["DEVIN_TRIAGE_WEBHOOK_SECRET"] = webhook["secret"]
            print(f"Created {TRIAGE_NAME}")
        else:
            print(f"Using existing {TRIAGE_NAME}")
        updates["DEVIN_TRIAGE_AUTOMATION_ID"] = self._id(triage)

        remediation = existing.get(REMEDIATION_NAME)
        if remediation is None:
            remediation = self._create(self._remediation_payload())
            print(f"Created {REMEDIATION_NAME}")
        else:
            print(f"Using existing {REMEDIATION_NAME}")
        updates["DEVIN_REMEDIATION_AUTOMATION_ID"] = self._id(remediation)

        update_env(updates)
        print("Saved automation identifiers and the webhook credential to .env")
        return updates

    def _list_automations(self) -> list[dict[str, Any]]:
        response = self.client.get(
            f"/v3/organizations/{self.org_id}/automations", params={"first": 100}
        )
        response.raise_for_status()
        return response.json().get("items", [])

    def _create(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(
            f"/v3/organizations/{self.org_id}/automations", json=payload
        )
        if response.is_error:
            raise RuntimeError(
                f"Unable to create {payload['name']}: "
                f"HTTP {response.status_code} {response.text}"
            )
        return response.json()

    def _triage_payload(self) -> dict[str, Any]:
        return {
            "name": TRIAGE_NAME,
            "enabled": True,
            "metadata": {"managed-by": "devin-demo", "stage": "triage"},
            "run_as": {"type": "organization"},
            "triggers": [
                {"event_type": "webhook:incoming", "conditions": None, "replies": []}
            ],
            "actions": [
                {
                    "type": "start_session",
                    "prompt": self._triage_prompt(),
                    "session": {
                        "tags": ["incident-triage", "superset"],
                        "bypass_approval": False,
                    },
                }
            ],
            "limits": {
                "max_acu_limit": 20,
                "invocations": {"max_per_window": 5, "window_seconds": 3600},
            },
            "concurrency": {"max_concurrent_runs": 2, "max_queue_depth": 10},
            "session_settings": {"devin_mode": "normal"},
        }

    def _remediation_payload(self) -> dict[str, Any]:
        conditions = {
            "any": [
                {
                    "all": [
                        {
                            "field": "repository.full_name",
                            "operator": "eq",
                            "value": self.repository,
                        },
                        {"field": "action", "operator": "eq", "value": "labeled"},
                        {
                            "field": "label.name",
                            "operator": "eq",
                            "value": "devin-ready",
                        },
                    ]
                }
            ]
        }
        return {
            "name": REMEDIATION_NAME,
            "enabled": True,
            "metadata": {"managed-by": "devin-demo", "stage": "remediation"},
            "run_as": {"type": "organization"},
            "triggers": [
                {
                    "event_type": "github:issues",
                    "conditions": conditions,
                    "replies": [{"type": "post_response"}],
                }
            ],
            "actions": [
                {
                    "type": "start_session",
                    "prompt": self._remediation_prompt(),
                    "session": {
                        "tags": ["incident-remediation", "superset"],
                        "bypass_approval": False,
                    },
                }
            ],
            "limits": {
                "max_acu_limit": 40,
                "invocations": {"max_per_window": 5, "window_seconds": 3600},
            },
            "concurrency": {"max_concurrent_runs": 3, "max_queue_depth": 10},
            "session_settings": {"devin_mode": "normal"},
        }

    def _triage_prompt(self) -> str:
        return f"""You are the first-stage production incident triage engineer for
an embedded Apache Superset deployment. Work in @{self.repository}. The triggering
monitor payload is appended to this prompt by Devin Automations.

Your goal is to turn the alert into a high-quality, reproducible engineering issue.

1. Read the alert payload, preserving its incident ID and measured evidence.
2. Inspect the current default branch. Reproduce or falsify the reported behavior
   with a focused automated test or deterministic script. Do not assume the alert's
   proposed root cause is correct.
3. If the problem is not caused by this repository, report why and stop without
   creating an issue.
4. If it is reproducible, create exactly one issue in {self.repository}. The issue
   must contain customer impact, observed and expected behavior, reproduction steps,
   evidence, likely code area, acceptance criteria, and the incident ID.
5. Apply labels `incident-autopilot`, `sev2`, and `devin-ready`. Confirm the issue URL
   in your final response.

This is a triage stage. Do not modify production code, push a branch, or open a PR.
Keep any local reproduction artifacts only as evidence for the issue body."""

    def _remediation_prompt(self) -> str:
        return f"""You are the remediation engineer for @{self.repository}. Devin
Automations appends the complete GitHub issue event to this prompt.

Treat the issue body as the handoff contract from incident triage:

1. Read the linked issue and independently reproduce the failure on the current
   default branch before changing code.
2. Find the root cause and implement the smallest production-quality fix.
3. Add a regression test that fails before the fix and passes afterward.
4. Run the narrow test, relevant lint/type checks, and any broader suite justified
   by the changed code. Record exact commands and results.
5. Create a pull request against {self.repository}'s default branch. Link it with
   `Closes #<issue-number>` and include root cause, fix, tests, rollout risk, and a
   reviewer checklist.
6. Post a concise final response to the issue with the PR URL and verification.

Do not merge the pull request. Human approval remains the production gate."""

    @staticmethod
    def _id(item: dict[str, Any]) -> str:
        value = item.get("automation_id") or item.get("id")
        if not value:
            raise RuntimeError("Automation response did not include an ID")
        return str(value)


if __name__ == "__main__":
    DevinAutomationProvisioner(read_env()).provision()
