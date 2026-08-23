from anthropic import AsyncAnthropic

from app.core.config import get_settings


class AIClientNotConfiguredError(Exception):
    pass


def get_ai_client() -> AsyncAnthropic:
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        raise AIClientNotConfiguredError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env before running investigations."
        )
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
