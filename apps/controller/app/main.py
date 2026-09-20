from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .superset import SupersetGuestTokenClient

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")

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


@app.get("/api/config")
async def embed_config() -> dict[str, str]:
    if not settings.embedded_superset_configured:
        return {"mode": "preview"}
    return {
        "mode": "embedded",
        "dashboardId": settings.superset_dashboard_id,
        "supersetDomain": settings.superset_public_url.rstrip("/"),
    }


@app.post("/api/superset/guest-token")
async def guest_token() -> dict[str, str]:
    client = SupersetGuestTokenClient(settings)
    return {"token": await client.create_guest_token()}
