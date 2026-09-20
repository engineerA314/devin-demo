from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from contextlib import asynccontextmanager, suppress
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import IncidentEventAccepted, IncidentEventEnvelope
from .operations import OperationsService
from .superset import SupersetGuestTokenClient

settings = get_settings()
operations = OperationsService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.devin_configured:
        raise RuntimeError("Set DEVIN_API_KEY and DEVIN_ORG_ID before starting the controller")
    await operations.devin.check_connection()
    task = asyncio.create_task(operations.run_reconciler())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/setup/status")
async def setup_status() -> dict[str, Any]:
    """Describe live-demo readiness without exposing credential values."""
    required_actions: list[str] = []
    if not settings.devin_api_key:
        required_actions.append("Set DEVIN_API_KEY in .env")
    if not settings.devin_org_id:
        required_actions.append("Set DEVIN_ORG_ID in .env")

    github_detail = (
        f"Authenticated reconciliation every {settings.effective_reconcile_seconds}s"
        if settings.github_token
        else (
            "Anonymous public-repository reconciliation every "
            f"{settings.effective_reconcile_seconds}s"
        )
    )
    intake_detail = (
        "Signed GitHub issue events with polling recovery"
        if settings.github_webhook_secret
        else "No webhook required; polling detects managed GitHub issues"
    )
    return {
        "liveDispatchReady": settings.devin_configured,
        "repository": settings.github_repository,
        "repositories": settings.allowed_repositories,
        "dispatchMode": "direct-session-api",
        "issueIntakeMode": settings.issue_intake_mode,
        "pollIntervalSeconds": settings.effective_reconcile_seconds,
        "checks": [
            {
                "key": "controller",
                "status": "ready",
                "label": "Controller",
                "detail": "Durable workflow store online",
                "required": True,
            },
            {
                "key": "devin",
                "status": "ready" if settings.devin_configured else "missing",
                "label": "Devin Cloud",
                "detail": (
                    "Direct session API configured"
                    if settings.devin_configured
                    else "DEVIN_API_KEY and DEVIN_ORG_ID are required"
                ),
                "required": True,
            },
            {
                "key": "github",
                "status": "ready" if settings.github_token else "optional",
                "label": "GitHub reconciliation",
                "detail": github_detail,
                "required": False,
            },
            {
                "key": "webhook",
                "status": "ready" if settings.github_webhook_secret else "optional",
                "label": "GitHub webhook",
                "detail": intake_detail,
                "required": False,
            },
        ],
        "requiredActions": required_actions,
    }


@app.get("/api/config")
async def embed_config() -> dict[str, str]:
    if not settings.embedded_superset_configured:
        return {"mode": "unconfigured"}
    return {
        "mode": "embedded",
        "dashboardId": settings.superset_dashboard_id,
        "supersetDomain": settings.superset_public_url.rstrip("/"),
    }


@app.post("/api/superset/guest-token")
async def guest_token() -> dict[str, str]:
    client = SupersetGuestTokenClient(settings)
    return {"token": await client.create_guest_token()}


@app.get("/api/operations/overview")
async def operations_overview() -> dict[str, Any]:
    overview = await operations.overview()
    overview["warnings"] = [warning for warning in overview["warnings"] if warning]
    return overview


@app.post("/api/incidents/demo")
async def trigger_demo_incident() -> dict[str, Any]:
    return await operations.trigger_demo_incident()


@app.post("/api/v1/incidents/events", response_model=IncidentEventAccepted)
@app.post("/api/v1/alerts", response_model=IncidentEventAccepted, deprecated=True)
async def ingest_incident_event(event: IncidentEventEnvelope) -> dict[str, Any]:
    if event.repository and event.repository not in settings.allowed_repositories:
        raise HTTPException(
            status_code=422,
            detail="repository hint is outside the configured allowlist",
        )
    payload = event.model_dump(mode="json")
    if len(json.dumps(payload, ensure_ascii=False).encode()) > 65_536:
        raise HTTPException(status_code=413, detail="incident event exceeds 64 KiB")
    return await operations.ingest_incident_event(payload)


@app.post("/api/v1/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(default=None),
    x_github_delivery: Optional[str] = Header(default=None),
    x_hub_signature_256: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    body = await request.body()
    if not settings.github_webhook_secret:
        raise HTTPException(status_code=503, detail="GitHub webhook secret is not configured")
    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(
        expected, x_hub_signature_256
    ):
        raise HTTPException(status_code=401, detail="invalid GitHub signature")
    if x_github_event != "issues":
        return {"accepted": False, "reason": "event ignored"}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="invalid JSON payload") from error
    if payload.get("action") not in {"opened", "reopened", "labeled"}:
        return {"accepted": False, "reason": "action ignored"}
    repository = (payload.get("repository") or {}).get("full_name")
    issue = payload.get("issue")
    if not repository or not issue:
        raise HTTPException(status_code=422, detail="missing repository or issue")
    if repository not in settings.allowed_repositories:
        return {"accepted": False, "reason": "repository is outside the allowlist"}
    labels = {
        str(label.get("name", "")).lower()
        for label in issue.get("labels", [])
        if isinstance(label, dict)
    }
    if settings.github_managed_label.lower() not in labels:
        return {"accepted": False, "reason": "issue is outside the admission policy"}
    result = await operations.ingest_github_issue(issue, repository)
    return {"accepted": True, "delivery": x_github_delivery, **result}
