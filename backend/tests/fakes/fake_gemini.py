"""
Fake Google Gemini client for unit tests.

Mirrors the subset of google.genai that GeminiAIProvider uses:
  client.aio.models.generate_content(model, contents, config)

Usage in tests:
  responses = [
      gemini_function_call_response("get_reconciliation_case", {"case_id": "c1"}),
      gemini_function_call_response("submit_investigation_result", {...}),
  ]
  client = FakeGeminiClient(responses)
  provider = GeminiAIProvider(client=client, model="gemini-3.6-flash")
  run = await provider.investigate("c1", store)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─── Fake SDK types ──────────────────────────────────────────────────────────

@dataclass
class FakeFunctionCall:
    name: str
    args: dict


@dataclass
class FakePart:
    function_call: FakeFunctionCall | None = None
    text: str | None = None


@dataclass
class FakeContent:
    role: str
    parts: list[FakePart] = field(default_factory=list)


@dataclass
class FakeCandidate:
    content: FakeContent


@dataclass
class FakeResponse:
    candidates: list[FakeCandidate]
    function_calls: list[FakeFunctionCall] | None = None


# ─── Helpers to build scripted responses ─────────────────────────────────────

def gemini_function_call_response(name: str, args: dict) -> FakeResponse:
    """Build a FakeResponse as if Gemini is calling function `name` with `args`."""
    fc = FakeFunctionCall(name=name, args=args)
    part = FakePart(function_call=fc)
    content = FakeContent(role="model", parts=[part])
    candidate = FakeCandidate(content=content)
    return FakeResponse(candidates=[candidate], function_calls=[fc])


def gemini_text_response(text: str) -> FakeResponse:
    """Build a FakeResponse that is plain text (model not calling any tool)."""
    part = FakePart(text=text)
    content = FakeContent(role="model", parts=[part])
    candidate = FakeCandidate(content=content)
    return FakeResponse(candidates=[candidate], function_calls=[])


# ─── Fake client ─────────────────────────────────────────────────────────────

class _FakeAioModels:
    def __init__(self, scripted_responses: list[FakeResponse]):
        self._responses = list(scripted_responses)
        self.call_count = 0

    async def generate_content(self, model: str, contents: Any, config: Any = None) -> FakeResponse:
        self.call_count += 1
        if not self._responses:
            raise AssertionError("FakeGeminiClient ran out of scripted responses")
        return self._responses.pop(0)


class _FakeAio:
    def __init__(self, scripted_responses: list[FakeResponse]):
        self.models = _FakeAioModels(scripted_responses)


class FakeGeminiClient:
    """
    Duck-types the parts of google.genai.Client that GeminiAIProvider uses.

    GeminiAIProvider calls:
        await self.client.aio.models.generate_content(model=..., contents=..., config=...)
    """

    def __init__(self, scripted_responses: list[FakeResponse]):
        self.aio = _FakeAio(scripted_responses)
