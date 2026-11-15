"""Keycloak OIDC token acquisition for the smoke suite.

All traffic enters through the api-gateway, which validates a Keycloak JWT
(see the gateway's ``keycloakJWKSURL``). The suite therefore mints a real token
from the staging ``saas`` realm and sends it as a Bearer header. Prefers the
``client_credentials`` grant (headless, no human user); falls back to the
``password`` grant when a username/password pair is configured.
"""

from __future__ import annotations

import httpx

from .config import Settings


class KeycloakAuthError(RuntimeError):
    pass


def fetch_token(settings: Settings) -> str:
    """Return a bearer access token, or raise KeycloakAuthError."""
    token_url = (
        f"{settings.keycloak_url.rstrip('/')}"
        f"/realms/{settings.keycloak_realm}/protocol/openid-connect/token"
    )

    if settings.has_oidc_client:
        data = {
            "grant_type": "client_credentials",
            "client_id": settings.keycloak_client_id,
            "client_secret": settings.keycloak_client_secret,
        }
    elif settings.has_oidc_password:
        data = {
            "grant_type": "password",
            "client_id": settings.keycloak_client_id or "saas-e2e",
            "username": settings.keycloak_username,
            "password": settings.keycloak_password,
        }
        if settings.keycloak_client_secret:
            data["client_secret"] = settings.keycloak_client_secret
    else:
        raise KeycloakAuthError(
            "No Keycloak credentials configured "
            "(set E2E_KEYCLOAK_CLIENT_ID/SECRET or USERNAME/PASSWORD)."
        )

    try:
        resp = httpx.post(
            token_url,
            data=data,
            timeout=settings.http_timeout,
            verify=settings.verify_tls,
        )
    except httpx.HTTPError as exc:  # pragma: no cover - network failure path
        raise KeycloakAuthError(f"Keycloak unreachable at {token_url}: {exc}") from exc

    if resp.status_code != 200:
        raise KeycloakAuthError(f"Token request failed [{resp.status_code}]: {resp.text[:300]}")

    token = resp.json().get("access_token")
    if not token:
        raise KeycloakAuthError("Token response contained no access_token.")
    return token
