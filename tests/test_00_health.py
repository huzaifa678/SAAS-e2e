"""Gateway liveness/readiness — the fastest fail-fast signal.

Runs first (file name sorts first) and needs no auth: if the public entrypoint
is down, nothing else can pass, so surface that immediately.
"""

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.health]


@pytest.mark.parametrize("path", ["/healthz/live", "/healthz/ready"])
def test_gateway_health(anon, path):
    resp = anon.get(path)
    assert resp.status_code == 200, f"gateway {path} -> {resp.status_code}"


def test_gateway_rejects_unauthenticated(anon):
    """A protected route without a token must be refused (401/403), proving the
    Keycloak JWT interceptor is active rather than wide open."""
    resp = anon.get(
        "/api/v1/billing/active", params={"userId": "00000000-0000-0000-0000-000000000000"}
    )
    assert resp.status_code in (401, 403), f"expected auth challenge, got {resp.status_code}"
