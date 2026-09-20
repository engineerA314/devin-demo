from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AlertSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.:-]+$")
    label: str = Field(min_length=1, max_length=120)
    value: Union[str, int, float]
    unit: Optional[str] = Field(default=None, max_length=30)


class IncidentEventEnvelope(BaseModel):
    """A lifecycle event for an incident already qualified by observability."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(
        min_length=3,
        max_length=160,
        pattern=r"^[a-zA-Z0-9_.:/-]+$",
    )
    incident_id: str = Field(
        min_length=3,
        max_length=160,
        pattern=r"^[a-zA-Z0-9_.:/-]+$",
    )
    event_action: Literal["trigger", "update", "acknowledge", "resolve"] = "trigger"
    source: str = Field(default="custom", min_length=1, max_length=80)
    repository: Optional[str] = Field(default=None, max_length=200)
    title: str = Field(min_length=3, max_length=240)
    service: str = Field(min_length=1, max_length=120)
    severity: str = Field(default="SEV-3", pattern=r"^SEV-[0-4]$")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    signals: list[AlertSignal] = Field(default_factory=list, max_length=20)
    evidence: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class IncidentEventAccepted(BaseModel):
    id: str
    incident_id: str
    status: str
    incident_status: str
    event_count: int
    duplicate_event_count: int
    incident_created: bool
    event_duplicate: bool
    duplicate: bool
    session_id: Optional[str] = None
    session_url: Optional[str] = None


# Backward-compatible imports for integrations still using the old endpoint name.
AlertEnvelope = IncidentEventEnvelope
AlertAccepted = IncidentEventAccepted
