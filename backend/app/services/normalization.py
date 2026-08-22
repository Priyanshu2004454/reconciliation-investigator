"""
Converts raw Razorpay API objects into the internal NormalizedRecord shape
defined in app.schemas.financial. The reconciliation engine only ever touches
normalized records — never raw Razorpay dicts — so it stays agnostic to
whatever Razorpay's API happens to name a field this year.
"""

from datetime import datetime, timezone

from app.schemas.financial import NormalizedRecord


def _paise_to_rupees(amount_paise: int | None) -> float:
    """Razorpay amounts are in paise (smallest currency unit). Convert to rupees."""
    if amount_paise is None:
        return 0.0
    return round(amount_paise / 100, 2)


def _unix_to_datetime(ts: int | None) -> datetime:
    if ts is None:
        raise ValueError("Missing timestamp in Razorpay record — cannot normalize.")
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def normalize_payment(raw: dict) -> NormalizedRecord:
    return NormalizedRecord(
        source="RAZORPAY_PAYMENT",
        external_id=raw["id"],
        amount=_paise_to_rupees(raw.get("amount")),
        currency=raw.get("currency", "INR"),
        date=_unix_to_datetime(raw.get("created_at")),
        reference_id=raw.get("order_id"),
        utr=None,  # payments don't carry a UTR — settlements do
        status=raw.get("status", "unknown"),
        metadata={
            "method": raw.get("method"),
            "fee": _paise_to_rupees(raw.get("fee")),
            "tax": _paise_to_rupees(raw.get("tax")),
            "order_id": raw.get("order_id"),
            "captured": raw.get("captured"),
        },
    )


def normalize_order(raw: dict) -> NormalizedRecord:
    return NormalizedRecord(
        source="RAZORPAY_ORDER",
        external_id=raw["id"],
        amount=_paise_to_rupees(raw.get("amount")),
        currency=raw.get("currency", "INR"),
        date=_unix_to_datetime(raw.get("created_at")),
        reference_id=raw.get("receipt"),
        utr=None,
        status=raw.get("status", "unknown"),
        metadata={"receipt": raw.get("receipt")},
    )


def normalize_refund(raw: dict) -> NormalizedRecord:
    return NormalizedRecord(
        source="RAZORPAY_REFUND",
        external_id=raw["id"],
        amount=_paise_to_rupees(raw.get("amount")),
        currency=raw.get("currency", "INR"),
        date=_unix_to_datetime(raw.get("created_at")),
        reference_id=raw.get("payment_id"),
        utr=None,
        status=raw.get("status", "unknown"),
        metadata={"payment_id": raw.get("payment_id"), "speed_processed": raw.get("speed_processed")},
    )


def normalize_settlement(raw: dict) -> NormalizedRecord:
    return NormalizedRecord(
        source="RAZORPAY_SETTLEMENT",
        external_id=raw["id"],
        amount=_paise_to_rupees(raw.get("amount")),
        currency="INR",
        date=_unix_to_datetime(raw.get("created_at")),
        reference_id=raw.get("id"),
        utr=raw.get("utr"),
        status=raw.get("status", "unknown"),
        metadata={
            "fees": _paise_to_rupees(raw.get("fees")),
            "tax": _paise_to_rupees(raw.get("tax")),
        },
    )


def normalize_bank_row(row: dict) -> NormalizedRecord:
    """
    `row` here is already the *cleaned* internal dict produced by the CSV
    normalization layer (app.services.bank_statement_parser), i.e. it already
    has keys: transaction_date, description, reference_id, utr, credit, debit, balance.
    """
    credit = row.get("credit") or 0.0
    debit = row.get("debit") or 0.0
    amount = credit if credit else -debit

    return NormalizedRecord(
        source="BANK_STATEMENT",
        external_id=row.get("reference_id") or row.get("utr") or f"bank-{row.get('row_hash', '')[:12]}",
        amount=amount,
        currency="INR",
        date=row["transaction_date"] if isinstance(row["transaction_date"], datetime)
        else datetime.combine(row["transaction_date"], datetime.min.time()),
        reference_id=row.get("reference_id"),
        utr=row.get("utr"),
        status="credit" if credit else "debit",
        metadata={"description": row.get("description"), "balance": row.get("balance")},
    )
