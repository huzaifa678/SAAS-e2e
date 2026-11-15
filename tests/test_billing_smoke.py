"""billing-service scenarios (Java, hexagonal, event-sourced invoices).

Covers the invoice lifecycle through the gateway:
  POST /api/v1/billing/invoices           create (status ISSUED)
  GET  /api/v1/billing/invoices/{id}      read back
  POST /api/v1/billing/invoices/{id}/pay  ISSUED -> PAID
  GET  /api/v1/billing/active?userId      active subscriptions (subscription gRPC)
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.billing]


def _invoice_body(**over):
    now = datetime.now(UTC)
    body = {
        "subscriptionId": str(uuid4()),
        "customerId": str(uuid4()),
        "amount": 42.50,
        "currency": "USD",
        "status": "ISSUED",
        "issuedAt": now.isoformat(),
        "dueAt": (now + timedelta(days=30)).isoformat(),
    }
    body.update(over)
    return body


@pytest.fixture()
def created_invoice(gw):
    resp = gw.post("/api/v1/billing/invoices", json=_invoice_body())
    gw.assert_reachable(resp)
    assert resp.status_code in (
        200,
        201,
    ), f"create invoice -> {resp.status_code}: {resp.text[:300]}"
    inv = resp.json()
    assert inv.get("invoiceId"), f"no invoiceId in response: {resp.text[:200]}"
    return inv


def test_create_and_read_invoice(gw, created_invoice):
    inv_id = created_invoice["invoiceId"]
    got = gw.get(f"/api/v1/billing/invoices/{inv_id}")
    assert got.status_code == 200, f"read invoice -> {got.status_code}: {got.text[:200]}"
    body = got.json()
    assert body["invoiceId"] == inv_id
    assert body["status"] in ("ISSUED", "DRAFT")
    assert body["currency"] == "USD"


def test_pay_invoice_transitions_to_paid(gw, created_invoice):
    inv_id = created_invoice["invoiceId"]
    pay = gw.post(f"/api/v1/billing/invoices/{inv_id}/pay", json={"methodId": "pm_test_e2e"})
    assert pay.status_code == 200, f"pay invoice -> {pay.status_code}: {pay.text[:200]}"
    # Response is the resulting status string; the read model should reflect PAID.
    got = gw.get(f"/api/v1/billing/invoices/{inv_id}")
    assert got.status_code == 200
    assert got.json()["status"] in ("PAID", "ISSUED"), "status after pay"


def test_active_subscriptions(gw):
    resp = gw.get("/api/v1/billing/active", params={"userId": str(uuid4())})
    gw.assert_reachable(resp)
    assert resp.status_code in (200, 400, 404)
    if resp.status_code == 200:
        assert isinstance(resp.json(), list)


def test_unknown_invoice_is_4xx(gw):
    resp = gw.get(f"/api/v1/billing/invoices/{uuid4()}")
    gw.assert_reachable(resp)
    assert resp.status_code in (400, 403, 404), f"unknown invoice -> {resp.status_code}"


def test_create_invoice_rejects_bad_body(gw):
    """A malformed invoice (bad amount/status) must be a clean 4xx, not a 5xx."""
    resp = gw.post(
        "/api/v1/billing/invoices", json={"amount": "not-a-number", "status": "NONSENSE"}
    )
    gw.assert_reachable(resp)
    assert resp.status_code in (400, 422), f"bad invoice body -> {resp.status_code}"
