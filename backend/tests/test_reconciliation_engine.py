from datetime import date

import pytest

from app.services.reconciliation_engine import reconcile
from app.schemas.reconciliation_engine import (
    BankRowInput, PaymentInput, RefundInput, SettlementInput, ReconciliationInput,
)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MATCH_AMOUNT_TOLERANCE_PAISE", "100")
    monkeypatch.setenv("MATCH_DATE_WINDOW_DAYS", "3")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "x")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("APP_SECRET_KEY", "x")
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_case_1_perfect_match():
    """Payment 10,000 / Settlement 10,000 / Bank 10,000 -> MATCHED"""
    data = ReconciliationInput(
        payments=[PaymentInput(razorpay_payment_id="pay_1", amount=10000, fee=0, tax=0)],
        settlements=[SettlementInput(
            razorpay_settlement_id="setl_1", utr="UTR001", amount=10000,
            settlement_date=date(2026, 6, 1), payment_ids=["pay_1"],
        )],
        bank_rows=[BankRowInput(id="bank_1", transaction_date=date(2026, 6, 1), utr="UTR001", credit=10000)],
    )
    result = reconcile(data)
    assert result.cases[0].status == "MATCHED"
    assert result.cases[0].match_rule == "RULE_1_UTR_MATCH"


def test_case_2_fee_and_tax_explained():
    """Payment 10,000, Fee 180, Tax 32.40 -> Expected settlement 9787.60 -> Bank 9787.60 -> EXPLAINED"""
    data = ReconciliationInput(
        payments=[PaymentInput(razorpay_payment_id="pay_2", amount=10000, fee=180, tax=32.40)],
        settlements=[SettlementInput(
            razorpay_settlement_id="setl_2", utr="UTR002", amount=9787.60,
            settlement_date=date(2026, 6, 1), payment_ids=["pay_2"],
        )],
        bank_rows=[BankRowInput(id="bank_2", transaction_date=date(2026, 6, 1), utr="UTR002", credit=9787.60)],
    )
    result = reconcile(data)
    case = result.cases[0]
    # Settlement amount == bank amount exactly, so this resolves as a clean MATCHED
    # (the fee/tax math is what PRODUCED the settlement amount in the first place).
    assert case.status == "MATCHED"
    assert case.bank_transaction_id == "bank_2"


def test_case_2b_settlement_still_shows_gross_but_bank_shows_net():
    """
    A more realistic version of Case 2: the settlement record itself hasn't been
    fully adjusted, but the *bank* shows the fee/tax-adjusted net amount -> EXPLAINED.
    """
    data = ReconciliationInput(
        payments=[PaymentInput(razorpay_payment_id="pay_2b", amount=10000, fee=180, tax=32.40)],
        settlements=[SettlementInput(
            razorpay_settlement_id="setl_2b", utr="UTR002B", amount=10000,  # gross, not yet netted
            settlement_date=date(2026, 6, 1), payment_ids=["pay_2b"],
        )],
        bank_rows=[BankRowInput(id="bank_2b", transaction_date=date(2026, 6, 1), utr="UTR002B", credit=9787.60)],
    )
    result = reconcile(data)
    case = result.cases[0]
    assert case.status == "EXPLAINED"
    assert case.root_cause == "FEE_TAX"


def test_case_3_refund_explained():
    """Payment 5,000, Refund 5,000 -> bank shows 0 net -> EXPLAINED via refund"""
    data = ReconciliationInput(
        payments=[PaymentInput(razorpay_payment_id="pay_3", amount=5000, fee=0, tax=0)],
        refunds=[RefundInput(razorpay_refund_id="rfnd_3", razorpay_payment_id="pay_3", amount=5000)],
        settlements=[SettlementInput(
            razorpay_settlement_id="setl_3", utr="UTR003", amount=5000,  # settlement not yet adjusted
            settlement_date=date(2026, 6, 1), payment_ids=["pay_3"],
        )],
        bank_rows=[BankRowInput(id="bank_3", transaction_date=date(2026, 6, 1), utr="UTR003", credit=0.0)],
    )
    result = reconcile(data)
    case = result.cases[0]
    assert case.status == "EXPLAINED"
    assert case.root_cause == "REFUND"


def test_case_4_missing_bank_credit():
    """Settlement 25,000, UTR ABC123, no bank transaction at all -> NEEDS_REVIEW"""
    data = ReconciliationInput(
        settlements=[SettlementInput(
            razorpay_settlement_id="setl_4", utr="ABC123", amount=25000,
            settlement_date=date(2026, 8, 22),
        )],
        bank_rows=[],
    )
    result = reconcile(data)
    case = result.cases[0]
    assert case.status == "NEEDS_REVIEW"
    assert case.root_cause == "MISSING_BANK_CREDIT"
    assert case.match_rule == "RULE_6_UNMATCHED"


def test_case_5_duplicate_bank_entry():
    """Same UTR appears twice in bank statement -> NEEDS_REVIEW (ambiguous)"""
    data = ReconciliationInput(
        settlements=[SettlementInput(
            razorpay_settlement_id="setl_5", utr="UTR005", amount=8000,
            settlement_date=date(2026, 6, 1),
        )],
        bank_rows=[
            BankRowInput(id="bank_5a", transaction_date=date(2026, 6, 1), utr="UTR005", credit=8000),
            BankRowInput(id="bank_5b", transaction_date=date(2026, 6, 1), utr="UTR005", credit=8000),
        ],
    )
    result = reconcile(data)
    case = result.cases[0]
    assert case.status == "NEEDS_REVIEW"
    assert case.root_cause == "DUPLICATE"


def test_case_6_timing_difference():
    """Settlement processed on one date, bank credit posted a couple of days later -> EXPLAINED"""
    data = ReconciliationInput(
        settlements=[SettlementInput(
            razorpay_settlement_id="setl_6", utr="UTR006", amount=15000,
            settlement_date=date(2026, 6, 1),
        )],
        bank_rows=[BankRowInput(id="bank_6", transaction_date=date(2026, 6, 3), utr="UTR006", credit=15000)],
    )
    result = reconcile(data)
    case = result.cases[0]
    assert case.status == "EXPLAINED"
    assert case.root_cause == "TIMING_DIFFERENCE"


def test_amount_date_candidate_match_rule_3():
    """No UTR/reference on either side, but amount + date align -> MATCHED via Rule 3."""
    data = ReconciliationInput(
        settlements=[SettlementInput(
            razorpay_settlement_id="setl_7", amount=4200, settlement_date=date(2026, 6, 5),
        )],
        bank_rows=[BankRowInput(id="bank_7", transaction_date=date(2026, 6, 6), credit=4200)],
    )
    result = reconcile(data)
    case = result.cases[0]
    assert case.status == "MATCHED"
    assert case.match_rule == "RULE_3_AMOUNT_DATE_CANDIDATE"


def test_never_forces_a_match_when_nothing_lines_up():
    """Genuinely unexplainable case -> NEEDS_REVIEW, never a fabricated match."""
    data = ReconciliationInput(
        settlements=[SettlementInput(
            razorpay_settlement_id="setl_8", utr="NOMATCH", amount=999999,
            settlement_date=date(2026, 1, 1),
        )],
        bank_rows=[BankRowInput(id="bank_8", transaction_date=date(2026, 6, 1), utr="OTHERUTR", credit=1)],
    )
    result = reconcile(data)
    assert result.cases[0].status == "NEEDS_REVIEW"


def test_bank_row_not_reused_across_two_settlements():
    """A single bank row, once matched, can't be double-counted for a second settlement."""
    data = ReconciliationInput(
        settlements=[
            SettlementInput(razorpay_settlement_id="setl_9a", utr="SHARED", amount=1000, settlement_date=date(2026, 6, 1)),
            SettlementInput(razorpay_settlement_id="setl_9b", amount=1000, settlement_date=date(2026, 6, 1)),
        ],
        bank_rows=[BankRowInput(id="bank_9", transaction_date=date(2026, 6, 1), utr="SHARED", credit=1000)],
    )
    result = reconcile(data)
    assert result.cases[0].status == "MATCHED"
    assert result.cases[1].status == "NEEDS_REVIEW"  # bank row already consumed by case 1
