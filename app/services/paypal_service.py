import secrets
from decimal import Decimal

import httpx

from app.core.config import settings


class PayPalError(RuntimeError):
    """Raised when PayPal cannot create or verify a payment."""


def _is_mock() -> bool:
    return settings.paypal_mode.lower() in {"mock", "demo", ""}


def _token() -> str:
    if not settings.paypal_client_id or not settings.paypal_client_secret:
        raise PayPalError("PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are required for Sandbox mode")
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{settings.paypal_api_base_url.rstrip('/')}/v1/oauth2/token",
                auth=(settings.paypal_client_id, settings.paypal_client_secret),
                headers={"Accept": "application/json", "Accept-Language": "en_US"},
                data={"grant_type": "client_credentials"},
            )
            response.raise_for_status()
            return response.json()["access_token"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise PayPalError(f"PayPal authentication failed: {exc}") from exc


def create_order(job_id: str, amount: float, currency: str, request_id: str | None = None) -> dict:
    if _is_mock():
        return {
            "id": f"MOCK-{job_id[:8]}-{secrets.token_hex(4).upper()}",
            "status": "CREATED",
            "amount": f"{amount:.2f}",
            "currency": currency,
            "mode": "mock",
        }

    token = _token()
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": job_id,
            "custom_id": job_id,
            "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
        }],
        "application_context": {
            "brand_name": settings.app_name,
            "user_action": "PAY_NOW",
            "return_url": settings.paypal_return_url,
            "cancel_url": settings.paypal_cancel_url,
        },
    }
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{settings.paypal_api_base_url.rstrip('/')}/v2/checkout/orders",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "PayPal-Request-Id": request_id or f"job-{job_id}-order-v1"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            approve_url = next((link["href"] for link in data.get("links", []) if link.get("rel") == "approve"), None)
            if not approve_url:
                raise PayPalError("PayPal did not return an approval URL")
            return {
                "id": data["id"],
                "status": data["status"],
                "amount": f"{amount:.2f}",
                "currency": currency,
                "mode": "sandbox",
                "approve_url": approve_url,
            }
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise PayPalError(f"PayPal order creation failed: {exc}") from exc


def capture_order(order_id: str, expected_amount: float, expected_currency: str, job_id: str, request_id: str | None = None) -> dict:
    if _is_mock():
        return {"id": f"CAPTURE-{order_id[-8:]}", "order_id": order_id, "status": "COMPLETED"}

    token = _token()
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{settings.paypal_api_base_url.rstrip('/')}/v2/checkout/orders/{order_id}/capture",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "PayPal-Request-Id": request_id or f"job-{job_id}-capture-v1"},
                json={},
            )
            response.raise_for_status()
            data = response.json()
            purchase_unit = next(
                (unit for unit in data.get("purchase_units", []) if unit.get("reference_id") == job_id or unit.get("custom_id") == job_id),
                None,
            )
            capture = (purchase_unit or {}).get("payments", {}).get("captures", [{}])[0]
            amount = capture.get("amount", {})
            if (
                data.get("status") != "COMPLETED"
                or capture.get("status") != "COMPLETED"
                or purchase_unit is None
                or amount.get("currency_code") != expected_currency
                or Decimal(str(amount.get("value", "0"))) != Decimal(f"{expected_amount:.2f}")
            ):
                raise PayPalError("PayPal capture failed amount, currency, job, or status verification")
            return {"id": capture["id"], "order_id": order_id, "status": "COMPLETED"}
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise PayPalError(f"PayPal capture failed: {exc}") from exc
