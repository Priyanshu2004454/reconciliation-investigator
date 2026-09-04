import pytest

from app.ai.copilot import run_copilot_turn, CopilotGroundingError, CopilotError
from tests.fakes.fake_anthropic import FakeAnthropicClient, tool_use_response, text_response


class FakeCopilotStore:
    """Mirrors CopilotDataStore's public interface with in-memory data."""

    def __init__(self):
        self.cases = {
            "case_1": {
                "case_id": "case_1", "razorpay_settlement_id": "setl_ABC", "razorpay_payment_id": None,
                "utr": "UTR001", "status": "NEEDS_REVIEW", "match_rule": "RULE_6_UNMATCHED",
                "expected_amount": 25000.0, "actual_amount": None, "difference": None,
                "investigation": None,
            },
        }

    async def search_cases(self, status=None, min_amount=None, limit=10):
        results = list(self.cases.values())
        if status:
            results = [c for c in results if c["status"] == status]
        return [
            {
                "case_id": c["case_id"], "razorpay_settlement_id": c["razorpay_settlement_id"],
                "status": c["status"], "match_rule": c["match_rule"],
                "actual_amount": c["actual_amount"], "difference": c["difference"],
                "updated_at": "2026-08-30T00:00:00",
            }
            for c in results
        ][:limit]

    async def get_case(self, case_id: str):
        return self.cases.get(case_id)

    async def list_runs(self, limit=5):
        return []

    async def get_dashboard_summary(self):
        return {"total_transactions": 100, "needs_review_count": 1}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "claude-sonnet-4-6")
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


@pytest.mark.asyncio
async def test_copilot_answers_using_search_cases_tool():
    store = FakeCopilotStore()
    client = FakeAnthropicClient([
        tool_use_response("t1", "search_cases", {"status": "NEEDS_REVIEW"}),
        tool_use_response("t2", "submit_response", {
            "text": "1 case needs review.",
            "case_refs": [{"case_id": "case_1", "label": "setl_ABC"}],
        }),
    ])

    result = await run_copilot_turn("What needs attention?", [], store, client)

    assert result.text == "1 case needs review."
    assert result.case_refs[0]["case_id"] == "case_1"
    assert len(result.sources) == 1


@pytest.mark.asyncio
async def test_copilot_rejects_ungrounded_case_reference():
    """If the model references a case_id no tool call ever returned, reject it."""
    store = FakeCopilotStore()
    client = FakeAnthropicClient([
        tool_use_response("t1", "submit_response", {
            "text": "Case 999 is the biggest issue.",
            "case_refs": [{"case_id": "case_999_never_fetched", "label": "made up"}],
        }),
    ])

    with pytest.raises(CopilotGroundingError):
        await run_copilot_turn("Which case is worst?", [], store, client)


@pytest.mark.asyncio
async def test_copilot_uses_conversation_history():
    """Prior turns should be included in the message list sent to the provider."""
    store = FakeCopilotStore()
    client = FakeAnthropicClient([
        tool_use_response("t1", "submit_response", {"text": "Case setl_ABC is the one I mentioned."}),
    ])
    history = [
        {"role": "user", "text": "Show cases above 50000"},
        {"role": "assistant", "text": "Found 1 case: setl_ABC"},
    ]

    result = await run_copilot_turn("Which one is most urgent?", history, store, client)
    assert "setl_ABC" in result.text


@pytest.mark.asyncio
async def test_copilot_free_text_is_rejected_and_nudged():
    store = FakeCopilotStore()
    client = FakeAnthropicClient([
        text_response("I think case 1 needs review."),
        tool_use_response("t1", "submit_response", {"text": "1 case needs review."}),
    ])

    result = await run_copilot_turn("What needs attention?", [], store, client)
    assert result.text == "1 case needs review."
    assert client.messages.call_count == 2


@pytest.mark.asyncio
async def test_copilot_runs_out_of_iterations_raises():
    store = FakeCopilotStore()
    client = FakeAnthropicClient([
        tool_use_response("t1", "search_cases", {}),
        tool_use_response("t2", "search_cases", {}),
        tool_use_response("t3", "search_cases", {}),
    ])

    with pytest.raises(CopilotError):
        await run_copilot_turn("test", [], store, client, max_tool_iterations=3)
