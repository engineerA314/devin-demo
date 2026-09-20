from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import Settings
from app.incidents import IncidentStore
from app.operations import OperationsService


REPOSITORY = "engineerA314/superset"


def alert(event_id: str, title: str) -> dict:
    return {
        "event_id": event_id,
        "source": "test-monitor",
        "repository": REPOSITORY,
        "title": title,
        "service": "superset-test",
        "severity": "SEV-2",
        "signals": [{"key": "errors", "label": "Errors", "value": 12}],
    }


def issue(number: int, run_id: str | None = None) -> dict:
    marker = f"<!-- devin-autopilot-run:{run_id} -->" if run_id else ""
    return {
        "number": number,
        "title": f"Issue {number}",
        "body": marker,
        "state": "open",
        "html_url": f"https://github.com/{REPOSITORY}/issues/{number}",
        "created_at": f"2026-09-20T00:0{number}:00Z",
        "labels": [{"name": "autopilot-managed"}],
    }


class SetupModeTests(unittest.TestCase):
    def test_public_fork_without_secrets_uses_safe_polling(self) -> None:
        settings = Settings(_env_file=None, workflow_reconcile_seconds=20)

        self.assertEqual("polling", settings.issue_intake_mode)
        self.assertEqual(120, settings.effective_reconcile_seconds)

    def test_authenticated_webhook_mode_keeps_polling_as_recovery(self) -> None:
        settings = Settings(
            _env_file=None,
            github_token="read-token",
            github_webhook_secret="shared-secret",
            workflow_reconcile_seconds=20,
        )

        self.assertEqual(
            "signed-webhook-with-polling-recovery",
            settings.issue_intake_mode,
        )
        self.assertEqual(20, settings.effective_reconcile_seconds)


class VerificationParsingTests(unittest.TestCase):
    def test_accepts_devin_present_tense_verification_report(self) -> None:
        body = (
            "## Verification\n"
            "`npm test` → 3 files, 20 tests pass; "
            "`npm run build` (tsc + babel + webpack) passes."
        )

        self.assertEqual("20/20", OperationsService._tests_passed(body))
        self.assertTrue(OperationsService._build_passed(body))

    def test_build_command_without_result_is_not_a_success_signal(self) -> None:
        body = "## Testing instructions\nRun `npm test && npm run build`."

        self.assertIsNone(OperationsService._tests_passed(body))
        self.assertFalse(OperationsService._build_passed(body))


class WorkflowStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "runs.db")
        self.store = IncidentStore(self.path, REPOSITORY)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_duplicate_alert_delivery_reuses_one_run(self) -> None:
        first, first_created = self.store.create_alert(alert("delivery:1", "First"))
        second, second_created = self.store.create_alert(alert("delivery:1", "First"))

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(1, len(self.store.list()))

    def test_atomic_dispatch_claim_allows_one_winner(self) -> None:
        run, _ = self.store.create_alert(alert("delivery:claim", "Claim"))

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(
                    lambda _: self.store.claim_dispatch(run["id"], "triage"),
                    range(8),
                )
            )

        self.assertEqual(1, sum(results))

    def test_independent_issue_becomes_a_workflow_run(self) -> None:
        run, created = self.store.upsert_issue(issue(7), REPOSITORY)

        self.assertTrue(created)
        self.assertEqual("issue", run["source_type"])
        self.assertEqual(7, run["issue_number"])
        self.assertEqual("issue_created", run["state"])

    def test_legacy_alert_and_reconciled_issue_are_merged(self) -> None:
        legacy_path = str(Path(self.tmp.name) / "legacy.db")
        with sqlite3.connect(legacy_path) as connection:
            connection.execute(
                """
                CREATE TABLE incidents (
                    id TEXT PRIMARY KEY, title TEXT, service TEXT, severity TEXT,
                    status TEXT, detected_at TEXT, updated_at TEXT,
                    error_rate REAL, p95_latency_ms INTEGER,
                    affected_sessions INTEGER, error_detail TEXT
                )
                """
            )
            connection.execute(
                """
                INSERT INTO incidents VALUES (
                    'INC-LEGACY', 'Legacy', 'service', 'SEV-2', 'triage_queued',
                    '2026-09-20T00:00:00Z', '2026-09-20T00:00:00Z',
                    1.0, 100, 2, NULL
                )
                """
            )
        old_store = IncidentStore(legacy_path)
        old_store.upsert_issue(issue(9, "INC-LEGACY"), REPOSITORY, "INC-LEGACY")

        repaired = IncidentStore(legacy_path, REPOSITORY)

        self.assertEqual(1, len(repaired.list()))
        self.assertEqual(REPOSITORY, repaired.get("INC-LEGACY")["repository"])
        self.assertEqual(9, repaired.get("INC-LEGACY")["issue_number"])

    def test_two_runs_keep_sessions_issues_and_pull_requests_isolated(self) -> None:
        first, _ = self.store.create_alert(alert("delivery:a", "Alert A"))
        second, _ = self.store.create_alert(alert("delivery:b", "Alert B"))
        self.store.bind_session(first["id"], "triage", {"session_id": "devin-a"})
        self.store.bind_session(second["id"], "triage", {"session_id": "devin-b"})
        self.store.upsert_issue(issue(11, first["id"]), REPOSITORY, first["id"])
        self.store.upsert_issue(issue(12, second["id"]), REPOSITORY, second["id"])
        self.store.bind_pull_request(
            first["id"],
            {"number": 21, "html_url": f"https://github.com/{REPOSITORY}/pull/21"},
        )
        self.store.bind_pull_request(
            second["id"],
            {"number": 22, "html_url": f"https://github.com/{REPOSITORY}/pull/22"},
        )

        first_result = self.store.get(first["id"])
        second_result = self.store.get(second["id"])
        self.assertEqual(("devin-a", 11, 21), (
            first_result["triage_session_id"],
            first_result["issue_number"],
            first_result["pull_request_number"],
        ))
        self.assertEqual(("devin-b", 12, 22), (
            second_result["triage_session_id"],
            second_result["issue_number"],
            second_result["pull_request_number"],
        ))


class ExplicitSessionCorrelationTests(unittest.TestCase):
    def test_duplicate_ingest_calls_devin_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def exercise() -> tuple[dict, dict, int]:
                settings = Settings(
                    _env_file=None,
                    incident_db_path=str(Path(tmp) / "runs.db"),
                    github_repository=REPOSITORY,
                    devin_api_key="test-key",
                    devin_org_id="test-org",
                )
                service = OperationsService(settings)

                class FakeDevin:
                    def __init__(self) -> None:
                        self.calls = 0

                    async def create_session(self, **_: object) -> dict:
                        self.calls += 1
                        return {
                            "session_id": "devin-one",
                            "url": "https://app.devin.ai/sessions/devin-one",
                            "created_at": 1,
                        }

                fake = FakeDevin()
                service.devin = fake  # type: ignore[assignment]
                payload = alert("delivery:idempotent", "Idempotent")
                first = await service.ingest_alert(payload)
                second = await service.ingest_alert(payload)
                return first, second, fake.calls

            first, second, calls = asyncio.run(exercise())
            self.assertEqual(first["id"], second["id"])
            self.assertFalse(first["duplicate"])
            self.assertTrue(second["duplicate"])
            self.assertEqual(1, calls)

    def test_run_tags_bind_concurrent_sessions_without_time_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def exercise() -> tuple[str, str]:
                settings = Settings(
                    _env_file=None,
                    incident_db_path=str(Path(tmp) / "runs.db"),
                    github_repository=REPOSITORY,
                )
                service = OperationsService(settings)
                first, _ = service.incidents.create_alert(alert("delivery:x", "X"))
                second, _ = service.incidents.create_alert(alert("delivery:y", "Y"))
                sessions = [
                    {
                        "session_id": "devin-y",
                        "tags": ["incident-triage", service._run_tag(second["id"])],
                    },
                    {
                        "session_id": "devin-x",
                        "tags": ["incident-triage", service._run_tag(first["id"])],
                    },
                ]
                await service._bind_sessions(sessions)
                return (
                    service.incidents.get(first["id"])["triage_session_id"],
                    service.incidents.get(second["id"])["triage_session_id"],
                )

            first_session, second_session = asyncio.run(exercise())
            self.assertEqual("devin-x", first_session)
            self.assertEqual("devin-y", second_session)


if __name__ == "__main__":
    unittest.main()
