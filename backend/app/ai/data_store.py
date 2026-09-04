"""Data store interfaces used by the AI Investigator."""

from abc import ABC, abstractmethod
from typing import Optional


class InvestigationDataStore(ABC):
    @abstractmethod
    async def get_payment(self, payment_id: str) -> Optional[dict]:
        """Returns a normalized payment dict, or None if it doesn't exist."""

    @abstractmethod
    async def get_settlement(self, settlement_id: str) -> Optional[dict]:
        """Returns a normalized settlement dict, or None if it doesn't exist."""

    @abstractmethod
    async def get_refunds(self, payment_id: str) -> list[dict]:
        """Returns all refunds issued against a payment. Empty list if none."""

    @abstractmethod
    async def search_bank_transactions(
        self, utr: Optional[str] = None, reference_id: Optional[str] = None,
        amount: Optional[float] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> list[dict]:
        """Searches the uploaded bank statement. Never invents rows that don't exist."""

    @abstractmethod
    async def get_reconciliation_case(self, case_id: str) -> Optional[dict]:
        """Returns the case being investigated, including linked payment/settlement IDs."""

    @abstractmethod
    async def calculate_expected_settlement(self, case_id: str) -> Optional[float]:
        """Delegates to the deterministic engine's calculation — the AI never does this math itself."""

    @abstractmethod
    async def mark_case_for_review(self, case_id: str, reason: str) -> bool:
        """Flags a case for mandatory human review. Always allowed, never blocked."""
