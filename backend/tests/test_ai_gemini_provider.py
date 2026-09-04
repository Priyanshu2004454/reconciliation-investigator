import pytest

from app.ai.providers import (
    GeminiAIProvider,
    InvestigationHallucinationError,
    InvestigationError,
)
from tests.fakes.fake_gemini import (
    FakeGeminiClient,
    gemini_function_call_response,
    gemini_text_response,
)
from tests.fakes.in_memory_store import InMemoryInvestigationStore


# ─── env fixture (same pattern as existing Claude tests) ─────────────────────

@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-tests")
    monkeypatch.setenv("AI_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("AI_MAX_TOKENS", "2000")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "x")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("APP_SECRET_KEY", "x")
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ─── shared store fixture ─────────────────────────────────────────────────────

def _missing_bank_credit_store() -> InMemoryInvestigationStore:
    store = InMemoryInvestigationStore()
    store.settlements["setl_XYZ"] = {
        "razorpay_settlement_id": "setl_XYZ", "utr": "UTR_ABC",
        "amount": 25000.0, "status": "processed", "settlement_date": "2026-08-22",
    }
    store.cases["case_gemini_1"] = {
        "id": "case_gemini_1", "razorpay_settlement_id": "setl_XYZ", "payment_ids": [],
    }
    store.bank_rows = []
    return store


# ─── Tests ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_happy_path_missing_bank_credit():
    """Full tool-use loop: get_case → get_settlement → search_bank → submit."""
    store = _missing_bank_credit_store()
    client = FakeGeminiClient([
        gemini_function_call_response("get_reconciliation_case", {"case_id": "case_gemini_1"}),
        gemini_function_call_response("get_settlement", {"settlement_id": "setl_XYZ"}),
        gemini_function_call_response("search_bank_transactions", {"utr": "UTR_ABC"}),
        gemini_function_call_response("submit_investigation_result", {
            "classification": "NEEDS_REVIEW",
            "root_cause": "MISSING_BANK_CREDIT",
            "explanation": "Settlement setl_XYZ (UTR UTR_ABC) is processed but no matching bank row exists.",
            "evidence": [
                {
                    "source_type": "RAZORPAY_SETTLEMENT",
                    "source_id": "UTR_ABC",
                    "description": "Settlement UTR UTR_ABC, amount 25000, status processed",
                },
            ],
            "confidence": 0.93,
            "recommended_action": "Contact bank to verify UTR_ABC was credited.",
            "requires_human_review": True,
        }),
    ])

    provider = GeminiAIProvider(client=client, model="gemini-3.6-flash")
    run = await provider.investigate("case_gemini_1", store)

    assert run.result.classification == "NEEDS_REVIEW"
    assert run.result.root_cause == "MISSING_BANK_CREDIT"
    assert run.result.requires_human_review is True
    assert run.ai_model == "gemini-3.6-flash"
    # submit_investigation_result is NOT counted as a tool call in the log
    assert len(run.tool_calls) == 3


@pytest.mark.asyncio
async def test_gemini_hallucination_guard_rejects_invented_evidence():
    """AI references a bank UTR it never fetched → InvestigationHallucinationError."""
    store = _missing_bank_credit_store()
    client = FakeGeminiClient([
        gemini_function_call_response("get_reconciliation_case", {"case_id": "case_gemini_1"}),
        gemini_function_call_response("submit_investigation_result", {
            "classification": "EXPLAINED",
            "root_cause": "TIMING_DIFFERENCE",
            "explanation": "Bank credit posted a day later.",
            "evidence": [
                {
                    "source_type": "BANK_STATEMENT",
                    "source_id": "INVENTED_UTR_NEVER_FETCHED",
                    "description": "Invented bank row",
                },
            ],
            "confidence": 0.8,
            "recommended_action": "No action.",
            "requires_human_review": False,
        }),
    ])

    provider = GeminiAIProvider(client=client, model="gemini-3.6-flash")
    with pytest.raises(InvestigationHallucinationError):
        await provider.investigate("case_gemini_1", store)


@pytest.mark.asyncio
async def test_gemini_plain_text_response_is_nudged_then_submit():
    """Gemini answers in plain text → we nudge → it submits properly."""
    store = _missing_bank_credit_store()
    client = FakeGeminiClient([
        gemini_function_call_response("get_reconciliation_case", {"case_id": "case_gemini_1"}),
        gemini_text_response("I think this is probably a bank issue."),  # wrong — will be nudged
        gemini_function_call_response("submit_investigation_result", {
            "classification": "NEEDS_REVIEW",
            "root_cause": "MISSING_BANK_CREDIT",
            "explanation": "No bank credit found for this settlement's UTR.",
            "evidence": [],
            "confidence": 0.70,
            "recommended_action": "Verify with bank.",
            "requires_human_review": True,
        }),
    ])

    provider = GeminiAIProvider(client=client, model="gemini-3.6-flash")
    run = await provider.investigate("case_gemini_1", store)

    assert run.result.classification == "NEEDS_REVIEW"
    # 3 calls: initial, nudge, final
    assert client.aio.models.call_count == 3


@pytest.mark.asyncio
async def test_gemini_runs_out_of_iterations():
    """If Gemini keeps calling tools without submitting, raises InvestigationError."""
    store = _missing_bank_credit_store()
    client = FakeGeminiClient([
        gemini_function_call_response("get_reconciliation_case", {"case_id": "case_gemini_1"}),
        gemini_function_call_response("get_reconciliation_case", {"case_id": "case_gemini_1"}),
        gemini_function_call_response("get_reconciliation_case", {"case_id": "case_gemini_1"}),
    ])

    provider = GeminiAIProvider(client=client, model="gemini-3.6-flash")
    with pytest.raises(InvestigationError):
        await provider.investigate("case_gemini_1", store, max_tool_iterations=3)


# ─── Provider selection tests ─────────────────────────────────────────────────

def test_get_ai_provider_selects_gemini(monkeypatch):
    """AI_PROVIDER=gemini with a key set → returns GeminiAIProvider."""
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy-real-key")
    from app.core.config import get_settings
    get_settings.cache_clear()

    # Patch genai.Client so no real network call is made
    import unittest.mock as mock
    with mock.patch("google.genai.Client") as MockClient:
        MockClient.return_value = object()
        from app.ai.client import get_ai_provider
        provider = get_ai_provider()
        assert isinstance(provider, GeminiAIProvider)
    get_settings.cache_clear()


def test_get_ai_provider_selects_anthropic(monkeypatch):
    """AI_PROVIDER=anthropic with a key set → returns AnthropicAIProvider."""
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-key")
    from app.core.config import get_settings
    get_settings.cache_clear()

    import unittest.mock as mock
    with mock.patch("anthropic.AsyncAnthropic") as MockClaude:
        MockClaude.return_value = object()
        from app.ai.client import get_ai_provider
        from app.ai.providers import AnthropicAIProvider
        provider = get_ai_provider()
        assert isinstance(provider, AnthropicAIProvider)
    get_settings.cache_clear()


def test_missing_gemini_key_raises_configured_error(monkeypatch):
    """AI_PROVIDER=gemini without GEMINI_API_KEY → AIClientNotConfiguredError."""
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from app.core.config import get_settings
    get_settings.cache_clear()

    from app.ai.client import get_ai_provider, AIClientNotConfiguredError
    with pytest.raises(AIClientNotConfiguredError) as exc_info:
        get_ai_provider()
    assert "GEMINI_API_KEY" in str(exc_info.value)
    get_settings.cache_clear()


def test_unsupported_provider_raises_configured_error(monkeypatch):
    """AI_PROVIDER=openai (unsupported) → AIClientNotConfiguredError."""
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    from app.core.config import get_settings
    get_settings.cache_clear()

    from app.ai.client import get_ai_provider, AIClientNotConfiguredError
    with pytest.raises(AIClientNotConfiguredError) as exc_info:
        get_ai_provider()
    assert "openai" in str(exc_info.value)
    get_settings.cache_clear()
