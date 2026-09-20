#!/usr/bin/env python3
"""Provision the real warehouse fixture used to reproduce CD-1.

Run this inside the Superset container. It creates a PostgreSQL fact table,
registers it as a Superset dataset, and writes the exact chart-data payload used
by the load test to the shared demo state directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg2


WAREHOUSE_DSN = os.environ.get(
    "CD1_WAREHOUSE_DSN",
    "postgresql://superset:superset@analytics-db:5432/analytics",
)
SUPERSET_WAREHOUSE_URI = os.environ.get(
    "CD1_SUPERSET_WAREHOUSE_URI",
    "postgresql+psycopg2://superset:superset@analytics-db:5432/analytics",
)
STATE_PATH = Path(
    os.environ.get("CD1_STATE_PATH", "/tmp/superset-demo/cd1-benchmark.json")
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=10_000_000)
    parser.add_argument("--recreate", action="store_true")
    return parser.parse_args()


def provision_warehouse(rows: int, recreate: bool) -> None:
    connection = psycopg2.connect(WAREHOUSE_DSN)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
            cursor.execute("SELECT to_regclass('public.orders')")
            exists = cursor.fetchone()[0] is not None
            if exists and not recreate:
                cursor.execute("SELECT count(*) FROM public.orders")
                existing_rows = int(cursor.fetchone()[0])
                if existing_rows == rows:
                    return

            cursor.execute("DROP TABLE IF EXISTS public.orders")
            cursor.execute(
                """
                CREATE UNLOGGED TABLE public.orders AS
                SELECT
                  gs AS order_id,
                  'tenant-' || (gs %% 100)::text AS tenant_id,
                  'product-' || (gs %% 250)::text AS product_name,
                  (((gs::bigint * 7919) %% 100000)::numeric / 100) AS revenue,
                  TIMESTAMP '2025-01-01'
                    + ((gs %% 31536000) || ' seconds')::interval AS occurred_at
                FROM generate_series(1, %s) AS gs
                """,
                (rows,),
            )
            cursor.execute("ANALYZE public.orders")
    finally:
        connection.close()


def query_payload(dataset_id: int) -> dict[str, Any]:
    common: dict[str, Any] = {
        "time_range": "No filter",
        "filters": [],
        "extras": {"having": "", "where": ""},
        "applied_time_extras": {},
        "annotation_layers": [],
        "row_limit": 100,
        "row_offset": 0,
        "series_limit": 0,
        "order_desc": True,
        "url_params": {},
        "custom_params": {},
        "custom_form_data": {},
    }
    return {
        "datasource": {"id": dataset_id, "type": "table"},
        "force": False,
        "queries": [
            {
                **common,
                "columns": ["product_name"],
                "metrics": ["count", "sum_revenue"],
                "orderby": [["sum_revenue", False]],
                "post_processing": [
                    {
                        "operation": "contribution",
                        "options": {
                            "columns": ["sum_revenue"],
                            "rename_columns": ["%sum_revenue"],
                        },
                    }
                ],
            },
            {
                **common,
                "columns": [],
                "metrics": ["sum_revenue"],
                "orderby": [],
                "post_processing": [],
                "row_limit": 0,
                "row_offset": 0,
                "is_timeseries": False,
            },
        ],
        "result_format": "json",
        "result_type": "full",
    }


def register_superset_dataset() -> int:
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable, SqlMetric
        from superset.models.core import Database

        database = (
            db.session.query(Database)
            .filter_by(database_name="CD-1 Analytics Warehouse")
            .one_or_none()
        )
        if database is None:
            database = Database(
                database_name="CD-1 Analytics Warehouse",
                sqlalchemy_uri=SUPERSET_WAREHOUSE_URI,
            )
            db.session.add(database)
            db.session.flush()
        else:
            database.sqlalchemy_uri = SUPERSET_WAREHOUSE_URI
        database.cache_timeout = 3600
        db.session.commit()

        dataset = (
            db.session.query(SqlaTable)
            .filter_by(
                database_id=database.id,
                schema="public",
                table_name="orders",
            )
            .one_or_none()
        )
        if dataset is None:
            dataset = SqlaTable(
                database=database,
                database_id=database.id,
                schema="public",
                table_name="orders",
            )
            db.session.add(dataset)
            db.session.flush()
        dataset.cache_timeout = 3600
        dataset.fetch_metadata()
        if not any(metric.metric_name == "sum_revenue" for metric in dataset.metrics):
            dataset.metrics.append(
                SqlMetric(
                    metric_name="sum_revenue",
                    verbose_name="Revenue",
                    expression="SUM(revenue)",
                )
            )
        db.session.commit()
        return int(dataset.id)


def main() -> int:
    args = parse_args()
    provision_warehouse(args.rows, args.recreate)
    dataset_id = register_superset_dataset()
    state = {
        "rows": args.rows,
        "dataset_id": dataset_id,
        "payload": query_payload(dataset_id),
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
