import secrets
from decimal import Decimal, ROUND_HALF_UP

import httpx

from app.core.config import settings


class PayPalError(RuntimeError):
    """Raised when PayPal cannot create or verify a payment."""


PAYPAL_CURRENCY = "USD"


def _normalize_currency(currency: str | None) -> str:
    """Enforce the application's single supported billing currency."""
    normalized = (currency or PAYPAL_CURRENCY).upper().strip()
    if normalized != PAYPAL_CURRENCY:
        raise PayPalError("This application supports USD billing only. Create a new USD order.")
    return PAYPAL_CURRENCY


def _api_error_message(response: httpx.Response, operation: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    details = payload.get("details") or []
    if not isinstance(details, list):
        details = []
    details = [item for item in details if isinstance(item, dict)]
    issue = next((item.get("issue") for item in details if item.get("issue")), None)
    description = next(
        (item.get("description") for item in details if item.get("description")),
        payload.get("message"),
    )
    debug_id = payload.get("debug_id")
    if issue == "UNSUPPORTED_PAYEE_CURRENCY":
        return (
            "The PayPal seller account cannot receive this currency. The accepted currency is "
            "controlled by the merchant account, so enable this currency or allow PayPal to "
            "convert it in the Sandbox Business account’s payment receiving preferences, then "
            "cancel this attempt and create a fresh order."
        )
    if operation == "capture" and issue == "ORDER_NOT_APPROVED":
        return (
            "PayPal has not approved this order, so no payment was captured. "
            "If checkout said the seller does not accept this currency, enable it or allow "
            "PayPal to convert it in the Sandbox Business account’s payment receiving "
            "preferences, cancel this attempt, and create a fresh order."
        )
    message = f"PayPal {operation} request failed ({response.status_code})"
    if issue:
        message += f" · {issue}"
    if description:
        message += f": {description}"
    if debug_id:
        message += f" (PayPal debug ID: {debug_id})"
    return message


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


def create_order(
    job_id: str,
    amount: float,
    currency: str,
    request_id: str | None = None,
    bill_items: list[dict] | None = None,
) -> dict:
    currency = _normalize_currency(currency)
    if _is_mock():
        return {
            "id": f"MOCK-{job_id[:8]}-{secrets.token_hex(4).upper()}",
            "status": "CREATED",
            "amount": f"{amount:.2f}",
            "currency": currency,
            "mode": "mock",
        }

    token = _token()
    purchase_unit = {
        "reference_id": job_id,
        "custom_id": job_id,
        "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
    }
    paypal_items = []
    for item in bill_items or []:
        line_amount = Decimal(str(item.get("billed_amount", 0))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if line_amount <= 0:
            continue
        name = str(item.get("label") or "Acceptance check")
        clean_name = name.encode("ascii", "ignore").decode("ascii").strip() or "Acceptance check"
        paypal_item = {
            "name": clean_name[:127],
            "quantity": "1",
            "unit_amount": {"currency_code": currency, "value": f"{line_amount:.2f}"},
            "category": "DIGITAL_GOODS",
        }
        description = str(item.get("detail") or "").strip()
        clean_desc = description.encode("ascii", "ignore").decode("ascii").strip()
        if clean_desc:
            paypal_item["description"] = clean_desc[:127]
        paypal_items.append(paypal_item)
    if paypal_items:
        item_total = sum(
            (Decimal(item["unit_amount"]["value"]) for item in paypal_items),
            start=Decimal("0.00"),
        )
        expected_total = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if item_total != expected_total:
            raise PayPalError("The itemized bill does not match the PayPal order total")
        purchase_unit["items"] = paypal_items
        purchase_unit["amount"]["breakdown"] = {
            "item_total": {"currency_code": currency, "value": f"{item_total:.2f}"}
        }
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [purchase_unit],
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
    except httpx.HTTPStatusError as exc:
        raise PayPalError(_api_error_message(exc.response, "order creation")) from exc
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise PayPalError(f"PayPal order creation failed: {exc}") from exc


def get_order_diagnostics(order_id: str, job_id: str) -> dict:
    """Return only the seller/currency fields needed to diagnose a checkout.

    PayPal's order response contains buyer and shipping data too, so never pass
    the complete response back to the browser.
    """
    if _is_mock():
        return {"mode": "mock", "status": "UNKNOWN", "currency": None, "amount": None, "payee_merchant_id": None}

    token = _token()
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{settings.paypal_api_base_url.rstrip('/')}/v2/checkout/orders/{order_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            purchase_unit = next(
                (
                    unit for unit in data.get("purchase_units", [])
                    if unit.get("reference_id") == job_id or unit.get("custom_id") == job_id
                ),
                None,
            )
            if purchase_unit is None:
                raise PayPalError("PayPal order does not match this job")
            amount = purchase_unit.get("amount") or {}
            payee = purchase_unit.get("payee") or {}
            return {
                "mode": "sandbox",
                "status": data.get("status"),
                "currency": amount.get("currency_code"),
                "amount": amount.get("value"),
                "payee_merchant_id": payee.get("merchant_id"),
            }
    except httpx.HTTPStatusError as exc:
        raise PayPalError(_api_error_message(exc.response, "order lookup")) from exc
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise PayPalError(f"PayPal order lookup failed: {exc}") from exc


def capture_order(order_id: str, expected_amount: float, expected_currency: str, job_id: str, request_id: str | None = None) -> dict:
    expected_currency = _normalize_currency(expected_currency)
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
    except httpx.HTTPStatusError as exc:
        raise PayPalError(_api_error_message(exc.response, "capture")) from exc
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise PayPalError(f"PayPal capture failed: {exc}") from exc
