"""usage-service ETL pipeline smoke — event-first, not request/response.

usage-service ingests ``billing.usage-charge.created`` from Kafka, aggregates
into Postgres, and serves a read API. There is no synchronous write endpoint,
so the only faithful end-to-end check is:

    produce one UsageChargeCreated event (unique `metric` for this run)
        -> wait for ingest + aggregate
        -> poll GET /api/v1/usage/aggregates?metric=<unique> until it appears

This is marked ``usage_etl`` so it can be run/sharded separately from the fast
synchronous HTTP smokes (the pipeline is inherently slower and polls).
"""

import time

import pytest

from saas_e2e.config import settings
from saas_e2e.kafka_producer import produce_usage_charge

pytestmark = [pytest.mark.smoke, pytest.mark.usage_etl, pytest.mark.kafka]


@pytest.fixture(autouse=True)
def _requires_kafka():
    if not settings.can_kafka:
        pytest.skip("Kafka/Schema-Registry not configured (E2E_KAFKA_* unset).")


def test_usage_read_api_reachable(gw):
    resp = gw.get("/api/v1/usage/aggregates", params={"metric": "nonexistent"})
    gw.assert_reachable(resp)


def test_usage_pipeline_end_to_end(gw):
    """Full ETL path: event in -> aggregate out via the read API."""
    metric = f"e2e-smoke-{settings.run_id}"
    payload = produce_usage_charge(settings, metric=metric, quantity=7)

    deadline = time.monotonic() + settings.pipeline_timeout
    last = None
    while time.monotonic() < deadline:
        resp = gw.get("/api/v1/usage/aggregates", params={"metric": metric})
        gw.assert_reachable(resp)
        if resp.status_code == 200:
            rows = resp.json()
            last = rows
            if any(r.get("metric") == metric for r in rows):
                # Pipeline delivered: ingest -> aggregate -> read API.
                assert rows, "aggregate row present"
                return
        time.sleep(settings.poll_interval)

    pytest.fail(
        f"metric {metric!r} (invoice {payload['invoiceId']}) never surfaced in "
        f"usage aggregates within {settings.pipeline_timeout}s; last={last!r}"
    )
