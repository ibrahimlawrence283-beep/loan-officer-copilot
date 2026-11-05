"""FastAPI service for the loan officer copilot."""
from __future__ import annotations

import os
from typing import Optional

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import Orchestrator, ReviewError
from .audit import AuditLog
from .credit_model import train_default_model
from .schemas import Case, Decision


class CaseRequest(BaseModel):
    document_text: str = Field(min_length=1, max_length=20_000)


class ReviewRequest(BaseModel):
    reviewer: str
    action: str
    new_decision: Optional[Decision] = None
    note: str = ""


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    app = FastAPI(title="Loan Officer Copilot", version="0.1.0")
    if orchestrator is None:
        planner = None
        if os.getenv("PLANNER", "deterministic") == "llm":
            from .llm_planner import LLMPlanner  # needs ANTHROPIC_API_KEY
            planner = LLMPlanner()
        orchestrator = Orchestrator(train_default_model(), AuditLog(os.getenv("AUDIT_DB", ":memory:")),
                                    planner=planner)
    orch = orchestrator

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def workbench() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": orch.scorer.version, "planner": type(orch.planner).__name__}

    @app.post("/cases", response_model=Case)
    def create_case(req: CaseRequest) -> Case:
        return orch.run_case(req.document_text)

    @app.get("/cases", response_model=list[Case])
    def list_cases() -> list[Case]:
        return list(reversed(orch.cases.values()))  # newest first

    @app.get("/cases/{case_id}", response_model=Case)
    def get_case(case_id: str) -> Case:
        case = orch.cases.get(case_id)
        if not case:
            raise HTTPException(404, "Case not found")
        return case

    @app.post("/cases/{case_id}/review", response_model=Case)
    def review_case(case_id: str, req: ReviewRequest) -> Case:
        try:
            return orch.review(case_id, req.reviewer, req.action, req.new_decision, req.note)
        except KeyError:
            raise HTTPException(404, "Case not found")
        except ReviewError as e:
            raise HTTPException(409, str(e))

    @app.get("/model/audit")
    def model_audit() -> dict:
        if not hasattr(orch.scorer, "audit_summary"):
            raise HTTPException(404, "This scorer does not provide a model audit")
        return orch.scorer.audit_summary()

    @app.get("/audit/verify")
    def verify() -> dict:
        ok, bad = orch.audit.verify()
        return {"intact": ok, "first_bad_entry": bad}

    @app.get("/audit/{case_id}")
    def audit_trail(case_id: str) -> list[dict]:
        return orch.audit.entries(case_id)

    return app


app = create_app()
