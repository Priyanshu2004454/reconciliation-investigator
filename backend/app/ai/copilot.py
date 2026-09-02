"""
AI Copilot orchestrator. Structurally the same tool-use discipline as
app/ai/investigator.py (same AIProviderClient interface, same "final answer
only via a submit tool" pattern for reliable structured output) but
generalized for open-ended, multi-turn conversation instead of a single
case investigation.

Grounding guarantee: the Copilot can only reference case_ids/run_ids that a
tool call actually returned during this conversation turn. Anything else in
its final answer is text-only commentary, never a specific ID or amount
that wasn't tool-verified.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Optional
import json

from app.ai.copilot_tools import COPILOT_TOOL_SPECS, CopilotDataStore, execute_copilot_tool, CopilotToolExecutionError
from app.core.config import get_settings

SYSTEM_PROMPT = """You are the AI Copilot inside a Razorpay reconciliation product. You answer
questions about the merchant's real reconciliation data using the tools provided.

Rules:
- Only state facts (case IDs, amounts, settlement IDs, statuses) that a tool call actually
  returned in this conversation. Never invent or guess an ID or amount.
- If you cannot find something with the tools, say so plainly -- do not make it up.
- Prefer search_cases for "what needs attention" / "biggest mismatch" / "cases above X"
  questions -- it already sorts by financial impact.
- Use get_case for "explain case X" questions -- it includes the latest AI investigation.
- Keep your answer text short (1-2 sentences). If you have a list of cases or categories to
  show, put them in the `insights` or `case_refs` field of submit_response instead of writing
  them out as prose.
- When you are done, call submit_response exactly once with your final answer. Do not answer
  in plain text.
"""

SUBMIT_TOOL: dict[str, Any] = {
    "name": "submit_response",
    "description": "Submit your final answer to the user. Call this exactly once when you're done gathering data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "A short (1-2 sentence) answer."},
            "insights": {
                "type": "array",
                "description": "Optional compact category breakdowns to show as cards, e.g. mismatch categories.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "count": {"type": "integer"},
                        "amount": {"type": "number"},
                    },
                    "required": ["title", "count", "amount"],
                },
            },
            "case_refs": {
                "type": "array",
                "description": "Optional specific cases to link to, each must be a case_id a tool actually returned.",
                "items": {
                    "type": "object",
                    "properties": {
                        "case_id": {"type": "string"},
                        "label": {"type": "string", "description": "Short display label, e.g. the settlement ID."},
                    },
                    "required": ["case_id", "label"],
                },
            },
        },
        "required": ["text"],
    },
}


class CopilotError(Exception):
    pass


class CopilotTimeoutError(CopilotError):
    pass


class CopilotGroundingError(CopilotError):
    """Raised when the final answer references a case_id no tool call actually returned."""


@dataclass
class CopilotSource:
    tool_name: str
    summary: str


@dataclass
class CopilotResult:
    text: str
    insights: list[dict] = field(default_factory=list)
    case_refs: list[dict] = field(default_factory=list)
    sources: list[CopilotSource] = field(default_factory=list)
    duration_ms: int = 0


def _serialize_block(block: Any) -> dict:
    if block.type == "text":
        return {"type": "text", "text": block.text, "raw_part": getattr(block, "raw_part", None)}
    if block.type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
            "raw_part": getattr(block, "raw_part", None),
        }
    raise CopilotError(f"Unexpected content block type: {block.type}")


async def run_copilot_turn(
    message: str,
    history: list[dict],
    store: CopilotDataStore,
    client: Any,
    max_tool_iterations: int = 8,
) -> CopilotResult:
    """
    `history` is [{"role": "user"|"assistant", "text": str}, ...] from prior
    turns in this Copilot session -- the frontend keeps and resends it,
    the same way any stateless chat API works.
    """
    settings = get_settings()
    start = time.monotonic()

    tools = COPILOT_TOOL_SPECS + [SUBMIT_TOOL]
    messages: list[dict] = [{"role": h["role"], "content": h["text"]} for h in history]
    messages.append({"role": "user", "content": message})

    known_case_ids: set[str] = set()
    id_to_uuid: dict[str, str] = {}
    sources: list[CopilotSource] = []
    last_text: str = ""

    for iteration in range(max_tool_iterations):
        if time.monotonic() - start > settings.AI_TIMEOUT_SECONDS:
            raise CopilotTimeoutError("Copilot response took too long. Please try again.")

        if hasattr(client, "create_message"):
            response = await client.create_message(
                system=SYSTEM_PROMPT, tools=tools, messages=messages, max_tokens=settings.AI_MAX_TOKENS,
            )
        elif hasattr(client, "messages") and hasattr(client.messages, "create"):
            response = await client.messages.create(
                model=settings.AI_MODEL, system=SYSTEM_PROMPT, tools=tools, messages=messages, max_tokens=settings.AI_MAX_TOKENS,
            )
        else:
            raise CopilotError(f"Unsupported AI client type: {type(client)}")

        messages.append({"role": "assistant", "content": [_serialize_block(b) for b in response.content]})

        # Extract any plain text emitted
        current_text = ""
        for b in response.content:
            if getattr(b, "type", None) == "text" and getattr(b, "text", None):
                current_text += b.text
        if current_text:
            last_text = current_text

        if response.stop_reason != "tool_use":
            # If the model already gathered data via tools and provided a text answer, accept it!
            if sources and current_text:
                return CopilotResult(
                    text=current_text,
                    sources=sources,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )

            messages.append({
                "role": "user",
                "content": "Call submit_response with your final answer -- plain text isn't accepted.",
            })
            continue

        tool_result_blocks = []
        final_input: Optional[dict] = None

        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "submit_response":
                final_input = block.input
                continue
            try:
                result = await execute_copilot_tool(block.name, block.input, store)
                if block.name == "search_cases":
                    for c in result.get("cases", []):
                        cid = c.get("case_id", "")
                        sid = c.get("razorpay_settlement_id", "")
                        if cid:
                            known_case_ids.add(cid)
                            id_to_uuid[cid] = cid
                        if sid:
                            known_case_ids.add(sid)
                            if cid:
                                id_to_uuid[sid] = cid
                    sources.append(CopilotSource(block.name, f"{result.get('count', 0)} cases matched"))
                elif block.name == "get_case" and result.get("found"):
                    case_data = result.get("case", {})
                    cid = case_data.get("case_id", "")
                    sid = case_data.get("razorpay_settlement_id", "")
                    if cid:
                        known_case_ids.add(cid)
                        id_to_uuid[cid] = cid
                    if sid:
                        known_case_ids.add(sid)
                        if cid:
                            id_to_uuid[sid] = cid
                    sources.append(CopilotSource(block.name, f"Case {sid or cid[:8]}"))
                elif block.name == "list_runs":
                    sources.append(CopilotSource(block.name, f"{result.get('count', 0)} runs"))
                elif block.name == "get_dashboard_summary":
                    sources.append(CopilotSource(block.name, "dashboard summary"))
                content_str = json.dumps(result)
            except CopilotToolExecutionError as exc:
                content_str = json.dumps({"error": str(exc)})

            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "tool_name": block.name,
                "content": content_str,
            })

        if final_input is not None:
            raw_case_refs = final_input.get("case_refs") or []
            normalized_case_refs = []
            for ref in raw_case_refs:
                ref_id = ref.get("case_id")
                if ref_id not in known_case_ids:
                    raise CopilotGroundingError(
                        f"Response referenced case_id '{ref_id}' that was never returned by a tool call."
                    )
                # Map settlement ID to real case UUID so frontend Link works
                mapped_uuid = id_to_uuid.get(ref_id, ref_id)
                normalized_case_refs.append({
                    "case_id": mapped_uuid,
                    "label": ref.get("label") or ref_id,
                })

            return CopilotResult(
                text=final_input.get("text", "") or last_text,
                insights=final_input.get("insights") or [],
                case_refs=normalized_case_refs,
                sources=sources,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        if tool_result_blocks:
            messages.append({"role": "user", "content": tool_result_blocks})

    if last_text and sources:
        return CopilotResult(
            text=last_text,
            sources=sources,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    raise CopilotError("Could not produce an answer within the allotted tool-call budget.")

