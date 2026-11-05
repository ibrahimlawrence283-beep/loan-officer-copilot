"""Shared data models for the loan officer copilot."""
from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field


class Decision(str, Enum):
    APPROVE = "approve"
    DECLINE = "decline"
    MANUAL_REVIEW = "manual_review"


class CaseStatus(str, Enum):
    PENDING_HUMAN = "pending_human"          # blocked until an officer reviews
    CLEARED = "cleared"                      # low-risk recommendation, no extra approval needed
    CONFIRMED_BY_HUMAN = "confirmed_by_human"
    OVERRIDDEN_BY_HUMAN = "overridden_by_human"


class ExtractedField(BaseModel):
    value: Optional[Union[float, str]] = None
    confidence: float = 0.0
    raw_label: str = ""


class ExtractionResult(BaseModel):
    fields: dict[str, ExtractedField]
    missing: list[str]
    invalid: list[str] = Field(default_factory=list)
    confidence: float          # minimum confidence across required fields; 0 if anything missing/invalid
    notes: str = ""            # free-text notes from the document (treated as untrusted data)

    def values(self) -> dict[str, Union[float, str]]:
        return {k: v.value for k, v in self.fields.items() if v.value is not None}


class Reason(BaseModel):
    feature: str
    label: str
    contribution: float        # log-odds contribution relative to an average applicant
    direction: str             # "increases risk" | "reduces risk"
    value: float


class ScoreResult(BaseModel):
    approval_probability: float   # Pillar 1 predicts historical approval, not default
    risk_band: str                # low (>=60%) | medium (40-60%) | high (<40%)
    reasons: list[Reason]
    model_version: str


class PolicyHit(BaseModel):
    clause_id: str
    title: str
    text: str
    score: float


class Recommendation(BaseModel):
    decision: Decision
    summary: str
    rationale: list[str]
    citations: list[str]       # policy clause ids
    fallback_reason: Optional[str] = None


class GateResult(BaseModel):
    requires_human: bool
    reasons: list[str]
    flags: list[str] = Field(default_factory=list)


class Review(BaseModel):
    reviewer: str
    action: str                # "confirm" | "override"
    new_decision: Optional[Decision] = None
    note: str = ""


class Case(BaseModel):
    case_id: str
    status: CaseStatus
    extraction: Optional[ExtractionResult] = None
    score: Optional[ScoreResult] = None
    policy_hits: list[PolicyHit] = Field(default_factory=list)
    recommendation: Optional[Recommendation] = None
    gate: Optional[GateResult] = None
    review: Optional[Review] = None
    final_decision: Optional[Decision] = None   # only set once cleared or human-reviewed
