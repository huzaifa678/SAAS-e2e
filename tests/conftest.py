"""Shared fixtures for the smoke suite."""

from __future__ import annotations

import pytest

from saas_e2e.auth import KeycloakAuthError, fetch_token
from saas_e2e.config import settings as _settings
from saas_e2e.gateway import GatewayClient


@pytest.fixture(scope="session")
def settings():
    return _settings


@pytest.fixture(scope="session")
def token(settings) -> str:
    """A Keycloak bearer token for the whole run.

    Skips (not fails) the authenticated tests when no credentials are wired, so
    an unconfigured run still reports health instead of a red suite.
    """
    if not settings.can_auth:
        pytest.skip("No Keycloak credentials configured (E2E_KEYCLOAK_*).")
    try:
        return fetch_token(settings)
    except KeycloakAuthError as exc:
        pytest.fail(f"Could not obtain Keycloak token: {exc}")


@pytest.fixture()
def anon(settings):
    """Unauthenticated gateway client (health / 401 probes)."""
    with GatewayClient(
        settings.gateway_url,
        None,
        timeout=settings.http_timeout,
        verify=settings.verify_tls,
    ) as c:
        yield c


@pytest.fixture()
def gw(settings, token):
    """Authenticated gateway client."""
    with GatewayClient(
        settings.gateway_url,
        token,
        timeout=settings.http_timeout,
        verify=settings.verify_tls,
    ) as c:
        yield c
