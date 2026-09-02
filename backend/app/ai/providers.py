"""
LLM Provider Abstraction for the AI Investigator.

Supports:
1. Google Gemini (default, Free Tier compatible: gemini-3.6-flash) via official google-genai SDK.
2. Anthropic Claude (claude-sonnet-4-6, claude-3-5-sonnet) via anthropic SDK.

Both providers share:
- The exact same system prompt and financial investigation instructions.
- The exact same tool suite (get_payment, get_settlement, search_bank_transactions, etc.).
- Multi-turn tool execution loop with hallucination guardrails.
- Structured output validation via submit_investigation_result tool.
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import ValidationError

from app.ai.data_store import InvestigationDataStore
from app.ai.tools import TOOL_SPECS, execute_tool, ToolExecutionError
from app.core.config import Settings, get_settings
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
                        "source_type": {
                            "type": "string",
                            "enum": [
                                "RAZORPAY_PAYMENT", "RAZORPAY_SETTLEMENT", "RAZORPAY_REFUND",
                                "BANK_STATEMENT", "RECONCILIATION_CASE",
                            ],
                        },
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


class InvestigationError(Exception):
    pass


class InvestigationTimeoutError(InvestigationError):
    pass


class InvestigationHallucinationError(InvestigationError):
    """Raised when the AI's final answer references evidence it never actually fetched."""


class AIProviderError(Exception):
    """
    Raised by create_message() (a generic, single-call interface used by the
    Copilot orchestrator, app/ai/copilot.py -- distinct from investigate(),
    which runs a full self-contained investigation loop). `retryable`
    signals whether the failure is transient (e.g. rate limiting) so the
    caller can pick an appropriate HTTP status.
    """
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class _NormalizedBlock:
    type: str
    text: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    input: Optional[dict] = None
    raw_part: Any = None


@dataclass
class _NormalizedResponse:
    content: list[_NormalizedBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"
    raw_content: Any = None


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
    ai_model: str = ""


def track_fetched_ids(tool_name: str, tool_result: dict, fetched: set[tuple[str, str]]) -> None:
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
        case = tool_result["case"]
        fetched.add(("RECONCILIATION_CASE", case["id"]))
        # The case lookup itself surfaces linked settlement/payment IDs as genuinely
        # returned values — these must count as "fetched" even if the AI cites them
        # without a separate get_settlement/get_payment call, otherwise real (non-
        # hallucinated) evidence gets wrongly rejected.
        if case.get("razorpay_settlement_id"):
            fetched.add(("RAZORPAY_SETTLEMENT", case["razorpay_settlement_id"]))
        if case.get("razorpay_payment_id"):
            fetched.add(("RAZORPAY_PAYMENT", case["razorpay_payment_id"]))
        for pid in (case.get("payment_ids") or []):
            fetched.add(("RAZORPAY_PAYMENT", pid))


def validate_no_hallucinated_evidence(
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


class BaseAIProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
    async def investigate(
        self,
        case_id: str,
        store: InvestigationDataStore,
        timeout_seconds: Optional[int] = None,
        max_tool_iterations: int = 12,
    ) -> InvestigationRunResult:
        pass

    @abstractmethod
    async def create_message(
        self, system: str, tools: list[dict], messages: list[dict], max_tokens: int,
    ) -> Any:
        """
        Makes one raw model call for generic multi-turn tool-use callers
        (currently the Copilot orchestrator, app/ai/copilot.py). Returns a
        response exposing `.content` (blocks with `.type`, and `.text` or
        `.id`/`.name`/`.input`) and `.stop_reason` -- the Anthropic SDK
        shape. Distinct from investigate(), which is a complete, self-
        contained investigation loop with its own hallucination guard.
        """
        pass


class AnthropicAIProvider(BaseAIProvider):
    def __init__(self, client: Any, model: Optional[str] = None):
        self.client = client
        self._model = model or "claude-sonnet-4-6"

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    def _serialize_block(self, block: Any) -> dict:
        if block.type == "text":
            return {"type": "text", "text": block.text}
        if block.type == "tool_use":
            return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
        raise InvestigationError(f"Unexpected content block type: {block.type}")

    async def investigate(
        self,
        case_id: str,
        store: InvestigationDataStore,
        timeout_seconds: Optional[int] = None,
        max_tool_iterations: int = 12,
    ) -> InvestigationRunResult:
        settings = get_settings()
        timeout = timeout_seconds or settings.AI_TIMEOUT_SECONDS
        start = time.monotonic()

        tools = TOOL_SPECS + [SUBMIT_TOOL]
        messages: list[dict] = [
            {"role": "user", "content": f"Investigate reconciliation case_id={case_id}. "
                                         f"Start by calling get_reconciliation_case."}
        ]
        fetched_ids: set[tuple[str, str]] = set()
        tool_call_log: list[ToolCallLogEntry] = []

        for _ in range(max_tool_iterations):
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise InvestigationTimeoutError(
                    f"Investigation of case {case_id} exceeded {timeout}s timeout."
                )

            response = await self.client.messages.create(
                model=self._model,
                max_tokens=settings.AI_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": [self._serialize_block(b) for b in response.content]})

            if response.stop_reason != "tool_use":
                messages.append({
                    "role": "user",
                    "content": "You must call the submit_investigation_result tool with your final "
                                "structured finding — plain text answers are not accepted.",
                })
                continue

            tool_result_blocks = []
            final_input: Optional[dict] = None

            for block in response.content:
                if block.type != "tool_use":
                    continue

                if block.name == "submit_investigation_result":
                    final_input = block.input
                    continue

                try:
                    result = await execute_tool(block.name, block.input, store, allowed_case_id=case_id)
                    track_fetched_ids(block.name, result, fetched_ids)
                    tool_call_log.append(ToolCallLogEntry(
                        tool_name=block.name, tool_input=block.input,
                        result_summary=json.dumps(result)[:300],
                    ))
                    content_str = json.dumps(result)
                except ToolExecutionError as exc:
                    content_str = json.dumps({"error": str(exc)})

                tool_result_blocks.append({
                    "type": "tool_result", "tool_use_id": block.id, "content": content_str,
                })

            if final_input is not None:
                try:
                    parsed = AIInvestigationResult.model_validate(final_input)
                except ValidationError as exc:
                    raise InvestigationError(f"AI returned an invalid structured result: {exc}") from exc

                validate_no_hallucinated_evidence(parsed, fetched_ids, case_id)

                return InvestigationRunResult(
                    result=parsed,
                    tool_calls=tool_call_log,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    raw_final_input=final_input,
                    ai_model=self._model,
                )

            if tool_result_blocks:
                messages.append({"role": "user", "content": tool_result_blocks})

        raise InvestigationError(
            f"Investigation of case {case_id} did not reach a final answer within "
            f"{max_tool_iterations} tool-use iterations."
        )

    async def create_message(
        self, system: str, tools: list[dict], messages: list[dict], max_tokens: int,
    ) -> Any:
        """
        Raw single-call interface for the Copilot orchestrator. The Anthropic
        SDK response is already shaped exactly as that orchestrator expects
        (`.content` blocks, `.stop_reason`) -- no normalization needed,
        unlike GeminiAIProvider.create_message() below.
        """
        try:
            return await self.client.messages.create(
                model=self._model, max_tokens=max_tokens, system=system, tools=tools, messages=messages,
            )
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            raise AIProviderError(str(exc), retryable=(status_code == 429)) from exc


class GeminiAIProvider(BaseAIProvider):
    """
    Official Google GenAI SDK integration for the AI Investigator.
    Uses currently supported Gemini models with Free Tier availability (e.g. gemini-3.6-flash).
    """

    def __init__(self, client: Any, model: Optional[str] = None):
        self.client = client
        self._model = model or "gemini-3.6-flash"
        self._tools_config = self._build_gemini_tools()

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def _build_gemini_tools(self) -> list[Any]:
        try:
            from google.genai import types
            declarations = []
            for t in TOOL_SPECS + [SUBMIT_TOOL]:
                declarations.append(
                    types.FunctionDeclaration(
                        name=t["name"],
                        description=t["description"],
                        parameters=t["input_schema"],
                    )
                )
            return [types.Tool(function_declarations=declarations)]
        except Exception:
            return TOOL_SPECS + [SUBMIT_TOOL]

    async def investigate(
        self,
        case_id: str,
        store: InvestigationDataStore,
        timeout_seconds: Optional[int] = None,
        max_tool_iterations: int = 12,
    ) -> InvestigationRunResult:
        settings = get_settings()
        timeout = timeout_seconds or settings.AI_TIMEOUT_SECONDS
        start = time.monotonic()

        try:
            from google.genai import types
        except ImportError:
            types = None

        prompt_text = (
            f"Investigate reconciliation case_id={case_id}. "
            f"Start by calling get_reconciliation_case."
        )

        if types:
            contents: list[Any] = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt_text)],
                )
            ]
        else:
            contents = [{"role": "user", "parts": [{"text": prompt_text}]}]

        fetched_ids: set[tuple[str, str]] = set()
        tool_call_log: list[ToolCallLogEntry] = []

        for _ in range(max_tool_iterations):
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise InvestigationTimeoutError(
                    f"Investigation of case {case_id} exceeded {timeout}s timeout."
                )

            if types:
                thinking_cfg = types.ThinkingConfig(thinking_budget=0) if hasattr(types, "ThinkingConfig") else None
                config = types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=self._tools_config,
                    temperature=0.0,
                    max_output_tokens=settings.AI_MAX_TOKENS,
                    thinking_config=thinking_cfg,
                )
                response = await self.client.aio.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
            else:
                response = await self.client.aio.models.generate_content(
                    model=self._model,
                    contents=contents,
                )

            if not getattr(response, "candidates", None) or len(response.candidates) == 0:
                raise InvestigationError("Gemini API returned an empty candidate response.")

            candidate = response.candidates[0]
            candidate_content = candidate.content

            contents.append(candidate_content)

            function_calls = getattr(response, "function_calls", None)
            if function_calls is None and hasattr(candidate_content, "parts"):
                function_calls = [
                    p.function_call for p in candidate_content.parts
                    if getattr(p, "function_call", None) is not None
                ]

            if not function_calls:
                nudge_text = (
                    "You must call the submit_investigation_result tool with your final "
                    "structured finding — plain text answers are not accepted."
                )
                if types:
                    contents.append(
                        types.Content(role="user", parts=[types.Part.from_text(text=nudge_text)])
                    )
                else:
                    contents.append({"role": "user", "parts": [{"text": nudge_text}]})
                continue

            function_response_parts: list[Any] = []
            final_input: Optional[dict] = None

            for call in function_calls:
                call_name = getattr(call, "name", "")
                call_args = getattr(call, "args", {})
                if hasattr(call_args, "model_dump"):
                    call_args = call_args.model_dump()
                elif not isinstance(call_args, dict):
                    call_args = dict(call_args)

                if call_name == "submit_investigation_result":
                    final_input = call_args
                    continue

                try:
                    result = await execute_tool(call_name, call_args, store, allowed_case_id=case_id)
                    track_fetched_ids(call_name, result, fetched_ids)
                    tool_call_log.append(ToolCallLogEntry(
                        tool_name=call_name, tool_input=call_args,
                        result_summary=json.dumps(result)[:300],
                    ))
                except ToolExecutionError as exc:
                    result = {"error": str(exc)}

                if types:
                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=call_name,
                            response={"result": result},
                        )
                    )
                else:
                    function_response_parts.append({
                        "function_response": {"name": call_name, "response": {"result": result}}
                    })

            if final_input is not None:
                try:
                    parsed = AIInvestigationResult.model_validate(final_input)
                except ValidationError as exc:
                    raise InvestigationError(f"AI returned an invalid structured result: {exc}") from exc

                validate_no_hallucinated_evidence(parsed, fetched_ids, case_id)

                return InvestigationRunResult(
                    result=parsed,
                    tool_calls=tool_call_log,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    raw_final_input=final_input,
                    ai_model=self._model,
                )

            if function_response_parts:
                if types:
                    contents.append(
                        types.Content(role="user", parts=function_response_parts)
                    )
                else:
                    contents.append({"role": "user", "parts": function_response_parts})

        raise InvestigationError(
            f"Investigation of case {case_id} did not reach a final answer within "
            f"{max_tool_iterations} tool-use iterations."
        )

    def _build_gemini_tools_from_specs(self, tool_specs: list[dict]) -> list[Any]:
        """
        Builds Gemini function-declaration tools from a generic, Anthropic-
        shaped tool spec list (name/description/input_schema). Used by
        create_message() for the Copilot's own tool set, which differs from
        the Investigator's self._tools_config built once at __init__ time.
        """
        try:
            from google.genai import types
            declarations = [
                types.FunctionDeclaration(
                    name=t["name"], description=t["description"], parameters=t["input_schema"],
                )
                for t in tool_specs
            ]
            return [types.Tool(function_declarations=declarations)]
        except Exception:
            return tool_specs

    def _anthropic_messages_to_gemini_contents(self, messages: list[dict]) -> list[Any]:
        """Converts the Anthropic-shaped message list the Copilot orchestrator
        builds (app/ai/copilot.py) into Gemini's `contents` format."""
        try:
            from google.genai import types
        except ImportError:
            types = None

        contents: list[Any] = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            content = m["content"]
            parts: list[Any] = []

            if isinstance(content, str):
                parts.append(types.Part.from_text(text=content) if types else {"text": content})
            else:
                for block in content:
                    raw_part = block.get("raw_part") if isinstance(block, dict) else getattr(block, "raw_part", None)
                    if raw_part is not None and types:
                        parts.append(raw_part)
                        continue

                    btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                    if btype == "text":
                        text = block.get("text") if isinstance(block, dict) else block.text
                        parts.append(types.Part.from_text(text=text) if types else {"text": text})
                    elif btype == "tool_use":
                        name = block.get("name") if isinstance(block, dict) else block.name
                        args = block.get("input") if isinstance(block, dict) else block.input
                        if types:
                            parts.append(types.Part.from_function_call(name=name, args=args or {}))
                        else:
                            parts.append({"function_call": {"name": name, "args": args or {}}})
                    elif btype == "tool_result":
                        raw = block.get("content") if isinstance(block, dict) else getattr(block, "content", None)
                        try:
                            result_obj = json.loads(raw) if isinstance(raw, str) else raw
                        except (TypeError, ValueError):
                            result_obj = {"result": raw}
                        name = (
                            (block.get("tool_name") if isinstance(block, dict) else getattr(block, "tool_name", None))
                            or (block.get("name") if isinstance(block, dict) else getattr(block, "name", None))
                            or (block.get("tool_use_id") if isinstance(block, dict) else getattr(block, "tool_use_id", None))
                            or "tool_result"
                        )
                        if types:
                            parts.append(types.Part.from_function_response(name=name, response={"result": result_obj}))
                        else:
                            parts.append({"function_response": {"name": name, "response": {"result": result_obj}}})

            if types:
                contents.append(types.Content(role=role, parts=parts))
            else:
                contents.append({"role": role, "parts": parts})
        return contents

    async def create_message(
        self, system: str, tools: list[dict], messages: list[dict], max_tokens: int,
    ) -> Any:
        """
        Makes one raw Gemini call and normalizes the response into the same
        `.content` / `.stop_reason` shape the Copilot orchestrator
        (app/ai/copilot.py) already expects from the Anthropic SDK, so its
        tool-use loop and grounding guard work unmodified for either provider.
        """
        try:
            from google.genai import types
        except ImportError:
            types = None

        contents = self._anthropic_messages_to_gemini_contents(messages)
        gemini_tools = self._build_gemini_tools_from_specs(tools)

        try:
            if types:
                config = types.GenerateContentConfig(
                    system_instruction=system,
                    tools=gemini_tools,
                    temperature=0.0,
                    max_output_tokens=max_tokens,
                )
                response = await self.client.aio.models.generate_content(
                    model=self._model, contents=contents, config=config,
                )
            else:
                response = await self.client.aio.models.generate_content(
                    model=self._model, contents=contents,
                )
        except Exception as exc:
            status_code = getattr(exc, "status_code", getattr(exc, "code", None))
            raise AIProviderError(str(exc), retryable=(status_code in (429, 503))) from exc

        if not getattr(response, "candidates", None):
            raise AIProviderError("Gemini API returned an empty candidate response.", retryable=False)

        candidate_content = response.candidates[0].content
        blocks: list[_NormalizedBlock] = []

        for p in getattr(candidate_content, "parts", []):
            if getattr(p, "text", None):
                blocks.append(_NormalizedBlock(type="text", text=p.text, raw_part=p))
            elif getattr(p, "function_call", None):
                fc = p.function_call
                args = getattr(fc, "args", {})
                if hasattr(args, "model_dump"):
                    args = args.model_dump()
                elif not isinstance(args, dict):
                    args = dict(args)
                blocks.append(_NormalizedBlock(
                    type="tool_use",
                    id=getattr(fc, "name", "call"),
                    name=getattr(fc, "name", ""),
                    input=args,
                    raw_part=p,
                ))

        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        return _NormalizedResponse(content=blocks, stop_reason=stop_reason, raw_content=candidate_content)


