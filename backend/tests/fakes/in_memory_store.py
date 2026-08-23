from typing import Optional

from app.ai.data_store import InvestigationDataStore
from app.services.reconciliation_engine import calculate_expected_settlement as _calc
from app.schemas.reconciliation_engine import PaymentInput, RefundInput


class InMemoryInvestigationStore(InvestigationDataStore):
    """Test double — holds everything in plain dicts, no DB involved."""

    def __init__(self):
        self.payments: dict[str, dict] = {}
        self.settlements: dict[str, dict] = {}
        self.refunds: dict[str, list[dict]] = {}
        self.bank_rows: list[dict] = []
        self.cases: dict[str, dict] = {}
        self.marked_for_review: list[tuple[str, str]] = []

    async def get_payment(self, payment_id: str) -> Optional[dict]:
        return self.payments.get(payment_id)

    async def get_settlement(self, settlement_id: str) -> Optional[dict]:
        return self.settlements.get(settlement_id)

    async def get_refunds(self, payment_id: str) -> list[dict]:
        return self.refunds.get(payment_id, [])

    async def search_bank_transactions(
        self, utr=None, reference_id=None, amount=None, date_from=None, date_to=None,
    ) -> list[dict]:
        results = self.bank_rows
        if utr:
            results = [r for r in results if r.get("utr") == utr]
        if reference_id:
            results = [r for r in results if r.get("reference_id") == reference_id]
        if amount is not None:
            results = [r for r in results if r.get("credit") == amount]
        return results

    async def get_reconciliation_case(self, case_id: str) -> Optional[dict]:
        return self.cases.get(case_id)

    async def calculate_expected_settlement(self, case_id: str) -> Optional[float]:
        case = self.cases.get(case_id)
        if not case:
            return None
        payments = [PaymentInput(**self.payments[pid]) for pid in case.get("payment_ids", []) if pid in self.payments]
        refunds = [
            RefundInput(**r) for pid in case.get("payment_ids", []) for r in self.refunds.get(pid, [])
        ]
        return _calc(payments, refunds)

    async def mark_case_for_review(self, case_id: str, reason: str) -> bool:
        self.marked_for_review.append((case_id, reason))
        return True
