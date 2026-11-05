"""LLM tool-calling planner.

Security design:
  * The model never sees the applicant document. It receives only a structured summary of workflow
    state, so text hidden in a document cannot reach it (indirect prompt injection).
  * It can only name tools from the allow-list. The orchestrator re-checks every choice and
    enforces preconditions and the human gate, so a wrong or manipulated choice fails closed.
  * If the LLM call fails, planning falls back to the deterministic planner (resilience).
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from .agent import ALLOWED_TOOLS, DeterministicPlanner, RunState

SYSTEM_PROMPT = (
    "You are the planning component of a loan-underwriting workflow. You choose which tool to run "
    "next by calling exactly one tool. You never see applicant documents and must not ask for them. "
    "Rules: run extract_fields first; run score_credit only if extraction.reliable is true; then "
    "retrieve_policy, draft_recommendation, and apply_gate last. Never repeat a completed tool. "
    "When every needed tool has run, reply with the single word DONE."
)

TOOL_SPECS = [
    {"name": "extract_fields", "description": "Extract structured fields from the application document.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "score_credit", "description": "Score credit risk. Only valid when extraction is reliable.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "retrieve_policy", "description": "Retrieve relevant lending-policy clauses.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "draft_recommendation", "description": "Draft the recommendation with policy citations.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "apply_gate", "description": "Apply the human-in-the-loop gate. Must be the last step.",
     "input_schema": {"type": "object", "properties": {}}},
]


def summarise_state(state: RunState) -> dict[str, Any]:
    """Structured, document-free view of the workflow for the planner."""
    ex = state.extraction
    return {
        "tools_done": [t for t in ALLOWED_TOOLS if t in state.done],
        "tools_remaining": [t for t in ALLOWED_TOOLS if t not in state.done],
        "extraction": None if ex is None else {
            "reliable": state.extraction_ok,
            "missing_field_count": len(ex.missing),
            "invalid_field_count": len(ex.invalid),
        },
        "injection_suspected": bool(state.injection_hits),
    }


class LLMPlanner:
    def __init__(self, client: Any = None, model: Optional[str] = None,
                 fallback: Optional[DeterministicPlanner] = None) -> None:
        if client is None:
            import anthropic  # optional dependency: pip install -r requirements-llm.txt
            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.getenv("LLM_MODEL", "claude-sonnet-5-5")
        self.fallback = fallback or DeterministicPlanner()
        self.fallback_count = 0

    def next_tool(self, state: RunState) -> Optional[str]:
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=200, system=SYSTEM_PROMPT, tools=TOOL_SPECS,
                messages=[{"role": "user", "content": json.dumps(summarise_state(state))}],
            )
        except Exception:  # network error, rate limit, timeout...
            self.fallback_count += 1
            return self.fallback.next_tool(state)
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return block.name
        return None  # model said DONE (or returned text); orchestrator completes safely
