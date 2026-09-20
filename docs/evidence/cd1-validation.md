# CD-1 validation: cached contribution totals bypass the query cache

## Incident claim

Table V2 charts using **Percent of total → All records** send a grouped data
query and a second totals query. On the Superset base commit used for this
experiment (`4511c13`), a warm chart-data request reports both results as cached
but still executes the totals aggregate against the warehouse.

Under concurrent embedded analytics traffic, each customer request therefore
adds one full-table warehouse aggregate. The redundant work increases latency
until otherwise healthy cached panels exceed the product's rendering budget.

## Reproduction

The benchmark uses:

- Apache Superset at base commit `4511c13` and its `/api/v1/chart/data` endpoint;
- a physical PostgreSQL warehouse with a 10 million row `orders` fact table;
- a Table V2 query with a contribution post-processing step and the matching
  ungrouped totals query;
- a distinct `tenant_id` scope and separately warmed result cache for every
  virtual customer; and
- a five-second chart rendering budget for the mock SaaS.

```bash
make superset
make cd1-provision
make cd1-load-test
```

## Measured result

| Warm virtual customer requests | Warehouse totals queries | Successful panels | Timed out panels | p95 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 1 | 0 | 0.544s |
| 25 | 25 | 25 | 0 | 3.584s |
| 75 | 75 | 25 | 50 | 5.025s |

All tenant-scoped cache entries were warmed before measurement, and every
successful response reported both query results as cache hits. Despite that,
PostgreSQL `pg_stat_statements` recorded exactly one ungrouped `SUM(revenue)`
per customer request.

The raw baseline is in [`cd1-load-test.json`](cd1-load-test.json).

## Causal check

For diagnosis only, the totals acquisition in
`QueryContextProcessor.ensure_totals_available()` was changed from the direct
`get_query_result()` path to the cache-aware `get_df_payload_result()` path.
No warehouse, payload, cache, timeout, or concurrency setting changed. This
one-line experiment isolates the mechanism; it is separate from PR #12's test
results below.

| Warm virtual customer requests | Warehouse totals queries | Successful panels | Timed out panels | p95 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 1 | 0 | 0.059s |
| 25 | 0 | 25 | 0 | 0.976s |
| 75 | 0 | 75 | 0 | 2.486s |

The raw causal-check result is in
[`cd1-load-test-fixed.json`](cd1-load-test-fixed.json). The prototype change
was not committed to the base branch.

## Devin end-to-end result

The CD-1 simulator started workflow `INC-6736371C`. The controller kept one
workflow for a unique monitor event and its repeated delivery. Devin attributed
the failure to Superset after an executed failing reproduction, created
[issue #11](https://github.com/engineerA314/superset/issues/11) after 6 minutes
21 seconds, and opened [PR #12](https://github.com/engineerA314/superset/pull/12)
after 14 minutes 19 seconds.

Devin's PR verification reported 640 related tests passed, 2 expected failures,
and clean Ruff and Mypy checks. The fork has no GitHub check runs configured.
The PR remains open for human review. The warehouse load harness was not rerun
against PR #12; the controlled causal experiment above is independent evidence,
not a claim about that PR's measured throughput.

## Conclusion

CD-1 is confirmed as a Superset defect with customer-visible impact. The
warehouse amplification is linear in concurrent warm requests, the failure is
observable as chart latency and timeout rate, and a cache-aware code path
eliminates both the redundant warehouse traffic and the measured timeouts.
