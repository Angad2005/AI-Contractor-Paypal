import httpx
import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.jobs import Contract
from app.services import paypal_service


def test_paypal_api_requests_use_oauth_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "sandbox")
    monkeypatch.setattr(paypal_service, "_token", lambda: "sandbox-access-token")
    requests = []
    order_payloads = []

    class FakeClient:
        def __init__(self, timeout):
            assert timeout == 30

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, *, headers, json):
            requests.append(("POST", url, headers))
            if url.endswith("/v2/checkout/orders"):
                order_payloads.append(json)
            if url.endswith("/capture"):
                return httpx.Response(
                    201,
                    json={
                        "status": "COMPLETED",
                        "purchase_units": [{
                            "reference_id": "job-123",
                            "payments": {"captures": [{
                                "id": "capture-123",
                                "status": "COMPLETED",
                                "amount": {"currency_code": "USD", "value": "12.50"},
                            }]},
                        }],
                    },
                    request=httpx.Request("POST", url),
                )
            return httpx.Response(
                201,
                json={
                    "id": "order-123",
                    "status": "CREATED",
                    "links": [{
                        "rel": "approve",
                        "href": "https://www.sandbox.paypal.com/checkout",
                    }],
                },
                request=httpx.Request("POST", url),
            )

        def get(self, url, *, headers):
            requests.append(("GET", url, headers))
            return httpx.Response(
                200,
                json={
                    "status": "APPROVED",
                    "purchase_units": [{
                        "reference_id": "job-123",
                        "amount": {"currency_code": "USD", "value": "12.50"},
                        "payee": {"merchant_id": "seller-123"},
                    }],
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(paypal_service.httpx, "Client", FakeClient)

    order = paypal_service.create_order(
        "job-123",
        12.50,
        "USD",
        bill_items=[{"label": "Build", "billed_amount": 12.50}],
    )
    diagnostic = paypal_service.get_order_diagnostics("order-123", "job-123")
    capture = paypal_service.capture_order("order-123", 12.50, "USD", "job-123")

    assert order["approve_url"] == "https://www.sandbox.paypal.com/checkout"
    assert diagnostic["payee_merchant_id"] == "seller-123"
    assert capture["id"] == "capture-123"
    assert len(requests) == 3
    purchase_unit = order_payloads[0]["purchase_units"][0]
    assert purchase_unit["amount"]["currency_code"] == "USD"
    assert purchase_unit["items"][0]["unit_amount"]["currency_code"] == "USD"
    assert all(
        request[2]["Authorization"] == f"Bearer sandbox-access-token"
        for request in requests
    )


def test_contract_currency_is_usd_only():
    contract_data = {
        "required_sections": ["app"],
        "required_features": ["workflow"],
        "criteria": [],
        "price": 10,
    }

    assert Contract.model_validate(contract_data).currency == "USD"
    with pytest.raises(ValidationError):
        Contract.model_validate({**contract_data, "currency": "EUR"})


@pytest.mark.parametrize("currency", ["EUR", "GBP", "CAD"])
def test_non_usd_paypal_orders_and_captures_are_rejected(currency, monkeypatch):
    monkeypatch.setattr(settings, "paypal_mode", "sandbox")
    monkeypatch.setattr(
        paypal_service,
        "_token",
        lambda: pytest.fail("Non-USD payment must be rejected before API access"),
    )

    with pytest.raises(paypal_service.PayPalError, match="USD billing only"):
        paypal_service.create_order("job-123", 10, currency)
    with pytest.raises(paypal_service.PayPalError, match="USD billing only"):
        paypal_service.capture_order("order-123", 10, currency, "job-123")


def test_unsupported_payee_currency_error_explains_seller_setting():
    response = httpx.Response(
        422,
        json={
            "details": [{
                "issue": "UNSUPPORTED_PAYEE_CURRENCY",
                "description": "The payee does not support this currency.",
            }],
        },
        request=httpx.Request(
            "POST",
            "https://api-m.sandbox.paypal.com/v2/checkout/orders",
        ),
    )

    message = paypal_service._api_error_message(response, "order creation")

    assert "seller account cannot receive this currency" in message
    assert "payment receiving preferences" in message
    assert "create a fresh order" in message
