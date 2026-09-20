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


@lru_cache
def get_settings() -> Settings:
    return Settings()
