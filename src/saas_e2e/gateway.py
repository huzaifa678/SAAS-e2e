"""Thin httpx wrapper around the api-gateway for smoke assertions.

The suite talks to services ONLY through the gateway (the real client path),
never to pod IPs or internal Services directly. ``GatewayClient`` carries the
bearer token and exposes small helpers plus a `no_5xx` smoke assertion: for a
smoke test we assert the route is wired and the service is up (no 5xx / no
gateway error), without pinning exact business-field validation.
"""

from __future__ import annotations

from typing import Any, Self

import httpx

OK_SMOKE = "status code {code} on {method} {path} indicates the service is reachable"


class GatewayClient:
    def __init__(self, base_url: str, token: str | None, *, timeout: float, verify: bool):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            verify=verify,
            follow_redirects=True,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, **kw: Any) -> httpx.Response:
        return self._client.get(path, **kw)

    def post(self, path: str, **kw: Any) -> httpx.Response:
        return self._client.post(path, **kw)

    def put(self, path: str, **kw: Any) -> httpx.Response:
        return self._client.put(path, **kw)

    def patch(self, path: str, **kw: Any) -> httpx.Response:
        return self._client.patch(path, **kw)

    def delete(self, path: str, **kw: Any) -> httpx.Response:
        return self._client.request("DELETE", path, **kw)

    def graphql(self, query: str, variables: dict | None = None) -> httpx.Response:
        """POST a GraphQL operation to the auth-service (via /api/auth/)."""
        return self._client.post("/api/auth/", json={"query": query, "variables": variables or {}})

    @property
    def raw(self) -> httpx.Client:
        return self._client

    @staticmethod
    def assert_reachable(resp: httpx.Response) -> None:
        """A service is 'up' for smoke purposes if it answered without a 5xx.

        4xx (auth, validation, not-found) still proves the route is wired and
        the upstream pod is serving — which is all a post-deploy smoke needs.
        """
        assert resp.status_code < 500, (
            f"{resp.request.method} {resp.request.url.path} returned "
            f"{resp.status_code}: {resp.text[:300]}"
        )
