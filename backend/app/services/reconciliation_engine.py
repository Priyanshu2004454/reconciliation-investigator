"""
Deterministic reconciliation engine (section 8 of the spec).

Pure, deterministic, rule-based matching. NO AI is used here — the AI
Investigator only ever looks at cases this engine could not confidently
resolve (NEEDS_REVIEW), and it never overrides what this engine decides.

Rule priority (checked in this exact order, first match wins):
  1. Exact UTR match (settlement UTR == bank row UTR)
  2. Exact reference/transaction ID match
  3. Amount + date-window match (candidate match)
  4. Settlement adjustment — fee/tax explains the payment-vs-settlement gap
  5. Refund adjustment — a refund explains the gap
  6. Unmatched -> NEEDS_REVIEW

A configurable amount tolerance (paise-level rounding) and date window are
read from settings so they aren't magic numbers buried in the engine.
"""

from datetime import date, timedelta

from app.core.config import get_settings
from app.schemas.reconciliation_engine import (
    BankRowInput,
    CaseResult,
    PaymentInput,
    ReconciliationInput,
    ReconciliationOutput,
    RefundInput,
    SettlementInput,
)


def _amounts_match(a: float, b: float, tolerance_paise: int) -> bool:
    return abs(round((a - b) * 100)) <= tolerance_paise


def _within_date_window(d1: date, d2: date, window_days: int) -> bool:
    return abs((d1 - d2).days) <= window_days


def _find_utr_match(settlement: SettlementInput, bank_rows: list[BankRowInput], used: set[str]) -> list[BankRowInput]:
    if not settlement.utr:
        return []
    return [b for b in bank_rows if b.id not in used and b.utr and b.utr == settlement.utr]


def _find_reference_match(settlement: SettlementInput, bank_rows: list[BankRowInput], used: set[str]) -> list[BankRowInput]:
    return [
        b for b in bank_rows
        if b.id not in used and b.reference_id and b.reference_id == settlement.razorpay_settlement_id
    ]


def _find_amount_date_match(
    settlement: SettlementInput, bank_rows: list[BankRowInput], used: set[str],
    tolerance_paise: int, window_days: int,
) -> list[BankRowInput]:
    candidates = []
    for b in bank_rows:
        if b.id in used or b.credit is None:
            continue
        if _amounts_match(b.credit, settlement.amount, tolerance_paise) and _within_date_window(
            b.transaction_date, settlement.settlement_date, window_days
        ):
            candidates.append(b)
    return candidates


def _calculate_expected_settlement(
    linked_payments: list[PaymentInput], linked_refunds: list[RefundInput]
) -> float:
    """Rule 4/5 helper: gross payments minus fees, tax, and any refunds."""
    gross = sum(p.amount for p in linked_payments)
    fees = sum(p.fee for p in linked_payments)
    tax = sum(p.tax for p in linked_payments)
    refunded = sum(r.amount for r in linked_refunds)
    return round(gross - fees - tax - refunded, 2)


def calculate_expected_settlement(case_payments: list[PaymentInput], case_refunds: list[RefundInput]) -> float:
    """Public entry point — also used as an AI tool in the investigator (section 12)."""
    return _calculate_expected_settlement(case_payments, case_refunds)


def reconcile(data: ReconciliationInput) -> ReconciliationOutput:
    settings = get_settings()
    tolerance_paise = settings.MATCH_AMOUNT_TOLERANCE_PAISE
    window_days = settings.MATCH_DATE_WINDOW_DAYS

    payments_by_id = {p.razorpay_payment_id: p for p in data.payments}
    refunds_by_payment: dict[str, list[RefundInput]] = {}
    for r in data.refunds:
        refunds_by_payment.setdefault(r.razorpay_payment_id, []).append(r)

    used_bank_row_ids: set[str] = set()
    cases: list[CaseResult] = []

    for settlement in data.settlements:
        linked_payments = [payments_by_id[pid] for pid in settlement.payment_ids if pid in payments_by_id]
        linked_refunds = [
            r for pid in settlement.payment_ids for r in refunds_by_payment.get(pid, [])
        ]

        case = _reconcile_settlement(
            settlement, data.bank_rows, used_bank_row_ids, linked_payments, linked_refunds,
            tolerance_paise, window_days,
        )
        cases.append(case)

    matched = sum(1 for c in cases if c.status == "MATCHED")
    explained = sum(1 for c in cases if c.status == "EXPLAINED")
    needs_review = sum(1 for c in cases if c.status == "NEEDS_REVIEW")

    return ReconciliationOutput(
        total_cases=len(cases), matched=matched, explained=explained,
        needs_review=needs_review, cases=cases,
    )


def _reconcile_settlement(
    settlement: SettlementInput,
    bank_rows: list[BankRowInput],
    used_bank_row_ids: set[str],
    linked_payments: list[PaymentInput],
    linked_refunds: list[RefundInput],
    tolerance_paise: int,
    window_days: int,
) -> CaseResult:
    base = dict(razorpay_settlement_id=settlement.razorpay_settlement_id, actual_amount=settlement.amount)

    # ── Rule 1: exact UTR match ──────────────────────────────────────
    utr_matches = _find_utr_match(settlement, bank_rows, used_bank_row_ids)
    if len(utr_matches) > 1:
        # Same UTR appears more than once in the bank statement — Case 5 (Duplicate)
        return CaseResult(
            **base, status="NEEDS_REVIEW", match_rule="RULE_1_UTR_DUPLICATE",
            root_cause="DUPLICATE",
            notes=f"UTR '{settlement.utr}' matches {len(utr_matches)} bank rows — ambiguous, needs human review.",
        )
    if len(utr_matches) == 1:
        bank_row = utr_matches[0]
        used_bank_row_ids.add(bank_row.id)
        return _finalize_bank_match(base, bank_row, settlement, linked_payments, linked_refunds, "RULE_1_UTR_MATCH", window_days)

    # ── Rule 2: exact reference/transaction ID match ─────────────────
    ref_matches = _find_reference_match(settlement, bank_rows, used_bank_row_ids)
    if len(ref_matches) == 1:
        bank_row = ref_matches[0]
        used_bank_row_ids.add(bank_row.id)
        return _finalize_bank_match(base, bank_row, settlement, linked_payments, linked_refunds, "RULE_2_REFERENCE_MATCH", window_days)

    # ── Rule 3: amount + date window (candidate match) ────────────────
    amount_date_matches = _find_amount_date_match(settlement, bank_rows, used_bank_row_ids, tolerance_paise, window_days)
    if len(amount_date_matches) == 1:
        bank_row = amount_date_matches[0]
        used_bank_row_ids.add(bank_row.id)
        return CaseResult(
            **base, bank_transaction_id=bank_row.id,
            expected_amount=settlement.amount, difference=round(bank_row.credit - settlement.amount, 2),
            status="MATCHED", match_rule="RULE_3_AMOUNT_DATE_CANDIDATE",
            notes="No UTR/reference on either side, but amount and date align within the configured window.",
        )
    if len(amount_date_matches) > 1:
        return CaseResult(
            **base, status="NEEDS_REVIEW", match_rule="RULE_3_AMBIGUOUS",
            root_cause="DUPLICATE",
            notes=f"{len(amount_date_matches)} bank rows match on amount+date window — cannot pick one without a stronger signal.",
        )

    # ── Rules 4 & 5: no bank match at all — see if fee/tax/refund explains it ──
    if linked_payments:
        expected = _calculate_expected_settlement(linked_payments, linked_refunds)
        if _amounts_match(expected, settlement.amount, tolerance_paise):
            root_cause = "REFUND" if linked_refunds else "FEE_TAX"
            rule = "RULE_5_REFUND_ADJUSTMENT" if linked_refunds else "RULE_4_FEE_TAX_ADJUSTMENT"
            return CaseResult(
                **base, expected_amount=expected, difference=round(settlement.amount - expected, 2),
                status="EXPLAINED", match_rule=rule, root_cause=root_cause,
                notes="No bank credit found yet, but the settlement amount is fully explained by "
                      f"linked payment(s) minus fees/tax{'/refunds' if linked_refunds else ''}. "
                      "Still needs a bank-side match before it can be marked resolved.",
            )

    # ── Rule 6: no reliable explanation ────────────────────────────────
    return CaseResult(
        **base, status="NEEDS_REVIEW", match_rule="RULE_6_UNMATCHED",
        root_cause="MISSING_BANK_CREDIT",
        notes="No UTR match, no reference match, no amount+date candidate, and no fee/tax/refund "
              "explanation. Settlement cannot currently be reconciled against the bank statement.",
    )


def _finalize_bank_match(
    base: dict, bank_row: BankRowInput, settlement: SettlementInput,
    linked_payments: list[PaymentInput], linked_refunds: list[RefundInput],
    rule: str, window_days: int,
) -> CaseResult:
    """
    A bank row was matched via UTR or reference (high confidence on identity).
    Now check whether the *amount* also lines up, or a fee/tax/refund/timing
    difference explains a gap.
    """
    bank_amount = bank_row.credit or 0.0
    diff = round(bank_amount - settlement.amount, 2)

    if abs(diff) < 0.01:
        # Amounts match exactly. Check for a timing difference (Case 6) — bank
        # credit posted on a different date than the settlement was processed.
        if bank_row.transaction_date != settlement.settlement_date and _within_date_window(
            bank_row.transaction_date, settlement.settlement_date, window_days
        ):
            return CaseResult(
                **base, bank_transaction_id=bank_row.id, expected_amount=settlement.amount,
                difference=0.0, status="EXPLAINED", match_rule=rule, root_cause="TIMING_DIFFERENCE",
                notes=f"Settlement processed {settlement.settlement_date}, bank credit posted "
                      f"{bank_row.transaction_date} — amount matches exactly, timing differs.",
            )
        return CaseResult(
            **base, bank_transaction_id=bank_row.id, expected_amount=settlement.amount,
            difference=0.0, status="MATCHED", match_rule=rule,
        )

    # Amounts differ — see if payments/fees/tax/refunds explain the gap
    if linked_payments:
        expected = _calculate_expected_settlement(linked_payments, linked_refunds)
        if _amounts_match(expected, bank_amount, 100):
            root_cause = "REFUND" if linked_refunds else "FEE_TAX"
            return CaseResult(
                **{**base, "actual_amount": bank_amount},
                bank_transaction_id=bank_row.id, expected_amount=expected,
                difference=round(bank_amount - expected, 2),
                status="EXPLAINED", match_rule=rule, root_cause=root_cause,
                notes="Bank amount differs from settlement amount, but matches the expected value "
                      "after accounting for fees/tax" + ("/refunds." if linked_refunds else "."),
            )

    return CaseResult(
        **{**base, "actual_amount": bank_amount},
        bank_transaction_id=bank_row.id, expected_amount=settlement.amount,
        difference=diff,
        status="NEEDS_REVIEW", match_rule=rule, root_cause="AMOUNT_MISMATCH",
        notes=f"Bank row identity matched ({rule}) but amount differs by {diff} with no fee/tax/refund "
              "explanation available.",
    )
