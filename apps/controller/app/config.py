from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Luma Incident Controller"
    cors_origins: str = (
        "http://localhost:3000,http://localhost:5173,"
        "http://127.0.0.1:3000,http://127.0.0.1:5173"
    )

    superset_internal_url: str = ""
    superset_public_url: str = ""
    superset_dashboard_id: str = ""
    superset_username: str = ""
    superset_password: str = ""

    devin_api_key: str = ""
    devin_org_id: str = ""
    devin_api_base_url: str = "https://api.devin.ai"
    devin_triage_automation_id: str = ""
    devin_triage_webhook_url: str = ""
    devin_triage_webhook_secret: str = ""
    devin_remediation_automation_id: str = ""
    devin_triage_max_acu: int = 20
    devin_remediation_max_acu: int = 40

    github_repository: str = "engineerA314/superset"
    github_token: str = ""
    github_webhook_secret: str = ""
    github_managed_label: str = "autopilot-managed"
    incident_db_path: str = ".state/incidents.db"
    workflow_reconcile_seconds: int = 20

    @property
    def embedded_superset_configured(self) -> bool:
        return all(
            (
                self.superset_internal_url,
                self.superset_public_url,
                self.superset_dashboard_id,
                self.superset_username,
                self.superset_password,
            )
        )

    @property
    def parsed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def devin_configured(self) -> bool:
        return bool(self.devin_api_key and self.devin_org_id)

    @property
    def triage_webhook_configured(self) -> bool:
        return bool(self.devin_triage_webhook_url and self.devin_triage_webhook_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
