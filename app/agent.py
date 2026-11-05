"""Orchestrator: a bounded tool-using agent with a mandatory human-in-the-loop gate.

The planner chooses which tool to call next from a fixed allow-list. The default planner is
deterministic; an LLM tool-calling planner plugs into the same interface. The orchestrator, not
the planner, enforces the rules: unknown tools are rejected, steps are capped, and the gate
always runs before a case can leave the agent.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Protocol

from .audit import AuditLog
from .credit_model import CreditScorer
from .extraction import extract
from .guardrails import CONFIDENCE_MIN, detect_injection, evaluate_gate
from .policy_rag import PolicyIndex
from .schemas import (Case, CaseStatus, Decision, ExtractionResult, GateResult, PolicyHit,
                      Recommendation, Review, ScoreResult)

ALLOWED_TOOLS = ["extract_fields", "score_credit", "retrieve_policy", "draft_recommendation", "apply_gate"]
MAX_STEPS = 8


class ReviewError(ValueError):
    pass


@dataclass
class RunState:
    text: str
    extraction: Optional[ExtractionResult] = None
    score: Optional[ScoreResult] = None
    policy_hits: list[PolicyHit] = field(default_factory=list)
    recommendation: Optional[Recommendation] = None
    gate: Optional[GateResult] = None
    injection_hits: list[str] = field(default_factory=list)
    out_of_range: list[str] = field(default_factory=list)
    done: set[str] = field(default_factory=set)

    @property
    def extraction_ok(self) -> bool:
        return self.extraction is not None and self.extraction.confidence >= CONFIDENCE_MIN


class Planner(Protocol):
    def next_tool(self, state: RunState) -> Optional[str]: ...


class DeterministicPlanner:
    def next_tool(self, state: RunState) -> Optional[str]:
        for tool in ALLOWED_TOOLS:
            if tool in state.done:
                continue
            if tool == "score_credit" and state.extraction is not None and not state.extraction_ok:
                continue  # fallback path: never score on unreliable extraction
            return tool
        return None


def instalment_ratio(v: dict) -> float:
    """Monthly instalment (loan / term) as a share of gross monthly income."""
    return float(v["loan_amount_kes"]) / float(v["loan_term_months"]) / float(v["monthly_income_kes"])


def decide(values: dict, score: ScoreResult) -> tuple[Decision, list[str], list[str]]:
    """Policy rules applied to extracted values and the model score. Returns decision, rationale, clause ids."""
    ratio = instalment_ratio(values)
    p = score.approval_probability
    rationale: list[str] = []
    cites: list[str] = []
    decline = review = False

    if ratio > 0.5:
        decline = True; cites.append("LP-01")
        rationale.append(f"Monthly instalment is {ratio:.0%} of income, above the 50% limit.")
    elif ratio > 0.35:
        review = True; cites.append("LP-01")
        rationale.append(f"Monthly instalment is {ratio:.0%} of income, in the 35-50% review band.")
    if values["late_payments_12m"] >= 3:
        decline = True; cites.append("LP-02")
        rationale.append(f"{int(values['late_payments_12m'])} late payments in the last 12 months.")
    if values["employment_years"] < 0.5:
        review = True; cites.append("LP-03")
        rationale.append("Less than 6 months in current employment.")
    if values["loan_amount_kes"] > 1_000_000:
        cites.append("LP-04")
        rationale.append("Loan exceeds the KES 1,000,000 approval-authority threshold.")
    if p < 0.40:
        decline = True
        rationale.append(f"Model approval probability is low ({p:.0%}).")
    elif p < 0.60:
        review = True; cites.append("LP-08")
        rationale.append(f"Model approval probability is borderline ({p:.0%}).")

    if decline:
        decision = Decision.DECLINE
        cites += ["LP-05", "LP-06"]
    elif review:
        decision = Decision.MANUAL_REVIEW
    else:
        decision = Decision.APPROVE
        rationale.append(f"Within policy limits; model approval probability {p:.0%}.")
    return decision, rationale, list(dict.fromkeys(cites))


class Orchestrator:
    def __init__(self, scorer: CreditScorer, audit: AuditLog | None = None,
                 policy: PolicyIndex | None = None, planner: Planner | None = None) -> None:
        self.scorer = scorer
        self.audit = audit or AuditLog()
        self.policy = policy or PolicyIndex()
        self.planner = planner or DeterministicPlanner()
        self.cases: dict[str, Case] = {}

    # ---- tools -------------------------------------------------------------------------
    def _extract_fields(self, s: RunState) -> dict:
        s.extraction = extract(s.text)
        s.injection_hits = detect_injection(s.text)
        return {"confidence": s.extraction.confidence, "missing": s.extraction.missing,
                "invalid": s.extraction.invalid, "injection_hits": len(s.injection_hits)}

    def _score_credit(self, s: RunState) -> dict:
        values = s.extraction.values()
        s.score = self.scorer.predict(values)
        s.out_of_range = self.scorer.out_of_range(values)
        return {"approval_probability": s.score.approval_probability, "band": s.score.risk_band,
                "model_version": s.score.model_version, "out_of_range": s.out_of_range}

    def _retrieve_policy(self, s: RunState) -> dict:
        terms = ["human oversight adverse decision explainability"]
        if s.extraction_ok:
            v = s.extraction.values()
            if instalment_ratio(v) > 0.35: terms.append("monthly instalment income affordability")
            if v["late_payments_12m"] >= 3: terms.append("late payments repayment history declined")
            if v["employment_years"] < 0.5: terms.append("employment stability")
            if v["loan_amount_kes"] > 1_000_000: terms.append("approval authority loans")
            if s.score is not None and s.score.risk_band != "low": terms.append("borderline model score")
        else:
            terms.append("manual review")
        s.policy_hits = self.policy.search(" ".join(terms), k=5)
        return {"clauses": [h.clause_id for h in s.policy_hits]}

    def _draft_recommendation(self, s: RunState) -> dict:
        if not s.extraction_ok or s.score is None:
            why = "invalid values" if s.extraction and s.extraction.invalid else "missing or low-confidence fields"
            s.recommendation = Recommendation(
                decision=Decision.MANUAL_REVIEW,
                summary="Automated assessment not possible; route to a loan officer.",
                rationale=[f"Document extraction unreliable ({why}); no credit score was produced."],
                citations=[c for c in ("LP-06",) if self.policy.get(c)],
                fallback_reason="extraction_unreliable")
            return {"decision": "manual_review", "fallback": True}
        decision, rationale, cites = decide(s.extraction.values(), s.score)
        top = "; ".join(f"{r.label} ({r.direction})" for r in s.score.reasons[:3])
        rationale.append(f"Main model drivers: {top}.")
        cites = [c for c in cites if self.policy.get(c)]  # citations must resolve to real clauses
        s.recommendation = Recommendation(
            decision=decision, rationale=rationale, citations=cites,
            summary=f"Recommend {decision.value.replace('_', ' ')} (risk band {s.score.risk_band}).")
        return {"decision": decision.value, "citations": cites}

    def _apply_gate(self, s: RunState) -> dict:
        v = s.extraction.values() if s.extraction else {}
        s.gate = evaluate_gate(
            decision=s.recommendation.decision, loan_amount=v.get("loan_amount_kes"),
            extraction_confidence=s.extraction.confidence if s.extraction else 0.0,
            risk_band=s.score.risk_band if s.score else None, injection_hits=s.injection_hits,
            out_of_range=s.out_of_range)
        return {"requires_human": s.gate.requires_human, "flags": s.gate.flags}

    # ---- run ---------------------------------------------------------------------------
    def run_case(self, text: str) -> Case:
        case_id = "CASE-" + uuid.uuid4().hex[:8].upper()
        # data minimisation (LP-07): the audit log stores a hash of the document, not its contents
        self.audit.append(case_id, "system", "case_created",
                          {"doc_sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text)})
        state = RunState(text=text)
        tools = {"extract_fields": self._extract_fields, "score_credit": self._score_credit,
                 "retrieve_policy": self._retrieve_policy,
                 "draft_recommendation": self._draft_recommendation, "apply_gate": self._apply_gate}
        for _ in range(MAX_STEPS):
            name = self.planner.next_tool(state)
            if name is None:
                break
            if name not in tools or name in state.done:
                self.audit.append(case_id, "agent", "tool_rejected", {"tool": name, "why": "unknown_or_repeated"})
                break
            if name == "score_credit" and not state.extraction_ok:
                # precondition enforced here, not trusted to the planner: never score unreliable extraction
                self.audit.append(case_id, "agent", "tool_rejected", {"tool": name, "why": "precondition"})
                continue
            t0 = time.perf_counter()
            result = tools[name](state)
            state.done.add(name)
            self.audit.append(case_id, "agent", "tool_call",
                              {"tool": name, "ms": round((time.perf_counter() - t0) * 1000, 2), **result})
        # the gate must always run, whatever the planner did
        if state.extraction is None:
            self._extract_fields(state)
        if state.recommendation is None:
            self._draft_recommendation(state)
        if state.gate is None:
            self._apply_gate(state)
            self.audit.append(case_id, "system", "gate_enforced", {"reason": "planner skipped gate"})
        if "outside_training_range" in state.gate.flags and "LP-08" not in state.recommendation.citations \
                and self.policy.get("LP-08"):
            state.recommendation.citations.append("LP-08")
        have = {h.clause_id for h in state.policy_hits}
        for cid in state.recommendation.citations:
            hit = self.policy.get(cid)
            if hit and cid not in have:
                state.policy_hits.append(hit)

        cleared = not state.gate.requires_human
        case = Case(
            case_id=case_id, status=CaseStatus.CLEARED if cleared else CaseStatus.PENDING_HUMAN,
            extraction=state.extraction, score=state.score, policy_hits=state.policy_hits,
            recommendation=state.recommendation, gate=state.gate,
            final_decision=state.recommendation.decision if cleared else None)
        self.cases[case_id] = case
        self.audit.append(case_id, "system", "gate_result", {
            "requires_human": state.gate.requires_human, "reasons": state.gate.reasons,
            "status": case.status.value})
        return case

    # ---- human review ------------------------------------------------------------------
    def review(self, case_id: str, reviewer: str, action: str,
               new_decision: Decision | None = None, note: str = "") -> Case:
        case = self.cases.get(case_id)
        if case is None:
            raise KeyError(case_id)
        if case.status != CaseStatus.PENDING_HUMAN:
            raise ReviewError("Case is not awaiting human review.")
        if not reviewer or not reviewer.strip():
            raise ReviewError("A named reviewer is required.")
        rec = case.recommendation
        if action == "confirm":
            if rec.decision == Decision.MANUAL_REVIEW:
                raise ReviewError("A manual-review recommendation needs an explicit approve or decline decision.")
            final, status = rec.decision, CaseStatus.CONFIRMED_BY_HUMAN
        elif action == "override":
            if new_decision not in (Decision.APPROVE, Decision.DECLINE):
                raise ReviewError("Override must set the decision to approve or decline.")
            if len(note.strip()) < 10:
                raise ReviewError("An override requires a written justification (at least 10 characters).")
            final, status = new_decision, CaseStatus.OVERRIDDEN_BY_HUMAN
        else:
            raise ReviewError("Action must be 'confirm' or 'override'.")
        case.review = Review(reviewer=reviewer.strip(), action=action, new_decision=new_decision, note=note)
        case.final_decision, case.status = final, status
        self.audit.append(case_id, reviewer.strip(), "human_review",
                          {"action": action, "final_decision": final.value, "note": note,
                           "agent_recommendation": rec.decision.value})
        return case
