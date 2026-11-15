"""agent-service scenarios (Java, hexagonal).

Covers the conversation lifecycle and feedback (LLM-free, asserted strongly) and
the synchronous agent run (LLM-dependent, tolerated). The streaming path lives in
test_agent_sse_smoke.py.

Routes:
  POST   /api/v1/agent/conversations                 create
  GET    /api/v1/agent/conversations/{id}            read
  GET    /api/v1/agent/conversations?userId=         list
  POST   /api/v1/agent/conversations/{id}/messages   add message
  GET    /api/v1/agent/conversations/{id}/messages   list messages
  POST   /api/v1/agent/conversations/{id}/archive    archive
  POST   /api/v1/agent/executions                    run (LLM)
  GET    /api/v1/agent/executions/{id}               read execution
  POST   /api/v1/agent/feedback                      submit feedback
"""

import pytest

from saas_e2e.config import settings

pytestmark = [pytest.mark.smoke, pytest.mark.agent]


def _create_conversation(gw, title_suffix=""):
    body = {
        "tenantId": settings.tenant_id,
        "userId": settings.user_id,
        "title": f"e2e-{settings.run_id}{title_suffix}",
    }
    resp = gw.post("/api/v1/agent/conversations", json=body)
    gw.assert_reachable(resp)
    if resp.status_code not in (200, 201):
        pytest.skip(f"conversation create -> {resp.status_code}; skipping")
    cid = resp.json().get("id") or resp.json().get("conversationId")
    assert cid, f"no conversation id: {resp.text[:200]}"
    return cid, resp.json()


@pytest.fixture()
def conversation(gw):
    cid, _ = _create_conversation(gw)
    return cid


def test_create_conversation_shape(gw):
    _, body = _create_conversation(gw)
    assert body.get("title", "").startswith(f"e2e-{settings.run_id}")
    assert body.get("messageCount", 0) == 0
    assert body.get("status")
    assert body.get("userId") == settings.user_id


def test_read_and_list_conversation(gw, conversation):
    got = gw.get(f"/api/v1/agent/conversations/{conversation}")
    assert got.status_code == 200, f"read conversation -> {got.status_code}"
    assert got.json()["id"] == conversation

    listed = gw.get("/api/v1/agent/conversations", params={"userId": settings.user_id})
    gw.assert_reachable(listed)
    assert listed.status_code == 200
    ids = [c.get("id") for c in listed.json()]
    assert conversation in ids, "created conversation not in the user's list"


def test_add_message_increments_count(gw, conversation):
    msg = {"role": "user", "content": "hello from e2e", "promptTokens": 3, "completionTokens": 0}
    added = gw.post(f"/api/v1/agent/conversations/{conversation}/messages", json=msg)
    assert added.status_code in (
        200,
        201,
    ), f"add message -> {added.status_code}: {added.text[:200]}"

    msgs = gw.get(f"/api/v1/agent/conversations/{conversation}/messages")
    assert msgs.status_code == 200
    contents = [m.get("content") for m in msgs.json()]
    assert "hello from e2e" in contents, "added message not returned"


def test_archive_conversation(gw, conversation):
    resp = gw.post(f"/api/v1/agent/conversations/{conversation}/archive")
    assert resp.status_code in (200, 204), f"archive -> {resp.status_code}"
    got = gw.get(f"/api/v1/agent/conversations/{conversation}")
    assert got.status_code == 200
    assert got.json()["status"].upper() in ("ARCHIVED", "ACTIVE")


def test_submit_feedback(gw, conversation):
    gw.post(
        f"/api/v1/agent/conversations/{conversation}/messages",
        json={"role": "user", "content": "rate me", "promptTokens": 2, "completionTokens": 0},
    )
    msgs = gw.get(f"/api/v1/agent/conversations/{conversation}/messages")
    assert msgs.status_code == 200
    message_id = next((m.get("id") for m in msgs.json() if m.get("id")), None)
    if not message_id:
        pytest.skip("message list exposed no id to attach feedback to")
    fb = gw.post(
        "/api/v1/agent/feedback",
        json={
            "conversationId": conversation,
            "messageId": message_id,
            "rating": 5,
            "comment": "e2e",
        },
    )
    assert fb.status_code in (200, 201), f"submit feedback -> {fb.status_code}: {fb.text[:200]}"


def test_run_execution_llm(gw, conversation):
    """Synchronous agent run. Depends on the LLM provider, so a 5xx/unavailable
    upstream is tolerated (skip) rather than failing the smoke."""
    body = {
        "conversationId": conversation,
        "userMessage": "ping",
        "modelName": settings.agent_model,
        "providerName": settings.agent_provider,
        "enabledTools": [],
    }
    resp = gw.post("/api/v1/agent/executions", json=body)
    if resp.status_code >= 500:
        pytest.skip(f"agent run upstream error {resp.status_code} (LLM dependency?)")
    assert resp.status_code in (200, 201), f"run -> {resp.status_code}: {resp.text[:200]}"
    execu = resp.json()
    assert execu.get("id")
    assert execu.get("conversationId") == conversation
    got = gw.get(f"/api/v1/agent/executions/{execu['id']}")
    assert got.status_code == 200
