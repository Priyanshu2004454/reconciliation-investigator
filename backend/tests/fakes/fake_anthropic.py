class FakeBlock:
    def __init__(self, type: str, **kwargs):
        self.type = type
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeResponse:
    def __init__(self, content: list[FakeBlock], stop_reason: str):
        self.content = content
        self.stop_reason = stop_reason


def tool_use_response(tool_id: str, name: str, tool_input: dict) -> FakeResponse:
    return FakeResponse(
        content=[FakeBlock("tool_use", id=tool_id, name=name, input=tool_input)],
        stop_reason="tool_use",
    )


def text_response(text: str) -> FakeResponse:
    return FakeResponse(content=[FakeBlock("text", text=text)], stop_reason="end_turn")


class _FakeMessages:
    def __init__(self, scripted_responses: list[FakeResponse]):
        self._responses = list(scripted_responses)
        self.call_count = 0

    async def create(self, **kwargs):
        self.call_count += 1
        if not self._responses:
            raise AssertionError("FakeAnthropicClient ran out of scripted responses")
        return self._responses.pop(0)


class FakeAnthropicClient:
    """Duck-types the parts of anthropic.AsyncAnthropic our investigator uses."""

    def __init__(self, scripted_responses: list[FakeResponse]):
        self.messages = _FakeMessages(scripted_responses)
