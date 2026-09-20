from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import Settings
from app.github import GitHubReadClient
from app.incidents import IncidentStore
from app.operations import OperationsService
from app.observability import ObservabilitySnapshotStore


REPOSITORY = "engineerA314/superset"


def alert(
    event_id: str,
    title: str,
    *,
    incident_id: str | None = None,
    event_action: str = "trigger",
) -> dict:
    return {
        "event_id": event_id,
        "incident_id": incident_id or event_id,
        "event_action": event_action,
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
    def test_verified_pr_remains_complete_after_session_suspends(self) -> None:
        pull = {"number": 12}
        suspended = {
            "status": "suspended",
            "status_detail": "inactivity",
            "structured_output": {
                "pr_number": 12,
                "verification": "640 tests passed",
                "blocked_reason": None,
            },
        }

        self.assertTrue(OperationsService._remediation_complete(suspended, pull))
        self.assertFalse(
            OperationsService._remediation_complete(
                {**suspended, "structured_output": {}}, pull
            )
        )
        self.assertFalse(
            OperationsService._remediation_complete(suspended, {"number": 13})
        )

    def test_accepts_devin_present_tense_verification_report(self) -> None:
        body = (
            "## Verification\n"
            "`npm test` → 3 files, 20 tests pass; "
            "`npm run build` (tsc + babel + webpack) passes."
        )

        self.assertEqual("20/20", OperationsService._tests_passed(body))
        self.assertTrue(OperationsService._build_passed(body))

    def test_accepts_fraction_style_test_result_but_not_partial_pass(self) -> None:
        self.assertEqual(
            "22/22",
            OperationsService._tests_passed(
                "`npm test` → 22/22 passed; `npm run build` → success."
            ),
        )
        self.assertIsNone(OperationsService._tests_passed("21/22 tests passed"))

    def test_build_command_without_result_is_not_a_success_signal(self) -> None:
        body = "## Testing instructions\nRun `npm test && npm run build`."

        self.assertIsNone(OperationsService._tests_passed(body))
        self.assertFalse(OperationsService._build_passed(body))

    def test_accepts_python_verification_report(self) -> None:
        body = (
            "## Verification\n"
            "`pytest tests/unit_tests/common/test_query_context_processor.py` → "
            "77 passed.\n"
            "`pytest tests/unit_tests/common tests/unit_tests/charts` → "
            "641 passed, 2 xfailed.\n"
            "`ruff check` / `ruff format --check` clean on both changed files; "
            "`mypy` reports no errors in `query_context_processor.py`."
        )

        self.assertEqual("641/641", OperationsService._tests_passed(body))
        self.assertTrue(OperationsService._build_passed(body))

    def test_rejects_pytest_partial_failure(self) -> None:
        body = "`pytest` → 640 passed, 1 failed."

        self.assertIsNone(OperationsService._tests_passed(body))


class GitHubCheckClassificationTests(unittest.TestCase):
    def test_pending_checks_take_precedence_over_completed_failures(self) -> None:
        result = GitHubReadClient.classify_checks(
            "abc123",
            [
                {"name": "unit", "status": "completed", "conclusion": "failure"},
                {"name": "build", "status": "in_progress", "conclusion": None},
            ],
        )

        self.assertEqual("pending", result["status"])

    def test_completed_failure_is_reported_with_its_check_name(self) -> None:
        result = GitHubReadClient.classify_checks(
            "abc123",
            [{"name": "unit", "status": "completed", "conclusion": "failure"}],
        )

        self.assertEqual("failed", result["status"])
        self.assertEqual("unit", result["failedChecks"][0]["name"])


class ObservabilitySnapshotTests(unittest.TestCase):
    def test_cd1_snapshot_uses_configured_repository_names(self) -> None:
        store = ObservabilitySnapshotStore()
        snapshot = store.load(
            "CD-1",
            {
                "engineerA314/superset": "reviewer/superset",
                "engineerA314/devin-demo": "reviewer/devin-demo",
            },
        )

        changes = next(
            artifact["data"]
            for artifact in snapshot["artifacts"]
            if artifact["id"] == "change-events"
        )
        repositories = {item["repository"] for item in changes["most_recent"]}
        self.assertIn("reviewer/superset", repositories)
        self.assertIn("reviewer/devin-demo", repositories)
        self.assertNotIn("engineerA314/superset", repositories)
        self.assertIn("data-platform/warehouse-config", repositories)

    def test_cd1_snapshot_exposes_sources_without_a_diagnosis(self) -> None:
        store = ObservabilitySnapshotStore()

        snapshot = store.load("CD-1")
        public = store.public_view(snapshot)

        self.assertIsNotNone(snapshot)
        self.assertEqual("Datadog (simulated export)", public["provider"])
        self.assertEqual(6, len(public["artifacts"]))
        self.assertEqual("Browser RUM", public["artifacts"][0]["label"])
        self.assertNotIn("ensure_totals_available", str(snapshot))
        self.assertNotIn("cache bypass", str(snapshot).lower())

    def test_attribution_prompt_separates_alert_from_observability_views(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                _env_file=None,
                incident_db_path=str(Path(tmp) / "runs.db"),
                github_repository=REPOSITORY,
                product_repository="engineerA314/devin-demo",
            )
            service = OperationsService(settings)
            event = alert("delivery:cd1", "Embedded charts exceed the SLO")
            event["metadata"] = {
                "scenario_id": "CD-1",
                "observability_snapshot_id": "cd1-prod-window-01",
            }
            run, _ = service.incidents.create_alert(event)

            prompt = service._attribution_prompt(run)

        self.assertIn("<untrusted_incident_json>", prompt)
        self.assertIn("<untrusted_observability_snapshot>", prompt)
        self.assertIn('"id": "rum-events"', prompt)
        self.assertIn("Compare\n   affected and healthy requests", prompt)
        self.assertNotIn("ensure_totals_available", prompt)


class PortfolioIsolationTests(unittest.TestCase):
    def test_overview_excludes_historical_cloud_artifacts_after_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def exercise() -> dict:
                service = OperationsService(
                    Settings(
                        _env_file=None,
                        incident_db_path=str(Path(tmp) / "runs.db"),
                        github_repository=REPOSITORY,
                    )
                )

                class FakeDevin:
                    async def list_sessions(self, first: int = 100) -> list[dict]:
                        return [
                            {
                                "session_id": "historical-session",
                                "tags": ["incident-attribution", "workflow-INC-OLD"],
                                "status": "exit",
                            }
                        ]

                class FakeGitHub:
                    async def list_incident_issues(self) -> list[dict]:
                        return []

                    async def list_pull_requests(self) -> list[dict]:
                        return [
                            {
                                "number": 92,
                                "html_url": f"https://github.com/{REPOSITORY}/pull/92",
                                "state": "closed",
                            }
                        ]

                service.devin = FakeDevin()  # type: ignore[assignment]
                service.github = FakeGitHub()  # type: ignore[assignment]
                return await service.overview()

            overview = asyncio.run(exercise())

        self.assertEqual([], overview["runs"])
        self.assertEqual([], overview["sessions"])
        self.assertEqual([], overview["issues"])
        self.assertEqual([], overview["pullRequests"])
        self.assertEqual(0, overview["metrics"]["acusConsumed"])


class WorkflowStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "runs.db")
        self.store = IncidentStore(self.path, REPOSITORY)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_verification_time_survives_reconciliation(self) -> None:
        run, _ = self.store.create_alert(alert("delivery:verified", "Cached chart"))

        first = self.store.record_verification_if_absent(
            run["id"], "2026-09-20T13:06:03+00:00"
        )
        second = self.store.record_verification_if_absent(
            run["id"], "2026-09-20T13:40:00+00:00"
        )

        self.assertEqual(first, second)
        self.assertEqual(first, self.store.get(run["id"])["verification_completed_at"])

    def test_duplicate_alert_delivery_reuses_one_run(self) -> None:
        first, first_created = self.store.create_alert(alert("delivery:1", "First"))
        second, second_created = self.store.create_alert(alert("delivery:1", "First"))

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(1, len(self.store.list()))
        self.assertEqual(1, second["event_count"])
        self.assertEqual(1, second["duplicate_event_count"])

    def test_incident_lifecycle_events_fold_into_one_run(self) -> None:
        first, created, accepted = self.store.record_incident_event(
            alert("delivery:trigger", "Failure", incident_id="incident:42")
        )
        updated, updated_created, updated_accepted = self.store.record_incident_event(
            alert(
                "delivery:update",
                "Failure",
                incident_id="incident:42",
                event_action="update",
            )
        )
        resolved, resolved_created, resolved_accepted = self.store.record_incident_event(
            alert(
                "delivery:resolve",
                "Failure",
                incident_id="incident:42",
                event_action="resolve",
            )
        )

        self.assertTrue(created)
        self.assertTrue(accepted)
        self.assertFalse(updated_created)
        self.assertTrue(updated_accepted)
        self.assertFalse(resolved_created)
        self.assertTrue(resolved_accepted)
        self.assertEqual(first["id"], updated["id"])
        self.assertEqual(first["id"], resolved["id"])
        self.assertEqual(3, resolved["event_count"])
        self.assertEqual("resolved", resolved["upstream_status"])
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

    def test_ci_feedback_claim_is_idempotent_and_bounded(self) -> None:
        run, _ = self.store.upsert_issue(issue(31), REPOSITORY)
        self.store.bind_session(
            run["id"], "remediation", {"session_id": "devin-remediation"}
        )

        with ThreadPoolExecutor(max_workers=8) as pool:
            first_results = list(
                pool.map(
                    lambda _: self.store.claim_ci_feedback(
                        run["id"], "sha-one:failure", 2
                    ),
                    range(8),
                )
            )

        self.assertEqual(1, sum(first_results))
        self.assertTrue(
            self.store.claim_ci_feedback(run["id"], "sha-two:failure", 2)
        )
        self.assertFalse(
            self.store.claim_ci_feedback(run["id"], "sha-three:failure", 2)
        )
        self.assertEqual(2, self.store.get(run["id"])["ci_feedback_attempts"])


class ExplicitSessionCorrelationTests(unittest.TestCase):
    def test_attribution_policy_routes_only_allowlisted_evidence_backed_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def exercise() -> tuple[tuple, tuple, tuple]:
                settings = Settings(
                    _env_file=None,
                    incident_db_path=str(Path(tmp) / "runs.db"),
                    github_repository=REPOSITORY,
                    product_repository="engineerA314/devin-demo",
                    attribution_min_confidence=0.75,
                )
                service = OperationsService(settings)

                approved = service._evaluate_attribution(
                    {
                        "disposition": "code_change_required",
                        "confidence": 0.91,
                        "primary_repository": REPOSITORY,
                        "evidence": ["Failure reproduces in the embedded SDK."],
                        "reproduction": {
                            "status": "reproduced",
                            "method": "Focused unit test",
                            "command": "pytest tests/unit_tests/common/test_query_context_processor.py",
                            "result": "The test demonstrated a duplicate totals query.",
                        },
                    }
                )
                low_confidence = service._evaluate_attribution(
                    {
                        "disposition": "code_change_required",
                        "confidence": 0.61,
                        "primary_repository": REPOSITORY,
                        "evidence": ["Only a timing correlation is available."],
                        "reproduction": {
                            "status": "reproduced",
                            "method": "Focused unit test",
                            "command": "pytest focused_test.py",
                            "result": "Failure reproduced.",
                        },
                    }
                )
                outside_allowlist = service._evaluate_attribution(
                    {
                        "disposition": "code_change_required",
                        "confidence": 0.99,
                        "primary_repository": "unknown/production",
                        "evidence": ["Untrusted recommendation."],
                        "reproduction": {
                            "status": "reproduced",
                            "method": "Focused unit test",
                            "command": "pytest focused_test.py",
                            "result": "Failure reproduced.",
                        },
                    }
                )
                inspection_only = service._evaluate_attribution(
                    {
                        "disposition": "code_change_required",
                        "confidence": 0.99,
                        "primary_repository": REPOSITORY,
                        "evidence": ["The source looks incorrect."],
                        "reproduction": {
                            "status": "not_run",
                            "method": "Source inspection",
                            "command": None,
                            "result": "The environment did not have pytest.",
                        },
                    }
                )
                return approved, low_confidence, outside_allowlist, inspection_only

            approved, low_confidence, outside_allowlist, inspection_only = asyncio.run(exercise())

            self.assertEqual(("approved", REPOSITORY), approved[:2])
            self.assertEqual("human_review", low_confidence[0])
            self.assertEqual("human_review", outside_allowlist[0])
            self.assertEqual("human_review", inspection_only[0])
            self.assertIn("Executable reproduction", inspection_only[2])

    def test_approved_attribution_dispatches_separate_issue_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def exercise() -> tuple[dict, list[dict]]:
                settings = Settings(
                    _env_file=None,
                    incident_db_path=str(Path(tmp) / "runs.db"),
                    github_repository=REPOSITORY,
                    product_repository="engineerA314/devin-demo",
                    devin_api_key="test-key",
                    devin_org_id="test-org",
                )
                service = OperationsService(settings)
                run, _ = service.incidents.create_alert(
                    alert("delivery:attribution", "Attribute this incident")
                )
                service.incidents.record_attribution(
                    run["id"],
                    result={
                        "disposition": "code_change_required",
                        "confidence": 0.93,
                        "primary_component": "apache-superset",
                        "primary_repository": REPOSITORY,
                        "evidence": ["Reproduced in SDK code."],
                        "reproduction": {
                            "status": "reproduced",
                            "method": "Focused unit test",
                            "command": "npm test -- retry.test.ts",
                            "result": "Failure reproduced.",
                        },
                        "summary": "Superset owns the retry scheduler.",
                    },
                    policy_status="approved",
                    repository=REPOSITORY,
                    policy_reason="Policy approved.",
                )

                class FakeDevin:
                    def __init__(self) -> None:
                        self.calls: list[dict] = []

                    async def create_session(self, **kwargs: object) -> dict:
                        self.calls.append(kwargs)
                        return {
                            "session_id": "devin-issue-author",
                            "url": "https://devin/issue-author",
                        }

                fake = FakeDevin()
                service.devin = fake  # type: ignore[assignment]
                await service._dispatch_issue_authoring(run["id"])
                return service.incidents.get(run["id"]), fake.calls

            current, calls = asyncio.run(exercise())
            self.assertEqual("devin-issue-author", current["issue_session_id"])
            self.assertEqual(1, len(calls))
            self.assertIn(f"@{REPOSITORY}", calls[0]["prompt"])
            self.assertIn("incident-issue", calls[0]["tags"])

    def test_failed_ci_resumes_same_session_once_per_failure_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            async def exercise() -> tuple[int, int, list[str]]:
                settings = Settings(
                    _env_file=None,
                    incident_db_path=str(Path(tmp) / "runs.db"),
                    github_repository=REPOSITORY,
                    devin_api_key="test-key",
                    devin_org_id="test-org",
                    ci_feedback_max_attempts=2,
                )
                service = OperationsService(settings)
                run, _ = service.incidents.upsert_issue(issue(41), REPOSITORY)
                service.incidents.bind_session(
                    run["id"],
                    "remediation",
                    {"session_id": "devin-fix", "url": "https://devin/fix"},
                )
                pull = {
                    "number": 51,
                    "state": "open",
                    "html_url": f"https://github.com/{REPOSITORY}/pull/51",
                    "head": {"sha": "sha-one"},
                }
                service.incidents.bind_pull_request(run["id"], pull)

                class FakeGitHub:
                    async def get_commit_checks(
                        self, sha: str, _repository: str | None = None
                    ) -> dict:
                        return {
                            "headSha": sha,
                            "status": "failed",
                            "failedChecks": [
                                {
                                    "name": "unit tests",
                                    "status": "completed",
                                    "conclusion": "failure",
                                    "url": "https://github/check/1",
                                }
                            ],
                        }

                class FakeDevin:
                    def __init__(self) -> None:
                        self.messages: list[str] = []

                    async def send_message(self, _: str, message: str) -> dict:
                        self.messages.append(message)
                        return {}

                fake_devin = FakeDevin()
                service.github = FakeGitHub()  # type: ignore[assignment]
                service.devin = fake_devin  # type: ignore[assignment]

                await service._reconcile_ci([pull])
                await service._reconcile_ci([pull])
                pull["head"]["sha"] = "sha-two"
                await service._reconcile_ci([pull])
                pull["head"]["sha"] = "sha-three"
                await service._reconcile_ci([pull])
                current = service.incidents.get(run["id"])
                return (
                    len(fake_devin.messages),
                    current["ci_feedback_attempts"],
                    fake_devin.messages,
                )

            messages, attempts, prompts = asyncio.run(exercise())
            self.assertEqual(2, messages)
            self.assertEqual(2, attempts)
            self.assertTrue(all("same pull request" in prompt for prompt in prompts))

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

    def test_distinct_events_for_one_incident_call_devin_once(self) -> None:
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
                            "session_id": "devin-incident",
                            "url": "https://app.devin.ai/sessions/devin-incident",
                            "created_at": 1,
                        }

                fake = FakeDevin()
                service.devin = fake  # type: ignore[assignment]
                first = await service.ingest_incident_event(
                    alert("delivery:first", "Incident", incident_id="incident:one")
                )
                second = await service.ingest_incident_event(
                    alert(
                        "delivery:second",
                        "Incident",
                        incident_id="incident:one",
                        event_action="update",
                    )
                )
                return first, second, fake.calls

            first, second, calls = asyncio.run(exercise())
            self.assertEqual(first["id"], second["id"])
            self.assertTrue(first["incident_created"])
            self.assertFalse(second["incident_created"])
            self.assertFalse(second["event_duplicate"])
            self.assertEqual(2, second["event_count"])
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
