from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SCENARIO_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


class ObservabilitySnapshotStore:
    """Read deterministic exports from the observability boundary.

    The demo does not recreate Datadog, Grafana, or Better Stack. These files
    represent the read-only RUM, APM, query, change, and service-health views an
    investigation agent would access through those products' APIs in production.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[1] / "fixtures"

    def load(
        self,
        scenario_id: str | None,
        repository_mapping: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        if not scenario_id or not SCENARIO_ID.fullmatch(scenario_id):
            return None
        directory = self.root / scenario_id.lower()
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            return None

        manifest = self._read_json(manifest_path)
        artifacts: list[dict[str, Any]] = []
        for descriptor in manifest.get("artifacts") or []:
            filename = str(descriptor.get("file") or "")
            path = (directory / filename).resolve()
            if not filename or directory.resolve() not in path.parents or not path.is_file():
                continue
            data = self._read_json(path)
            if repository_mapping:
                data = self._map_repositories(data, repository_mapping)
            artifacts.append({**descriptor, "data": data})
        return {**manifest, "artifacts": artifacts}

    @classmethod
    def _map_repositories(cls, value: Any, mapping: dict[str, str]) -> Any:
        if isinstance(value, dict):
            return {
                key: (
                    mapping.get(item, item)
                    if key == "repository" and isinstance(item, str)
                    else cls._map_repositories(item, mapping)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._map_repositories(item, mapping) for item in value]
        return value

    @staticmethod
    def public_view(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
        if not snapshot:
            return None
        return {
            "id": snapshot.get("id"),
            "provider": snapshot.get("provider"),
            "mode": snapshot.get("mode"),
            "capturedAt": snapshot.get("captured_at"),
            "window": snapshot.get("window"),
            "description": snapshot.get("description"),
            "artifacts": [
                {
                    key: artifact.get(key)
                    for key in (
                        "id",
                        "label",
                        "source",
                        "record_count",
                        "sample_count",
                        "summary",
                    )
                }
                for artifact in snapshot.get("artifacts") or []
            ],
        }

    @staticmethod
    def prompt_packet(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
        if not snapshot:
            return None
        return {
            "snapshot_id": snapshot.get("id"),
            "provider": snapshot.get("provider"),
            "capture_mode": snapshot.get("mode"),
            "captured_at": snapshot.get("captured_at"),
            "window": snapshot.get("window"),
            "notice": (
                "This is a deterministic export of upstream observability views. "
                "It contains observations, not a controller-generated diagnosis."
            ),
            "artifacts": snapshot.get("artifacts") or [],
        }

    @staticmethod
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))
