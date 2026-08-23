import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class EvidenceOut(BaseModel):
    source_type: str
    source_id: str
    description: str


class InvestigationOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    classification: str
    root_cause: str
    explanation: str
    confidence: float
    recommended_action: str
    requires_human_review: bool
    human_decision: Optional[str] = None
    human_notes: Optional[str] = None
    evidence: list[EvidenceOut] = []
    created_at: datetime

    class Config:
        from_attributes = True


class HumanDecisionRequest(BaseModel):
    decision: Literal["RESOLVED", "NEEDS_REVIEW", "REJECTED"]
    notes: Optional[str] = None
