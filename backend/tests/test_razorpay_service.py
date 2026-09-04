from unittest.mock import patch, MagicMock

import pytest

from app.services import razorpay_service
from app.services.exceptions import RazorpayAuthError


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_dummy")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "dummy_secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("APP_SECRET_KEY", "x")
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "x")
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _page(items, total=None):
    return {"entity": "collection", "count": total or len(items), "items": items}


def test_fetch_payments_paginates_across_pages():
    page_1_items = [{"id": f"pay_{i}"} for i in range(razorpay_service.PAGE_SIZE)]
    page_2_items = [{"id": "pay_last"}]

    mock_client = MagicMock()
    mock_client.payment.all.side_effect = [_page(page_1_items), _page(page_2_items)]

    with patch.object(razorpay_service, "_get_client", return_value=mock_client):
        result = razorpay_service.fetch_payments()

    assert len(result) == razorpay_service.PAGE_SIZE + 1
    assert mock_client.payment.all.call_count == 2


def test_fetch_payment_validates_id_format():
    with pytest.raises(ValueError):
        razorpay_service.fetch_payment("not-a-real-id")


def test_missing_credentials_raise_auth_error(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
    from app.core.config import get_settings
    get_settings.cache_clear()

    with pytest.raises(RazorpayAuthError):
        razorpay_service.fetch_payments()


def test_malformed_response_is_caught():
    mock_client = MagicMock()
    mock_client.payment.all.return_value = {"unexpected": "shape"}  # no "items" key

    with patch.object(razorpay_service, "_get_client", return_value=mock_client):
        with pytest.raises(Exception) as exc_info:
            razorpay_service.fetch_payments()

    assert "Unexpected response shape" in str(exc_info.value)
