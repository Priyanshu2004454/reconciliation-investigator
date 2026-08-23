from typing import Literal

from pydantic import BaseModel, Field, field_validator

CLASSIFICATIONS = {"MATCHED", "EXPLAINED", "NEEDS_REVIEW", "FALSE_POSITIVE", "RESOLVED"}
ROOT_CAUSES = {
    "FEE_TAX", "REFUND", "MISSING_BANK_CREDIT", "DUPLICATE",
    "TIMING_DIFFERENCE", "AMOUNT_MISMATCH", "UNKNOWN",
}


class EvidenceItem(BaseModel):
    """
    Every evidence item MUST trace back to a real tool call result the AI
    actually made during this investigation — see investigator.py's
    hallucination guard, which cross-checks source_id against IDs the AI
    genuinely fetched before accepting the final output.
    """
    source_type: str  # RecordSource value, e.g. "RAZORPAY_SETTLEMENT"
    source_id: str
    description: str


class AIInvestigationResult(BaseModel):
    classification: str
    root_cause: str
    explanation: str = Field(min_length=1)
    evidence: list[EvidenceItem]
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: str = Field(min_length=1)
    requires_human_review: bool

    @field_validator("classification")
    @classmethod
    def validate_classification(cls, v: str) -> str:
        if v not in CLASSIFICATIONS:
            raise ValueError(f"classification must be one of {CLASSIFICATIONS}, got '{v}'")
        return v

    @field_validator("root_cause")
    @classmethod
    def validate_root_cause(cls, v: str) -> str:
        if v not in ROOT_CAUSES:
            raise ValueError(f"root_cause must be one of {ROOT_CAUSES}, got '{v}'")
        return v


class InvestigationRequest(BaseModel):
    case_id: str


class InvestigationProgressStep(BaseModel):
    """Used to stream progress to the UI per section 13's checklist display."""
    label: str
    done: bool = False
