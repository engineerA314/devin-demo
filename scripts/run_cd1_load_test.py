#!/usr/bin/env python3
"""Measure CD-1 through the live Superset chart-data API and PostgreSQL."""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
import math
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:9001")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--customers", type=int, nargs="+", default=[1, 25, 75])
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--state",
        type=Path,
        default=Path(".state/superset/cd1-benchmark.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/cd1-load-test.json"),
    )
    return parser.parse_args()


def psql(sql: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "devin-superset-analytics-db-1",
            "psql",
            "-U",
            "superset",
            "-d",
            "analytics",
            "-At",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def reset_query_stats() -> None:
    psql("SELECT pg_stat_statements_reset()")


def wait_for_warehouse() -> None:
    for _ in range(60):
        active = int(
            psql(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE state = 'active' AND query ILIKE '%public.orders%' "
                "AND query NOT ILIKE '%pg_stat_activity%'"
            )
            or 0
        )
        if active == 0:
            return
        time.sleep(0.5)
    raise RuntimeError("warehouse queries did not drain")


def warehouse_stats() -> dict[str, Any]:
    raw = psql(
        "SELECT calls || E'\\t' || round(total_exec_time::numeric, 1) || "
        "E'\\t' || round(mean_exec_time::numeric, 1) "
        "FROM pg_stat_statements "
        "WHERE query ILIKE '%SUM(revenue)%' AND query ILIKE '%public.orders%' "
        "AND query NOT ILIKE '%GROUP BY%' ORDER BY calls DESC LIMIT 1"
    )
    if not raw:
        return {"totals_query_calls": 0, "total_exec_ms": 0.0, "mean_exec_ms": 0.0}
    calls, total_ms, mean_ms = raw.split("\t")
    return {
        "totals_query_calls": int(calls),
        "total_exec_ms": float(total_ms),
        "mean_exec_ms": float(mean_ms),
    }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def payload_for_customer(payload: dict[str, Any], customer_id: int) -> dict[str, Any]:
    """Scope every warehouse query to one customer tenant."""
    customer_payload = copy.deepcopy(payload)
    tenant_filter = {
        "col": "tenant_id",
        "op": "IN",
        "val": [f"tenant-{customer_id}"],
    }
    for query in customer_payload["queries"]:
        query.setdefault("filters", []).append(tenant_filter)
    return customer_payload


def main() -> int:
    args = parse_args()
    state = json.loads(args.state.read_text())
    payload = state["payload"]
    base_url = args.base_url.rstrip("/")
    max_customers = max(args.customers)
    customer_payloads = [
        payload_for_customer(payload, customer_id)
        for customer_id in range(max_customers)
    ]

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        login = client.post(
            "/api/v1/security/login",
            json={
                "username": args.username,
                "password": args.password,
                "provider": "db",
                "refresh": True,
            },
        )
        login.raise_for_status()
        token = login.json()["access_token"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Populate both chart-data entries for every tenant. Every measured request
    # after this should be a warm cache hit from Superset's perspective.
    def warm_customer(customer_id: int) -> None:
        with httpx.Client(base_url=base_url, timeout=120.0) as client:
            warmup = client.post(
                "/api/v1/chart/data",
                headers=headers,
                json=customer_payloads[customer_id],
            )
            warmup.raise_for_status()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(warm_customer, range(max_customers)))

    def request(customer_id: int) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            with httpx.Client(base_url=base_url, timeout=args.timeout) as client:
                response = client.post(
                    "/api/v1/chart/data",
                    headers=headers,
                    json=customer_payloads[customer_id],
                )
                cached = []
                if response.status_code == 200:
                    cached = [
                        result.get("is_cached")
                        for result in response.json().get("result", [])
                    ]
                return {
                    "customer": customer_id,
                    "status": response.status_code,
                    "seconds": time.perf_counter() - started,
                    "cached": cached,
                }
        except httpx.HTTPError as error:
            return {
                "customer": customer_id,
                "status": "timeout",
                "seconds": time.perf_counter() - started,
                "error": type(error).__name__,
            }

    runs: list[dict[str, Any]] = []
    for customers in args.customers:
        wait_for_warehouse()
        reset_query_stats()
        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=customers) as pool:
            results = list(pool.map(request, range(customers)))
        wall_seconds = time.perf_counter() - started
        wait_for_warehouse()

        latencies = [float(result["seconds"]) for result in results]
        statuses = Counter(str(result["status"]) for result in results)
        run = {
            "virtual_customers": customers,
            "client_timeout_seconds": args.timeout,
            "successes": statuses.get("200", 0),
            "failures": customers - statuses.get("200", 0),
            "status_counts": dict(statuses),
            "warm_cache_successes": sum(
                result.get("cached") == [True, True] for result in results
            ),
            "wall_seconds": round(wall_seconds, 3),
            "p50_seconds": round(percentile(latencies, 0.50), 3),
            "p95_seconds": round(percentile(latencies, 0.95), 3),
            "max_seconds": round(max(latencies), 3),
            **warehouse_stats(),
        }
        runs.append(run)
        print(json.dumps(run, indent=2))

    report = {
        "candidate": "CD-1",
        "generated_at": datetime.now(UTC).isoformat(),
        "superset_url": base_url,
        "warehouse_rows": state["rows"],
        "customer_scope": (
            "one separately warmed tenant_id filter per virtual customer"
        ),
        "cache_expectation": "warm chart-data requests execute zero warehouse queries",
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
