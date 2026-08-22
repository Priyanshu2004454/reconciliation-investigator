"""
Razorpay service layer.

This is the ONLY module in the codebase allowed to talk to Razorpay's API.
Everything else (routes, reconciliation engine, AI investigator) goes through
these functions, never the SDK directly.

RAZORPAY_KEY_SECRET is read once from settings and never logged, returned,
or passed to the frontend.
"""

import time
import logging
from datetime import datetime
from typing import Optional

import razorpay
from razorpay.errors import (
    BadRequestError,
    ServerError,
    GatewayError,
)

from app.core.config import get_settings
from app.services.exceptions import (
    RazorpayAuthError,
    RazorpayRateLimitError,
    RazorpayTimeoutError,
    RazorpayNotFoundError,
    RazorpayMalformedResponseError,
    RazorpayServiceError,
)

logger = logging.getLogger("razorpay_service")

PAGE_SIZE = 100  # Razorpay's max per page for list endpoints


def _get_client() -> razorpay.Client:
    settings = get_settings()
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise RazorpayAuthError("Razorpay credentials are not configured.")
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    client.set_app_details({"title": "Reconciliation Investigator", "version": "0.1.0"})
    return client


def _handle_sdk_error(exc: Exception, context: str) -> None:
    """Translate razorpay SDK / HTTP-level errors into our own exception types."""
    msg = str(exc)

    if isinstance(exc, BadRequestError):
        if "authentication" in msg.lower() or "key_id" in msg.lower():
            raise RazorpayAuthError(f"{context}: invalid Razorpay credentials") from exc
        if "not found" in msg.lower() or "does not exist" in msg.lower():
            raise RazorpayNotFoundError(f"{context}: resource not found") from exc
        raise RazorpayServiceError(f"{context}: bad request - {msg}") from exc

    if isinstance(exc, (ServerError, GatewayError)):
        raise RazorpayServiceError(f"{context}: Razorpay server error - {msg}") from exc

    if "timeout" in msg.lower() or isinstance(exc, TimeoutError):
        raise RazorpayTimeoutError(f"{context}: request timed out") from exc

    if "rate limit" in msg.lower() or "429" in msg:
        raise RazorpayRateLimitError(f"{context}: rate limited by Razorpay") from exc

    # Unknown error shape — don't swallow it silently
    raise RazorpayServiceError(f"{context}: unexpected error - {msg}") from exc


def _paginate(fetch_page_fn, entity_name: str, max_pages: int = 50) -> list[dict]:
    """
    Generic pagination helper for Razorpay list endpoints, which use
    skip/count style pagination and return {"count": N, "items": [...]}.
    """
    all_items: list[dict] = []
    skip = 0
    pages_fetched = 0

    while pages_fetched < max_pages:
        try:
            page = fetch_page_fn(skip=skip, count=PAGE_SIZE)
        except Exception as exc:  # noqa: BLE001 - re-raised as typed error below
            _handle_sdk_error(exc, context=f"fetching {entity_name} (skip={skip})")
            return all_items  # unreachable, _handle_sdk_error always raises

        if not isinstance(page, dict) or "items" not in page:
            raise RazorpayMalformedResponseError(
                f"Unexpected response shape while fetching {entity_name}: {type(page)}"
            )

        items = page.get("items", [])
        all_items.extend(items)
        pages_fetched += 1

        if len(items) < PAGE_SIZE:
            break
        skip += PAGE_SIZE

    return all_items


# ── Payments ─────────────────────────────────────────────────────────────

def fetch_payments(from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> list[dict]:
    """Fetch all payments, optionally within a unix-timestamp window."""
    client = _get_client()
    params: dict = {}
    if from_ts:
        params["from"] = from_ts
    if to_ts:
        params["to"] = to_ts

    def fetch_page(skip: int, count: int):
        return client.payment.all({**params, "skip": skip, "count": count})

    return _paginate(fetch_page, "payments")


def fetch_payment(payment_id: str) -> dict:
    """Fetch a single payment by Razorpay payment ID."""
    if not payment_id or not payment_id.startswith("pay_"):
        raise ValueError("payment_id must be a valid Razorpay payment ID (starts with 'pay_')")
    client = _get_client()
    try:
        return client.payment.fetch(payment_id)
    except Exception as exc:  # noqa: BLE001
        _handle_sdk_error(exc, context=f"fetching payment {payment_id}")


# ── Orders ───────────────────────────────────────────────────────────────

def fetch_orders(from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> list[dict]:
    client = _get_client()
    params: dict = {}
    if from_ts:
        params["from"] = from_ts
    if to_ts:
        params["to"] = to_ts

    def fetch_page(skip: int, count: int):
        return client.order.all({**params, "skip": skip, "count": count})

    return _paginate(fetch_page, "orders")


def fetch_order(order_id: str) -> dict:
    if not order_id or not order_id.startswith("order_"):
        raise ValueError("order_id must be a valid Razorpay order ID (starts with 'order_')")
    client = _get_client()
    try:
        return client.order.fetch(order_id)
    except Exception as exc:  # noqa: BLE001
        _handle_sdk_error(exc, context=f"fetching order {order_id}")


# ── Settlements ──────────────────────────────────────────────────────────

def fetch_settlements(from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> list[dict]:
    client = _get_client()
    params: dict = {}
    if from_ts:
        params["from"] = from_ts
    if to_ts:
        params["to"] = to_ts

    def fetch_page(skip: int, count: int):
        return client.settlement.all({**params, "skip": skip, "count": count})

    return _paginate(fetch_page, "settlements")


def fetch_settlement(settlement_id: str) -> dict:
    if not settlement_id or not settlement_id.startswith("setl_"):
        raise ValueError("settlement_id must be a valid Razorpay settlement ID (starts with 'setl_')")
    client = _get_client()
    try:
        return client.settlement.fetch(settlement_id)
    except Exception as exc:  # noqa: BLE001
        _handle_sdk_error(exc, context=f"fetching settlement {settlement_id}")


# ── Refunds ──────────────────────────────────────────────────────────────

def fetch_refunds(from_ts: Optional[int] = None, to_ts: Optional[int] = None) -> list[dict]:
    client = _get_client()
    params: dict = {}
    if from_ts:
        params["from"] = from_ts
    if to_ts:
        params["to"] = to_ts

    def fetch_page(skip: int, count: int):
        return client.refund.all({**params, "skip": skip, "count": count})

    return _paginate(fetch_page, "refunds")


def fetch_payment_refunds(payment_id: str) -> list[dict]:
    """Refunds issued against a specific payment."""
    if not payment_id or not payment_id.startswith("pay_"):
        raise ValueError("payment_id must be a valid Razorpay payment ID (starts with 'pay_')")
    client = _get_client()

    def fetch_page(skip: int, count: int):
        return client.payment.refunds(payment_id, {"skip": skip, "count": count})

    return _paginate(fetch_page, f"refunds for payment {payment_id}")


# ── Retry wrapper (used for flaky network conditions) ──────────────────

def with_retries(fn, *args, max_attempts: int = 3, backoff_seconds: float = 1.5, **kwargs):
    """
    Wraps a service call with exponential backoff. Only retries on transient
    errors (timeout, rate limit, server error) — never on auth or not-found,
    since retrying those just wastes time and hides the real problem.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except (RazorpayTimeoutError, RazorpayRateLimitError) as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            wait = backoff_seconds * (2 ** (attempt - 1))
            logger.warning("Transient Razorpay error (attempt %d/%d): %s. Retrying in %.1fs",
                            attempt, max_attempts, exc, wait)
            time.sleep(wait)
        except RazorpayServiceError:
            raise  # non-transient — don't retry (auth error, not found, malformed response)

    raise last_exc  # type: ignore[misc]
