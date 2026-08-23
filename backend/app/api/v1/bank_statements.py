import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant_account
from app.db.session import get_db
from app.models.financial import BankTransaction
from app.models.users import MerchantAccount
from app.schemas.bank_statement import ImportSummary
from app.services.bank_statement_parser import parse_bank_statement_csv, BankStatementValidationError

router = APIRouter(prefix="/bank-statements", tags=["bank-statements"])


@router.post("/upload", response_model=ImportSummary, status_code=status.HTTP_201_CREATED)
async def upload_bank_statement(
    file: UploadFile,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()

    try:
        rows, summary = parse_bank_statement_csv(content, file.filename or "upload.csv")
    except BankStatementValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    batch_id = uuid.UUID(summary.import_batch_id)
    for row in rows:
        db.add(BankTransaction(
            merchant_account_id=merchant.id,
            import_batch_id=batch_id,
            transaction_date=row.transaction_date,
            description=row.description,
            reference_id=row.reference_id,
            utr=row.utr,
            credit=row.credit,
            debit=row.debit,
            balance=row.balance,
            row_hash=row.row_hash,
            is_duplicate=row.is_duplicate,
            raw_row=row.model_dump(mode="json"),
        ))

    await db.commit()
    return summary
