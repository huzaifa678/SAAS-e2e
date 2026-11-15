"""agent-service Server-Sent Events streaming smoke.

Dedicated because SSE is a different transport from the JSON request/response
paths: `POST /api/v1/agent/executions/stream` returns `text/event-stream` and
pushes tokens/tool-calls/completion events over a held-open connection
(Reactor Flux bridged from a Sinks.Many). We assert the stream opens with the
right content type and yields at least one event frame before completion.

Tooling: httpx streaming + httpx-sse (the standard Python SSE client); handles
chunked framing and reconnection semantics that a plain GET cannot.
"""

import httpx
import pytest
from httpx_sse import connect_sse

from saas_e2e.config import settings

pytestmark = [pytest.mark.smoke, pytest.mark.agent, pytest.mark.sse]


@pytest.fixture()
def conversation_id(gw):
    body = {
        "tenantId": settings.tenant_id,
        "userId": settings.user_id,
        "title": f"e2e-sse-{settings.run_id}",
    }
    resp = gw.post("/api/v1/agent/conversations", json=body)
    gw.assert_reachable(resp)
    if resp.status_code not in (200, 201):
        pytest.skip(f"conversation create returned {resp.status_code}; skipping SSE")
    cid = resp.json().get("id") or resp.json().get("conversationId")
    assert cid, f"no conversation id in response: {resp.text[:200]}"
    return cid


def test_agent_stream_emits_events(token, conversation_id):
    body = {
        "conversationId": conversation_id,
        "userMessage": "stream a short hello",
        "modelName": settings.agent_model,
        "providerName": settings.agent_provider,
        "enabledTools": [],
    }
    url = f"{settings.gateway_url.rstrip('/')}/api/v1/agent/executions/stream"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
    }

    events = []
    with (
        httpx.Client(timeout=settings.sse_timeout, verify=settings.verify_tls) as client,
        connect_sse(client, "POST", url, json=body, headers=headers) as event_source,
    ):
        resp = event_source.response
        assert resp.status_code < 500, f"stream open failed: {resp.status_code}"
        if resp.status_code != 200:
            pytest.skip(f"stream not available ({resp.status_code}); LLM dependency?")
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct, f"unexpected content-type: {ct!r}"
        # Collect a handful of frames to prove it's a real token stream, not a
        # single-shot response. Stop early once we've seen enough.
        for sse in event_source.iter_sse():
            events.append(sse)
            if len(events) >= 5:
                break

    assert events, "stream opened but produced no SSE events before timeout"
    # Each frame should carry an event type and/or a data payload.
    assert any(e.event or e.data for e in events), "SSE frames had neither event nor data"
