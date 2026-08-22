import pytest

from app.services.bank_statement_parser import (
    parse_bank_statement_csv,
    BankStatementValidationError,
)


def test_detects_hdfc_style_columns():
    """Different bank, different column names — should still normalize correctly."""
    csv_content = (
        "Transaction Date,Narration,Reference No,Credit Amount,Debit Amount,Balance\n"
        "01/06/2026,UPI-ACME CORP-pay_ABC,REF1001,9787.60,,150000.00\n"
        "02/06/2026,NEFT-XYZ LTD,REF1002,,5000.00,145000.00\n"
    ).encode()

    rows, summary = parse_bank_statement_csv(csv_content, "hdfc_statement.csv")

    assert summary.detected_columns["transaction_date"] == "Transaction Date"
    assert summary.detected_columns["credit"] == "Credit Amount"
    assert summary.detected_columns["debit"] == "Debit Amount"
    assert summary.rows_imported == 2
    assert summary.rows_rejected == 0
    assert rows[0].credit == 9787.60
    assert rows[1].debit == 5000.00


def test_detects_alternate_column_names():
    """A different bank using UTR/Deposit/Withdrawal naming."""
    csv_content = (
        "Date,Particulars,UTR,Deposit,Withdrawal,Closing Balance\n"
        "10-06-2026,Settlement credit,UTR999XYZ,25000.00,,100000\n"
    ).encode()

    rows, summary = parse_bank_statement_csv(csv_content, "other_bank.csv")

    assert summary.detected_columns["utr"] == "UTR"
    assert rows[0].utr == "UTR999XYZ"
    assert rows[0].credit == 25000.00


def test_rejects_file_with_no_amount_column():
    csv_content = "Date,Description\n01/06/2026,Some transaction\n".encode()
    with pytest.raises(BankStatementValidationError):
        parse_bank_statement_csv(csv_content, "bad.csv")


def test_rejects_non_csv_extension():
    with pytest.raises(BankStatementValidationError):
        parse_bank_statement_csv(b"whatever", "statement.xlsx")


def test_rejects_empty_file():
    with pytest.raises(BankStatementValidationError):
        parse_bank_statement_csv(b"", "empty.csv")


def test_flags_invalid_dates_as_row_errors_not_crashes():
    csv_content = (
        "Date,Description,Credit,Debit,Balance\n"
        "01/06/2026,Good row,1000,,5000\n"
        "NOT-A-DATE,Bad row,2000,,7000\n"
    ).encode()

    rows, summary = parse_bank_statement_csv(csv_content, "statement.csv")

    assert summary.rows_imported == 1
    assert summary.rows_rejected == 1
    assert summary.errors[0].reason == "Invalid or missing date"


def test_handles_currency_symbols_and_commas():
    csv_content = (
        'Date,Description,Credit,Debit,Balance\n'
        '01/06/2026,Big payment,"\u20b91,25,000.50",,"\u20b95,00,000.00"\n'
    ).encode()
    rows, summary = parse_bank_statement_csv(csv_content, "statement.csv")
    assert summary.rows_imported == 1
    assert rows[0].credit == 125000.50


def test_detects_duplicate_rows():
    csv_content = (
        "Date,Description,Reference,Credit,Debit,Balance\n"
        "01/06/2026,Payment A,REF1,1000,,5000\n"
        "01/06/2026,Payment A,REF1,1000,,5000\n"  # exact duplicate
        "02/06/2026,Payment B,REF2,2000,,7000\n"
    ).encode()

    rows, summary = parse_bank_statement_csv(csv_content, "statement.csv")

    assert summary.total_rows == 3
    assert summary.rows_duplicated == 1
    assert summary.rows_imported == 2  # duplicate not double-counted as imported
    assert rows[1].is_duplicate is True


def test_skips_blank_rows_silently():
    csv_content = (
        "Date,Description,Credit,Debit,Balance\n"
        "01/06/2026,Payment A,1000,,5000\n"
        ",,,,\n"
        "02/06/2026,Payment B,2000,,7000\n"
    ).encode()

    rows, summary = parse_bank_statement_csv(csv_content, "statement.csv")
    assert summary.rows_imported == 2
    assert summary.rows_rejected == 0


def test_flags_ambiguous_row_with_both_credit_and_debit():
    csv_content = (
        "Date,Description,Credit,Debit,Balance\n"
        "01/06/2026,Weird row,1000,500,5000\n"
    ).encode()
    rows, summary = parse_bank_statement_csv(csv_content, "statement.csv")
    assert summary.rows_requiring_review == 1
