from typing import Literal, Optional

from pydantic import BaseModel


class CopilotHistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class CopilotChatRequest(BaseModel):
    message: str
    history: list[CopilotHistoryTurn] = []


class CopilotInsight(BaseModel):
    title: str
    count: int
    amount: float


class CopilotCaseRef(BaseModel):
    case_id: str
    label: str


class CopilotSourceOut(BaseModel):
    tool_name: str
    summary: str


class CopilotChatResponse(BaseModel):
    text: str
    insights: list[CopilotInsight] = []
    case_refs: list[CopilotCaseRef] = []
    sources: list[CopilotSourceOut] = []
