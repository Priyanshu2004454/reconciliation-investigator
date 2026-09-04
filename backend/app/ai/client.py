from typing import Any
from app.core.config import get_settings
from app.ai.providers import BaseAIProvider, GeminiAIProvider, AnthropicAIProvider


class AIClientNotConfiguredError(Exception):
    pass


def get_ai_provider() -> BaseAIProvider:
    settings = get_settings()
    provider_name = (settings.AI_PROVIDER or "gemini").strip().lower()

    if provider_name == "gemini":
        key = (settings.GEMINI_API_KEY or "").strip()
        if not key or key.startswith("AIzaSy-placeholder") or key.startswith("your-") or key.startswith("xxx"):
            raise AIClientNotConfiguredError(
                
            )
        try:
            from google import genai
        except ImportError as exc:
            raise AIClientNotConfiguredError(
                
            ) from exc

        client = genai.Client(api_key=key)
        model = settings.AI_MODEL if (settings.AI_MODEL and not settings.AI_MODEL.startswith("claude")) else "gemini-3.1-flash-lite"
        return GeminiAIProvider(client=client, model=model)

    elif provider_name == "anthropic":
        key = (settings.ANTHROPIC_API_KEY or "").strip()
        if not key or key.startswith("sk-ant-xxx") or key.startswith("your-") or key.startswith("xxx"):
            raise AIClientNotConfiguredError(
                
            )
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise AIClientNotConfiguredError(
                
            ) from exc

        client = AsyncAnthropic(api_key=key)
        model = settings.AI_MODEL if (settings.AI_MODEL and not settings.AI_MODEL.startswith("gemini")) else "claude-sonnet-4-6"
        return AnthropicAIProvider(client=client, model=model)

    else:
        raise AIClientNotConfiguredError(
            f"Unsupported AI_PROVIDER '{provider_name}'. Supported providers: 'gemini', 'anthropic'."
        )


def get_ai_client() -> Any:
    
    return get_ai_provider()
