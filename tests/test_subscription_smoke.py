"""subscription-service scenarios.

subscription-service exposes its business API over **gRPC** (port 50051, called
by billing-service), not REST — its only HTTP surface is health. So through the
gateway we can only assert the proxy route is wired; the subscription domain is
exercised **transitively** by the billing invoice flow (billing calls the
subscription gRPC `active`/lookup during create + `GET /api/v1/billing/active`).
"""

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.subscription]


def test_subscription_proxy_is_wired(gw):
    # No REST business route exists (gRPC-only), so a 404 from the upstream is
    # fine — what matters is the gateway reached subscription without a 5xx/502.
    resp = gw.get("/api/subscription/")
    gw.assert_reachable(resp)


def test_billing_active_exercises_subscription_grpc(gw):
    """billing's `/active` fans out to the subscription gRPC service — a clean
    (non-5xx) response proves that gRPC hop is healthy end to end."""
    from uuid import uuid4

    resp = gw.get("/api/v1/billing/active", params={"userId": str(uuid4())})
    gw.assert_reachable(resp)
    assert resp.status_code in (200, 400, 404), f"unexpected {resp.status_code}"
