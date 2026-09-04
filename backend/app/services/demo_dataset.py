import random
from datetime import date, timedelta

from app.schemas.reconciliation_engine import (
    BankRowInput, PaymentInput, RefundInput, SettlementInput, ReconciliationInput,
)

SEED = 42
BASE_DATE = date(2026, 7, 1)

CATEGORY_TARGET_COUNTS = {
    "MATCHED": 40,
    "FEE_TAX": 15,
    "REFUND": 10,
    "TIMING_DIFFERENCE": 10,
    "MISSING_BANK_CREDIT": 10,
    "DUPLICATE": 5,
    "AMOUNT_MISMATCH": 10,
}  # sums to 100


def generate_dataset(seed: int = SEED, prefix: str = "") -> tuple[ReconciliationInput, dict[str, str]]:
    rng = random.Random(seed)
    pfx = f"{prefix}_" if prefix and not prefix.endswith("_") else prefix

    payments: list[PaymentInput] = []
    settlements: list[SettlementInput] = []
    refunds: list[RefundInput] = []
    bank_rows: list[BankRowInput] = []
    ground_truth: dict[str, str] = {}

    idx = 0

    def next_amount() -> float:
        return round(rng.uniform(500, 50000), 2)

    def fee_tax_for(amount: float) -> tuple[float, float]:
        fee = round(amount * 0.02, 2)  
        tax = round(fee * 0.18, 2) 
        return fee, tax

    for _ in range(CATEGORY_TARGET_COUNTS["MATCHED"]):
        idx += 1
        pid, sid, utr = f"pay_{pfx}demo{idx:04d}", f"setl_{pfx}demo{idx:04d}", f"UTR{pfx}DEMO{idx:04d}"
        amount, day = next_amount(), idx % 25
        payments.append(PaymentInput(razorpay_payment_id=pid, amount=amount, fee=0, tax=0))
        settlements.append(SettlementInput(razorpay_settlement_id=sid, utr=utr, amount=amount,
                                            settlement_date=BASE_DATE + timedelta(days=day), payment_ids=[pid]))
        bank_rows.append(BankRowInput(id=f"bank-{sid}", transaction_date=BASE_DATE + timedelta(days=day),
                                       reference_id=sid, utr=utr, credit=amount))
        ground_truth[sid] = "MATCHED"

    for _ in range(CATEGORY_TARGET_COUNTS["FEE_TAX"]):
        idx += 1
        pid, sid, utr = f"pay_{pfx}demo{idx:04d}", f"setl_{pfx}demo{idx:04d}", f"UTR{pfx}DEMO{idx:04d}"
        amount, day = next_amount(), idx % 25
        fee, tax = fee_tax_for(amount)
        net = round(amount - fee - tax, 2)
        payments.append(PaymentInput(razorpay_payment_id=pid, amount=amount, fee=fee, tax=tax))
        settlements.append(SettlementInput(razorpay_settlement_id=sid, utr=utr, amount=amount,
                                            settlement_date=BASE_DATE + timedelta(days=day), payment_ids=[pid]))
        bank_rows.append(BankRowInput(id=f"bank-{sid}", transaction_date=BASE_DATE + timedelta(days=day),
                                       reference_id=sid, utr=utr, credit=net))
        ground_truth[sid] = "FEE_TAX"

    for _ in range(CATEGORY_TARGET_COUNTS["REFUND"]):
        idx += 1
        pid, sid, rid, utr = f"pay_{pfx}demo{idx:04d}", f"setl_{pfx}demo{idx:04d}", f"rfnd_{pfx}demo{idx:04d}", f"UTR{pfx}DEMO{idx:04d}"
        amount, day = next_amount(), idx % 25
        refund_amount = round(amount * rng.uniform(0.3, 1.0), 2)
        net = round(amount - refund_amount, 2)
        payments.append(PaymentInput(razorpay_payment_id=pid, amount=amount, fee=0, tax=0))
        refunds.append(RefundInput(razorpay_refund_id=rid, razorpay_payment_id=pid, amount=refund_amount))
        settlements.append(SettlementInput(razorpay_settlement_id=sid, utr=utr, amount=amount,
                                            settlement_date=BASE_DATE + timedelta(days=day), payment_ids=[pid]))
        bank_rows.append(BankRowInput(id=f"bank-{sid}", transaction_date=BASE_DATE + timedelta(days=day),
                                       reference_id=sid, utr=utr, credit=net))
        ground_truth[sid] = "REFUND"

    for _ in range(CATEGORY_TARGET_COUNTS["TIMING_DIFFERENCE"]):
        idx += 1
        pid, sid, utr = f"pay_{pfx}demo{idx:04d}", f"setl_{pfx}demo{idx:04d}", f"UTR{pfx}DEMO{idx:04d}"
        amount, day = next_amount(), idx % 25
        payments.append(PaymentInput(razorpay_payment_id=pid, amount=amount, fee=0, tax=0))
        settlements.append(SettlementInput(razorpay_settlement_id=sid, utr=utr, amount=amount,
                                            settlement_date=BASE_DATE + timedelta(days=day), payment_ids=[pid]))
        bank_rows.append(BankRowInput(id=f"bank-{sid}", transaction_date=BASE_DATE + timedelta(days=day + 2),
                                       reference_id=sid, utr=utr, credit=amount))
        ground_truth[sid] = "TIMING_DIFFERENCE"

    for _ in range(CATEGORY_TARGET_COUNTS["MISSING_BANK_CREDIT"]):
        idx += 1
        sid, utr = f"setl_{pfx}demo{idx:04d}", f"UTR{pfx}DEMO{idx:04d}"
        amount, day = next_amount(), idx % 25
        settlements.append(SettlementInput(razorpay_settlement_id=sid, utr=utr, amount=amount,
                                            settlement_date=BASE_DATE + timedelta(days=day), payment_ids=[]))
        ground_truth[sid] = "MISSING_BANK_CREDIT"

    for _ in range(CATEGORY_TARGET_COUNTS["DUPLICATE"]):
        idx += 1
        pid, sid, utr = f"pay_{pfx}demo{idx:04d}", f"setl_{pfx}demo{idx:04d}", f"UTR{pfx}DEMO{idx:04d}"
        amount, day = next_amount(), idx % 25
        payments.append(PaymentInput(razorpay_payment_id=pid, amount=amount, fee=0, tax=0))
        settlements.append(SettlementInput(razorpay_settlement_id=sid, utr=utr, amount=amount,
                                            settlement_date=BASE_DATE + timedelta(days=day), payment_ids=[pid]))
        bank_rows.append(BankRowInput(id=f"bank-{sid}-a", transaction_date=BASE_DATE + timedelta(days=day),
                                       reference_id=sid, utr=utr, credit=amount))
        bank_rows.append(BankRowInput(id=f"bank-{sid}-b", transaction_date=BASE_DATE + timedelta(days=day),
                                       reference_id=sid, utr=utr, credit=amount))
        ground_truth[sid] = "DUPLICATE"

    for _ in range(CATEGORY_TARGET_COUNTS["AMOUNT_MISMATCH"]):
        idx += 1
        pid, sid, utr = f"pay_{pfx}demo{idx:04d}", f"setl_{pfx}demo{idx:04d}", f"UTR{pfx}DEMO{idx:04d}"
        amount, day = next_amount(), idx % 25
        wrong_amount = round(amount + rng.uniform(50, 500) * rng.choice([-1, 1]), 2)
        payments.append(PaymentInput(razorpay_payment_id=pid, amount=amount, fee=0, tax=0))
        settlements.append(SettlementInput(razorpay_settlement_id=sid, utr=utr, amount=amount,
                                            settlement_date=BASE_DATE + timedelta(days=day), payment_ids=[pid]))
        bank_rows.append(BankRowInput(id=f"bank-{sid}", transaction_date=BASE_DATE + timedelta(days=day),
                                       reference_id=sid, utr=utr, credit=wrong_amount))
        ground_truth[sid] = "AMOUNT_MISMATCH"

    data = ReconciliationInput(payments=payments, settlements=settlements, refunds=refunds, bank_rows=bank_rows)
    return data, ground_truth
