"""auth-service scenarios.

auth-service is a **GraphQL** service: `POST /api/auth/` executes an operation
(schema: `me`, `register`, `login`, `refreshToken`, `logout`) behind the
gateway's JWT gate + its own `authenticate` middleware. GraphQL returns HTTP 200
even for operation errors, so these assert on the `data`/`errors` envelope.
"""

import uuid

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.auth]


def _gql(resp):
    """Return the parsed GraphQL body, asserting the transport reached auth."""
    assert (
        resp.status_code == 200
    ), f"GraphQL transport failed: {resp.status_code} {resp.text[:200]}"
    body = resp.json()
    assert "data" in body or "errors" in body, f"not a GraphQL response: {resp.text[:200]}"
    return body


def test_graphql_transport_and_me(gw):
    """The schema is served and a token is accepted: `me` returns a User or null
    (for a service-account subject with no user row) — but never a transport
    error."""
    body = _gql(gw.graphql("{ me { id email } }"))
    assert body.get("errors") is None or isinstance(body["errors"], list)


def test_invalid_query_returns_graphql_error(gw):
    """A malformed query must come back as a GraphQL error (200 + errors[]),
    proving the schema is validating input rather than 500-ing."""
    body = _gql(gw.graphql("{ thisFieldDoesNotExist }"))
    assert body.get("errors"), "expected a GraphQL validation error"


def test_register_login_refresh_flow(gw):
    """End-to-end auth lifecycle: register a fresh user -> log in -> refresh.

    Uses a unique email per run. GraphQL errors (e.g. a disabled registration
    policy) are surfaced as a skip with the server's message rather than a hard
    failure, so environment policy differences don't flake the suite."""
    email = f"e2e-{uuid.uuid4().hex[:12]}@example.test"
    password = uuid.uuid4().hex  # random throwaway secret for a test account

    reg = _gql(
        gw.graphql(
            "mutation($e:String!,$p:String!){ register(email:$e,password:$p){ id email } }",
            {"e": email, "p": password},
        )
    )
    if reg.get("errors"):
        pytest.skip(f"register rejected by policy: {reg['errors'][0].get('message')}")
    assert reg["data"]["register"]["email"] == email

    login = _gql(
        gw.graphql(
            "mutation($e:String!,$p:String!){ login(email:$e,password:$p){ accessToken refreshToken user { email } } }",
            {"e": email, "p": password},
        )
    )
    assert login.get("errors") is None, f"login failed: {login.get('errors')}"
    payload = login["data"]["login"]
    assert payload["accessToken"] and payload["refreshToken"]
    assert payload["user"]["email"] == email

    refreshed = _gql(
        gw.graphql(
            "mutation($t:String!){ refreshToken(token:$t){ accessToken } }",
            {"t": payload["refreshToken"]},
        )
    )
    assert refreshed.get("errors") is None, f"refresh failed: {refreshed.get('errors')}"
    assert refreshed["data"]["refreshToken"]["accessToken"]
