"""
Central application configuration.

Loads all settings from environment variables (.env file locally, real env vars
in production). NEVER hardcode secrets here. RAZORPAY_KEY_SECRET and
ANTHROPIC_API_KEY must only ever be read on the backend and must never be
serialized into any response sent to the frontend.
"""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────
    APP_ENV: str = "development"
    APP_SECRET_KEY: str
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:3000"

    # ── Database ─────────────────────────────────────
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # ── Razorpay ─────────────────────────────────────
    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str
    RAZORPAY_WEBHOOK_SECRET: str

    # ── AI ───────────────────────────────────────────
    AI_PROVIDER: str = "gemini"  # "gemini" | "anthropic"
    GEMINI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL: str = ""  # If empty, defaults to gemini-2.5-flash or claude-sonnet-4-6 based on provider
    AI_MAX_TOKENS: int = 2000
    AI_TIMEOUT_SECONDS: int = 30

    # ── Auth ─────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # ── Reconciliation Engine ────────────────────────
    MATCH_DATE_WINDOW_DAYS: int = 3
    MATCH_AMOUNT_TOLERANCE_PAISE: int = 100

    # ── Rate limiting ────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    def safe_dict(self) -> dict:
        """Returns settings with all secrets redacted — safe to log or expose."""
        redacted = "***REDACTED***"
        return {
            "APP_ENV": self.APP_ENV,
            "API_V1_PREFIX": self.API_V1_PREFIX,
            "RAZORPAY_KEY_ID": self.RAZORPAY_KEY_ID[:10] + "..." if self.RAZORPAY_KEY_ID else "",
            "RAZORPAY_KEY_SECRET": redacted if self.RAZORPAY_KEY_SECRET else "",
            "AI_PROVIDER": self.AI_PROVIDER,
            "GEMINI_API_KEY": redacted if self.GEMINI_API_KEY else "",
            "ANTHROPIC_API_KEY": redacted if self.ANTHROPIC_API_KEY else "",
            "JWT_SECRET_KEY": redacted if self.JWT_SECRET_KEY else "",
            "AI_MODEL": self.AI_MODEL,
            "MATCH_DATE_WINDOW_DAYS": self.MATCH_DATE_WINDOW_DAYS,
        }


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — env is read once per process."""
    return Settings()
