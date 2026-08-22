from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Reconciliation Investigator",
    description="AI-powered financial reconciliation investigator for Razorpay merchants.",
    version="0.1.0",
)

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


# Routers are added incrementally as each phase is built:
# from app.api.v1 import razorpay, bank_statements, reconciliation, investigations, audit
# app.include_router(razorpay.router, prefix=settings.API_V1_PREFIX)
