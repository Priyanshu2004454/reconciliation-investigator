"""
The AI Investigator (sections 10-13).

Core discipline enforced here, not just asked of the model in a prompt:
  - The AI can ONLY submit a final answer by calling the `submit_investigation_result`
    tool with a schema-validated payload — we never regex/parse JSON out of free text.
  - Every evidence item in the final answer is cross-checked against IDs the AI
    ACTUALLY fetched via tool calls during this run. If the AI's answer references
    a payment/settlement/UTR it never looked up, the result is rejected before it
    ever reaches a human — this is the hallucination guard.
  - The AI never resolves a case itself. `mark_case_for_review` is the only
    mutating tool, and financial state changes only ever happen through the
    human-in-the-loop endpoints (Phase 8), never automatically from this module.
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import ValidationError

from app.ai.data_store import InvestigationDataStore
from app.ai.tools import TOOL_SPECS, execute_tool, ToolExecutionError
from app.core.config import get_settings
from app.schemas.investigation import AIInvestigationResult

SYSTEM_PROMPT = """You are the AI Investigator inside a Razorpay reconciliation product.

You investigate a SINGLE reconciliation case using the tools provided. You must:
- Only use evidence you actually retrieve via tool calls. Never invent transaction IDs,
  amounts, UTRs, fees, or bank rows that no tool call returned to you.
- If a tool returns "found: false" or an empty list, that IS a real, meaningful finding
  (e.g. "no matching bank credit exists") — state it plainly, don't treat it as a dead end
  to work around.
- Distinguish fact ("the settlement's UTR is ABC123") from inference ("this is likely a
  timing difference"). Say so explicitly when you're inferring rather than reading a fact.
- If the evidence is genuinely insufficient or contradictory, classify the case as
  NEEDS_REVIEW with requires_human_review=true, and call mark_case_for_review with a
  clear reason. Do not force an explanation you can't fully back with evidence.
- Use calculate_expected_settlement instead of doing fee/tax/refund arithmetic yourself.
- When you are done gathering evidence, call submit_investigation_result exactly once
  with your final structured finding. Do not answer in plain text.
"""

SUBMIT_TOOL: dict[str, Any] = {
    "name": "submit_investigation_result",
    "description": "Submit your final, structured investigation result. Call this exactly once, after gathering all evidence you need.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classification": {
                "type": "string",
                "enum": ["MATCHED", "EXPLAINED", "NEEDS_REVIEW", "FALSE_POSITIVE", "RESOLVED"],
            },
            "root_cause": {
                "type": "string",
                "enum": ["FEE_TAX", "REFUND", "MISSING_BANK_CREDIT", "DUPLICATE",
                         "TIMING_DIFFERENCE", "AMOUNT_MISMATCH", "UNKNOWN"],
            },
            "explanation": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_type": {"type": "string"},
                        "source_id": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["source_type", "source_id", "description"],
                },
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "recommended_action": {"type": "string"},
            "requires_human_review": {"type": "boolean"},
        },
        "required": ["classification", "root_cause", "explanation", "evidence",
                      "confidence", "recommended_action", "requires_human_review"],
    },
}


# Exception classes live in providers.py and are re-exported here for
# backward compatibility so callers that import from investigator still work.
from app.ai.providers import (  # noqa: E402
    InvestigationError,
    InvestigationTimeoutError,
    InvestigationHallucinationError,
)

__all__ = ["InvestigationError", "InvestigationTimeoutError", "InvestigationHallucinationError"]


@dataclass
class ToolCallLogEntry:
    tool_name: str
    tool_input: dict
    result_summary: str


@dataclass
class InvestigationRunResult:
    result: AIInvestigationResult
    tool_calls: list[ToolCallLogEntry] = field(default_factory=list)
    duration_ms: int = 0
    raw_final_input: dict = field(default_factory=dict)
    ai_model: str = ""  # populated by providers; stored in Investigation.ai_model


def _serialize_block(block: Any) -> dict:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    raise InvestigationError(f"Unexpected content block type: {block.type}")


def _track_fetched_ids(tool_name: str, tool_result: dict, fetched: set[tuple[str, str]]) -> None:
    """Records which real (source_type, source_id) pairs this tool call actually surfaced."""
    if tool_name == "get_payment" and tool_result.get("found"):
        fetched.add(("RAZORPAY_PAYMENT", tool_result["payment"]["razorpay_payment_id"]))
    elif tool_name == "get_settlement" and tool_result.get("found"):
        s = tool_result["settlement"]
        fetched.add(("RAZORPAY_SETTLEMENT", s["razorpay_settlement_id"]))
        if s.get("utr"):
            fetched.add(("RAZORPAY_SETTLEMENT", s["utr"]))
    elif tool_name == "get_refunds":
        for r in tool_result.get("refunds", []):
            fetched.add(("RAZORPAY_REFUND", r["razorpay_refund_id"]))
    elif tool_name == "search_bank_transactions":
        for m in tool_result.get("matches", []):
            row_id = m.get("id") or m.get("reference_id") or m.get("utr")
            if row_id:
                fetched.add(("BANK_STATEMENT", row_id))
            if m.get("utr"):
                fetched.add(("BANK_STATEMENT", m["utr"]))
    elif tool_name == "get_reconciliation_case" and tool_result.get("found"):
        fetched.add(("RECONCILIATION_CASE", tool_result["case"]["id"]))


def _validate_no_hallucinated_evidence(
    result: AIInvestigationResult, fetched: set[tuple[str, str]], case_id: str
) -> None:
    for item in result.evidence:
        if item.source_id == case_id:
            continue  # referencing the case itself is always fine
        if (item.source_type, item.source_id) not in fetched:
            raise InvestigationHallucinationError(
                f"Evidence references {item.source_type}='{item.source_id}', which was never "
                "actually returned by any tool call during this investigation. Rejected."
            )


async def investigate_case(
    case_id: str,
    store: InvestigationDataStore,
    client: Any,
    max_tool_iterations: int = 12,
) -> InvestigationRunResult:
    """
    Legacy helper kept for backward compatibility with existing tests.

    `client` must expose an async `.messages.create(...)` matching the Anthropic SDK
    shape (AsyncAnthropic in production, FakeAnthropicClient in tests).  This wraps
    the old call site by constructing a temporary AnthropicAIProvider and delegating
    to its investigate() method so both paths share a single implementation.
    """
    from app.ai.providers import AnthropicAIProvider

    provider = AnthropicAIProvider(client=client)
    settings = get_settings()
    run = await provider.investigate(
        case_id=case_id,
        store=store,
        timeout_seconds=settings.AI_TIMEOUT_SECONDS,
        max_tool_iterations=max_tool_iterations,
    )
    return InvestigationRunResult(
        result=run.result,
        tool_calls=run.tool_calls,
        duration_ms=run.duration_ms,
        raw_final_input=run.raw_final_input,
        ai_model=run.ai_model,
    )
