from datetime import date
from typing import Optional

from pydantic import BaseModel


class BankRowError(BaseModel):
    row_number: int  
    reason: str
    raw_row: dict


class ImportSummary(BaseModel):
    import_batch_id: str
    filename: str
    total_rows: int
    rows_imported: int
    rows_rejected: int
    rows_duplicated: int
    rows_requiring_review: int
    detected_columns: dict[str, str]  
    errors: list[BankRowError] = []


class NormalizedBankRow(BaseModel):
    transaction_date: date
    description: Optional[str] = None
    reference_id: Optional[str] = None
    utr: Optional[str] = None
    credit: Optional[float] = None
    debit: Optional[float] = None
    balance: Optional[float] = None
    row_hash: str = ""
    is_duplicate: bool = False
