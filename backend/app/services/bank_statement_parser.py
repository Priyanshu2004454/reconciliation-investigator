"""
Bank statement CSV import.

Different banks name their columns differently (see section 6 of the spec).
This module:
  1. detects which CSV column maps to which internal field,
  2. validates the file has enough information to be usable,
  3. normalizes every row into a consistent internal shape,
  4. flags empty/duplicate/malformed rows instead of silently dropping them.

Nothing here talks to the database — it returns plain data structures that
the API layer persists. Keeps the parsing logic independently testable.
"""

import hashlib
import io
import re
import uuid
from datetime import date, datetime

import pandas as pd

from app.schemas.bank_statement import BankRowError, ImportSummary, NormalizedBankRow

ALLOWED_EXTENSIONS = {".csv"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

# Candidate header names (lowercased, non-alphanumeric stripped) for each internal field.
# Order matters within a list only for readability — matching is exact-set based.
COLUMN_CANDIDATES: dict[str, set[str]] = {
    "transaction_date": {"date", "transactiondate", "txndate", "valuedate", "postingdate"},
    "description": {"description", "narration", "particulars", "remarks", "transactiondetails"},
    "reference_id": {"referenceno", "reference", "referenceid", "chqrefno", "txnid", "transactionid"},
    "utr": {"utr", "utrno", "utrnumber"},
    "credit": {"credit", "creditamount", "deposit", "depositamount", "cr"},
    "debit": {"debit", "debitamount", "withdrawal", "withdrawalamount", "dr"},
    "balance": {"balance", "closingbalance", "runningbalance", "availablebalance"},
}

REQUIRED_FIELDS = {"transaction_date"}  # must have at least a date column
AT_LEAST_ONE_OF = {"credit", "debit"}  # must have at least one amount column


class BankStatementValidationError(Exception):
    """Raised when the file cannot be parsed at all (wrong type, no usable columns)."""


def _normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header).strip().lower())


def _detect_columns(headers: list[str]) -> dict[str, str]:
    """Returns internal_field -> original_column_name for every field we could detect."""
    normalized_to_original = {_normalize_header(h): h for h in headers}
    detected: dict[str, str] = {}

    for internal_field, candidates in COLUMN_CANDIDATES.items():
        for norm_header, original in normalized_to_original.items():
            if norm_header in candidates:
                detected[internal_field] = original
                break

    return detected


def _validate_file(filename: str, content: bytes) -> None:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise BankStatementValidationError(
            f"Unsupported file type '{ext}'. Only .csv files are accepted."
        )
    if len(content) == 0:
        raise BankStatementValidationError("Uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise BankStatementValidationError(
            f"File exceeds maximum size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
        )


def _parse_amount(raw) -> float | None:
    """Handles '1,234.50', '₹1,234.50', '(500.00)' (negative), empty/NaN -> None."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if s == "" or s.lower() in {"nan", "none", "-"}:
        return None

    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = re.sub(r"[^\d.\-]", "", s)  # strip currency symbols, commas, spaces
    if s in {"", "-", "."}:
        return None

    try:
        value = float(s)
    except ValueError:
        return None
    return -abs(value) if negative else value


def _parse_date(raw) -> date | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        parsed = pd.to_datetime(raw, dayfirst=True, errors="raise")
        return parsed.date()
    except (ValueError, TypeError):
        return None


def _row_hash(row: NormalizedBankRow) -> str:
    key = f"{row.transaction_date}|{row.reference_id}|{row.utr}|{row.credit}|{row.debit}|{row.balance}"
    return hashlib.sha256(key.encode()).hexdigest()


def parse_bank_statement_csv(content: bytes, filename: str) -> tuple[list[NormalizedBankRow], ImportSummary]:
    """
    Parses raw CSV bytes into normalized rows + an import summary.
    Never raises for row-level problems — those are captured in ImportSummary.errors.
    Raises BankStatementValidationError only for file-level problems (wrong type,
    unreadable, missing required columns entirely).
    """
    _validate_file(filename, content)

    try:
        df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=True)
    except Exception as exc:  # noqa: BLE001
        raise BankStatementValidationError(f"Could not parse CSV: {exc}") from exc

    if df.empty:
        raise BankStatementValidationError("CSV contains no data rows.")

    detected = _detect_columns(list(df.columns))

    missing_required = REQUIRED_FIELDS - detected.keys()
    if missing_required:
        raise BankStatementValidationError(
            f"Could not detect required column(s): {sorted(missing_required)}. "
            f"Found columns: {list(df.columns)}"
        )
    if not (AT_LEAST_ONE_OF & detected.keys()):
        raise BankStatementValidationError(
            "Could not detect a credit or debit amount column. "
            f"Found columns: {list(df.columns)}"
        )

    import_batch_id = str(uuid.uuid4())
    normalized_rows: list[NormalizedBankRow] = []
    errors: list[BankRowError] = []
    seen_hashes: set[str] = set()
    duplicated_count = 0
    needs_review_count = 0

    for position, (_, raw_row) in enumerate(df.iterrows()):
        row_number = position + 2  # +1 for 0-index, +1 for header row
        raw_dict = raw_row.to_dict()

        # Skip fully empty rows silently — these aren't errors, just blank lines
        if raw_row.isna().all() or all(str(v).strip() == "" for v in raw_row if pd.notna(v)):
            continue

        txn_date = _parse_date(raw_dict.get(detected.get("transaction_date", "")))
        if txn_date is None:
            errors.append(BankRowError(row_number=row_number, reason="Invalid or missing date", raw_row=raw_dict))
            continue

        credit = _parse_amount(raw_dict.get(detected.get("credit", ""), None)) if "credit" in detected else None
        debit = _parse_amount(raw_dict.get(detected.get("debit", ""), None)) if "debit" in detected else None
        balance = _parse_amount(raw_dict.get(detected.get("balance", ""), None)) if "balance" in detected else None

        if credit is None and debit is None:
            errors.append(
                BankRowError(row_number=row_number, reason="Row has neither a credit nor debit amount", raw_row=raw_dict)
            )
            continue

        needs_review = False
        if credit is not None and debit is not None and credit > 0 and debit > 0:
            # Same row has both a credit and a debit amount — ambiguous, flag for human review
            needs_review = True

        description = raw_dict.get(detected.get("description", ""), None)
        reference_id = raw_dict.get(detected.get("reference_id", ""), None)
        utr = raw_dict.get(detected.get("utr", ""), None)

        row = NormalizedBankRow(
            transaction_date=txn_date,
            description=str(description).strip() if description and str(description).strip().lower() != "nan" else None,
            reference_id=str(reference_id).strip() if reference_id and str(reference_id).strip().lower() != "nan" else None,
            utr=str(utr).strip() if utr and str(utr).strip().lower() != "nan" else None,
            credit=credit,
            debit=debit,
            balance=balance,
        )
        row_hash = _row_hash(row)
        row.row_hash = row_hash

        if row_hash in seen_hashes:
            row.is_duplicate = True
            duplicated_count += 1
        else:
            seen_hashes.add(row_hash)

        if needs_review:
            needs_review_count += 1

        normalized_rows.append(row)

    summary = ImportSummary(
        import_batch_id=import_batch_id,
        filename=filename,
        total_rows=len(df),
        rows_imported=len([r for r in normalized_rows if not r.is_duplicate]),
        rows_rejected=len(errors),
        rows_duplicated=duplicated_count,
        rows_requiring_review=needs_review_count,
        detected_columns=detected,
        errors=errors,
    )

    return normalized_rows, summary
