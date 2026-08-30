import hashlib
import hmac

import pytest

from app.services.webhook_service import verify_signature, _derive_event_id


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_123")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("APP_SECRET_KEY", "x")
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    body = b'{"event": "payment.captured"}'
    sig = _sign(body, "test_webhook_secret_123")
    assert verify_signature(body, sig) is True


def test_invalid_signature_rejected():
    body = b'{"event": "payment.captured"}'
    wrong_sig = _sign(body, "wrong_secret")
    assert verify_signature(body, wrong_sig) is False


def test_tampered_body_rejected():
    """Signature was computed for one body, but a different body is presented — must fail."""
    original_body = b'{"event": "payment.captured", "amount": 10000}'
    sig = _sign(original_body, "test_webhook_secret_123")
    tampered_body = b'{"event": "payment.captured", "amount": 999999}'
    assert verify_signature(tampered_body, sig) is False


def test_missing_signature_rejected():
    body = b'{"event": "payment.captured"}'
    assert verify_signature(body, "") is False


def test_derive_event_id_uses_explicit_id_when_present():
    payload = {"id": "evt_ABC123", "event": "payment.captured"}
    assert _derive_event_id(payload, b"whatever") == "evt_ABC123"


def test_derive_event_id_falls_back_to_content_hash():
    payload = {"event": "payment.captured"}  # no "id" field
    body = b'{"event": "payment.captured"}'
    event_id = _derive_event_id(payload, body)
    assert event_id == hashlib.sha256(body).hexdigest()


def test_derive_event_id_stable_for_identical_redelivery():
    """Same webhook redelivered (Razorpay retry) with no explicit id -> same derived id -> idempotency works."""
    payload = {"event": "settlement.processed"}
    body = b'{"event": "settlement.processed", "data": "same every time"}'
    assert _derive_event_id(payload, body) == _derive_event_id(payload, body)
