from fastapi import APIRouter, Depends, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import get_ai_client, AIClientNotConfiguredError
from app.ai.copilot import run_copilot_turn, CopilotError, CopilotTimeoutError, CopilotGroundingError
from app.ai.copilot_tools import CopilotDataStore
from app.ai.providers import AIProviderError
from app.api.deps import get_current_merchant_account
from app.db.session import get_db
from app.models.users import MerchantAccount
from app.schemas.copilot import CopilotChatRequest, CopilotChatResponse

router = APIRouter(prefix="/copilot", tags=["copilot"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/chat", response_model=CopilotChatResponse)
@limiter.limit("30/minute")
async def copilot_chat(
    request: Request,
    payload: CopilotChatRequest,
    merchant: MerchantAccount = Depends(get_current_merchant_account),
    db: AsyncSession = Depends(get_db),
):
    try:
        client = get_ai_client()
    except AIClientNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    store = CopilotDataStore(db, merchant.id)
    history = [{"role": h.role, "text": h.text} for h in payload.history]

    try:
        result = await run_copilot_turn(payload.message, history, store, client)
    except CopilotTimeoutError as exc:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except CopilotGroundingError as exc:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Evidence could not be verified.") from exc
    except AIProviderError as exc:
        import traceback; traceback.print_exc()
        status_code = status.HTTP_429_TOO_MANY_REQUESTS if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except CopilotError as exc:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return CopilotChatResponse(
        text=result.text,
        insights=[{"title": i["title"], "count": i["count"], "amount": i["amount"]} for i in result.insights],
        case_refs=[{"case_id": c["case_id"], "label": c["label"]} for c in result.case_refs],
        sources=[{"tool_name": s.tool_name, "summary": s.summary} for s in result.sources],
    )
