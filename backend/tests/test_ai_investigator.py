import pytest

from app.ai.investigator import (
    investigate_case,
    InvestigationHallucinationError,
    InvestigationTimeoutError,
    InvestigationError,
)
from tests.fakes.in_memory_store import InMemoryInvestigationStore
from tests.fakes.fake_anthropic import FakeAnthropicClient, tool_use_response, text_response


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("AI_MAX_TOKENS", "2000")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "x")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "x")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg2://u:p@localhost/db")
    monkeypatch.setenv("APP_SECRET_KEY", "x")
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _missing_bank_credit_store() -> InMemoryInvestigationStore:
    """Mirrors spec section 10's example: settlement processed, no matching bank credit."""
    store = InMemoryInvestigationStore()
    store.settlements["setl_XYZ"] = {
        "razorpay_settlement_id": "setl_XYZ", "utr": "ABC123", "amount": 25000.0,
        "status": "processed", "settlement_date": "2026-08-22",
    }
    store.cases["case_1"] = {
        "id": "case_1", "razorpay_settlement_id": "setl_XYZ", "payment_ids": [],
    }
    store.bank_rows = []  # no matching bank credit at all
    return store


@pytest.mark.asyncio
async def test_happy_path_missing_bank_credit_investigation():
    store = _missing_bank_credit_store()
    client = FakeAnthropicClient([
        tool_use_response("t1", "get_reconciliation_case", {"case_id": "case_1"}),
        tool_use_response("t2", "get_settlement", {"settlement_id": "setl_XYZ"}),
        tool_use_response("t3", "search_bank_transactions", {"utr": "ABC123"}),
        tool_use_response("t4", "submit_investigation_result", {
            "classification": "NEEDS_REVIEW",
            "root_cause": "MISSING_BANK_CREDIT",
            "explanation": "Settlement setl_XYZ shows UTR ABC123 with status processed, but no bank "
                            "transaction with that UTR was found in the uploaded statement.",
            "evidence": [
                {"source_type": "RAZORPAY_SETTLEMENT", "source_id": "ABC123",
                 "description": "Settlement UTR ABC123, amount 25000, status processed"},
            ],
            "confidence": 0.94,
            "recommended_action": "Verify with the bank whether UTR ABC123 was actually credited.",
            "requires_human_review": True,
        }),
    ])

    run_result = await investigate_case("case_1", store, client)

    assert run_result.result.classification == "NEEDS_REVIEW"
    assert run_result.result.root_cause == "MISSING_BANK_CREDIT"
    assert run_result.result.requires_human_review is True
    assert len(run_result.tool_calls) == 3  # get_case, get_settlement, search_bank (submit isn't logged as a tool call)


@pytest.mark.asyncio
async def test_hallucination_guard_rejects_invented_evidence():
    """AI claims evidence about a UTR it never actually looked up -> must be rejected."""
    store = _missing_bank_credit_store()
    client = FakeAnthropicClient([
        tool_use_response("t1", "get_reconciliation_case", {"case_id": "case_1"}),
        tool_use_response("t4", "submit_investigation_result", {
            "classification": "EXPLAINED",
            "root_cause": "TIMING_DIFFERENCE",
            "explanation": "The bank credit likely posted a day later under a different reference.",
            "evidence": [
                {"source_type": "BANK_STATEMENT", "source_id": "FAKE_UTR_NEVER_FETCHED",
                 "description": "Bank row exists with a slightly different UTR"},
            ],
            "confidence": 0.8,
            "recommended_action": "No action needed.",
            "requires_human_review": False,
        }),
    ])

    with pytest.raises(InvestigationHallucinationError):
        await investigate_case("case_1", store, client)


@pytest.mark.asyncio
async def test_mark_case_for_review_scoped_to_investigated_case():
    """mark_case_for_review on a DIFFERENT case_id than the one being investigated is rejected."""
    store = _missing_bank_credit_store()
    store.cases["case_2"] = {"id": "case_2", "razorpay_settlement_id": "setl_OTHER", "payment_ids": []}

    client = FakeAnthropicClient([
        tool_use_response("t1", "get_reconciliation_case", {"case_id": "case_1"}),
        tool_use_response("t2", "mark_case_for_review", {"case_id": "case_2", "reason": "trying to touch another case"}),
        tool_use_response("t3", "submit_investigation_result", {
            "classification": "NEEDS_REVIEW", "root_cause": "UNKNOWN",
            "explanation": "Could not verify.", "evidence": [],
            "confidence": 0.3, "recommended_action": "Review manually.",
            "requires_human_review": True,
        }),
    ])

    run_result = await investigate_case("case_1", store, client)
    # the mark_case_for_review call should have been rejected (tool error), not applied
    assert store.marked_for_review == []
    assert run_result.result.classification == "NEEDS_REVIEW"


@pytest.mark.asyncio
async def test_free_text_response_is_rejected_and_model_is_nudged():
    """If the model answers in plain text instead of calling submit_investigation_result, we push back."""
    store = _missing_bank_credit_store()
    client = FakeAnthropicClient([
        tool_use_response("t1", "get_reconciliation_case", {"case_id": "case_1"}),
        text_response("I think this is probably a bank issue."),
        tool_use_response("t2", "submit_investigation_result", {
            "classification": "NEEDS_REVIEW", "root_cause": "MISSING_BANK_CREDIT",
            "explanation": "No bank credit found for this settlement's UTR.",
            "evidence": [], "confidence": 0.7,
            "recommended_action": "Verify with bank.", "requires_human_review": True,
        }),
    ])

    run_result = await investigate_case("case_1", store, client)
    assert run_result.result.classification == "NEEDS_REVIEW"
    assert client.messages.call_count == 3  # initial + nudge + final


@pytest.mark.asyncio
async def test_invalid_structured_output_raises_investigation_error():
    store = _missing_bank_credit_store()
    client = FakeAnthropicClient([
        tool_use_response("t1", "submit_investigation_result", {
            "classification": "TOTALLY_MADE_UP_STATUS",  # invalid enum value
            "root_cause": "UNKNOWN", "explanation": "x", "evidence": [],
            "confidence": 0.5, "recommended_action": "x", "requires_human_review": True,
        }),
    ])

    with pytest.raises(InvestigationError):
        await investigate_case("case_1", store, client)


@pytest.mark.asyncio
async def test_runs_out_of_iterations_without_final_answer():
    store = _missing_bank_credit_store()
    client = FakeAnthropicClient([
        tool_use_response("t1", "get_reconciliation_case", {"case_id": "case_1"}),
        tool_use_response("t2", "get_reconciliation_case", {"case_id": "case_1"}),
        tool_use_response("t3", "get_reconciliation_case", {"case_id": "case_1"}),
    ])

    with pytest.raises(InvestigationError):
        await investigate_case("case_1", store, client, max_tool_iterations=3)
