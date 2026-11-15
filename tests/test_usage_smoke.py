"""usage-service read-API scenarios (FastAPI).

The synchronous read path:
  GET /api/v1/usage/aggregates?customer_id=&metric=   daily/monthly/rolling totals
  GET /api/v1/usage/search?q=&k=                      pgvector semantic search

The event-driven ETL pipeline is covered separately in test_usage_etl_smoke.py.
"""

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.usage]


def test_aggregates_no_filter(gw):
    resp = gw.get("/api/v1/usage/aggregates")
    assert resp.status_code == 200, f"aggregates -> {resp.status_code}: {resp.text[:200]}"
    assert isinstance(resp.json(), list)


def test_aggregates_filtered_rows_match(gw):
    """Filtering by metric must only return rows for that metric (or none)."""
    resp = gw.get(
        "/api/v1/usage/aggregates", params={"metric": "api_calls", "customer_id": "nobody"}
    )
    assert resp.status_code == 200, f"aggregates filtered -> {resp.status_code}"
    rows = resp.json()
    assert isinstance(rows, list)
    assert all(r.get("metric") == "api_calls" for r in rows), "filter leaked other metrics"
    for r in rows:
        assert {"customer_id", "metric", "daily_total", "monthly_total", "rolling_avg"} <= r.keys()


def test_search_returns_envelope(gw):
    """Semantic search echoes the query and returns a hits list. Embedding needs
    the provider key, so a 5xx is tolerated (skip)."""
    resp = gw.get("/api/v1/usage/search", params={"q": "database usage", "k": 3})
    if resp.status_code >= 500:
        pytest.skip(f"search upstream error {resp.status_code} (embedding provider?)")
    assert resp.status_code == 200, f"search -> {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body.get("query") == "database usage"
    assert isinstance(body.get("hits"), list)


def test_search_requires_query(gw):
    """`q` is required with min_length=1 → omitting it is a 422 (FastAPI)."""
    resp = gw.get("/api/v1/usage/search")
    gw.assert_reachable(resp)
    assert resp.status_code == 422, f"missing q -> {resp.status_code}"


def test_search_k_upper_bound(gw):
    """`k` is capped at 50 → a larger value is rejected (422), not silently run."""
    resp = gw.get("/api/v1/usage/search", params={"q": "x", "k": 999})
    gw.assert_reachable(resp)
    assert resp.status_code == 422, f"k=999 -> {resp.status_code}"
