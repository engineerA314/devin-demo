#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
SUPERSET_REPO="${SUPERSET_REPO:-$(cd "$DEMO_REPO/../superset" && pwd)}"

if [[ ! -f "$SUPERSET_REPO/docker-compose-light.yml" ]]; then
  echo "Apache Superset fork not found at $SUPERSET_REPO" >&2
  echo "Set SUPERSET_REPO to the path of engineerA314/superset." >&2
  exit 1
fi

SUPERSET_REPO_PATH="$SUPERSET_REPO" docker compose \
  -p devin-superset \
  -f "$DEMO_REPO/infra/superset/docker-compose.yml" \
  up --build -d

echo "Waiting for Superset at http://localhost:9001 ..."
for attempt in {1..90}; do
  if curl --fail --silent --output /dev/null http://localhost:9001/health; then
    break
  fi
  if [[ "$attempt" == 90 ]]; then
    echo "Superset did not become healthy within 15 minutes." >&2
    exit 1
  fi
  sleep 10
done

echo "Superset is ready with embedded dashboard 00000000-0000-4000-8000-000000000001."
