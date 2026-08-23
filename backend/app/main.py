from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.api.v1 import auth, merchant_accounts, razorpay_routes, bank_statements, reconciliation, investigations, dashboard, audit, webhooks

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])

app = FastAPI(
    title="Reconciliation Investigator",
    description="AI-powered financial reconciliation investigator for Razorpay merchants.",
    version="0.1.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Basic liveness check. Never returns secrets — see settings.safe_dict()."""
    return {
        "status": "ok",
        "app_env": settings.APP_ENV,
        "config": settings.safe_dict(),
    }


app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(merchant_accounts.router, prefix=settings.API_V1_PREFIX)
app.include_router(razorpay_routes.router, prefix=settings.API_V1_PREFIX)
app.include_router(bank_statements.router, prefix=settings.API_V1_PREFIX)
app.include_router(reconciliation.router, prefix=settings.API_V1_PREFIX)
app.include_router(investigations.router, prefix=settings.API_V1_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_V1_PREFIX)
app.include_router(audit.router, prefix=settings.API_V1_PREFIX)

# Deliberately NOT under /api/v1 — Razorpay's webhook is a fixed integration
# endpoint (section 5 specifies POST /api/webhooks/razorpay exactly), not a
# versioned client-facing API route.
app.include_router(webhooks.router, prefix="/api")
