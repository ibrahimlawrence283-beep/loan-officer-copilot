"""Guardrails: prompt-injection screening and the human-in-the-loop gate."""
from __future__ import annotations

import re

from .schemas import Decision, GateResult

CONFIDENCE_MIN = 0.8
APPROVAL_AUTHORITY_LIMIT = 1_000_000  # KES, policy LP-04

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|policy)",
    r"disregard\s+.{0,40}(instructions|policy|rules)",
    r"system\s+prompt",
    r"you\s+are\s+now\b",
    r"(auto[- ]?)?approve\s+(this|the)\s+(loan|application)",
    r"override\s+(the\s+)?(policy|rules|gate|review)",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def detect_injection(text: str) -> list[str]:
    """Return the patterns that matched. Document text is untrusted data, never instructions."""
    return [p.pattern for p in _COMPILED if p.search(text)]


def evaluate_gate(*, decision: Decision, loan_amount: float | None, extraction_confidence: float,
                  risk_band: str | None, injection_hits: list[str],
                  out_of_range: list[str] | None = None) -> GateResult:
    reasons: list[str] = []
    flags: list[str] = []
    if decision != Decision.APPROVE:
        reasons.append("Non-approval recommendation requires documented human review (LP-06).")
    if extraction_confidence < CONFIDENCE_MIN:
        reasons.append("Extraction confidence below threshold; manual review fallback.")
        flags.append("low_extraction_confidence")
    if injection_hits:
        reasons.append("Possible instruction-injection text found in the document.")
        flags.append("prompt_injection_suspected")
    if out_of_range:
        reasons.append("Inputs outside the range the model was trained on (" + ", ".join(out_of_range) + "); officer review required (LP-08).")
        flags.append("outside_training_range")
    if loan_amount is not None and loan_amount > APPROVAL_AUTHORITY_LIMIT:
        reasons.append("Loan above KES 1,000,000 requires credit officer approval (LP-04).")
    if risk_band is not None and risk_band != "low":
        reasons.append(f"Model risk band is {risk_band}; officer review required (LP-08).")
    return GateResult(requires_human=bool(reasons), reasons=reasons, flags=flags)
