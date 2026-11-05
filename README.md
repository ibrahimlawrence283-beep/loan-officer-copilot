# Loan Officer Copilot

An AI-assisted loan underwriting workflow with **human-in-the-loop controls**, a **tamper-evident audit trail** and an **automated evaluation suite**. It reads a loan application, scores it with an explainable credit model, retrieves the relevant lending-policy clauses, drafts a recommendation with citations, and **blocks any adverse or high-impact outcome until an authorised officer reviews it**.

> All data is synthetic and the policy clauses are fictional. This is a portfolio project, not a production lending system.

![CI](https://github.com/ibrahimlawrence283-beep/loan-officer-copilot/actions/workflows/ci.yml/badge.svg)

## Quick start

```bash
pip install -r requirements.txt
pytest -q                          # 34 tests (the first run trains the model, about 15 s)
python evals/run_evals.py          # guardrail evals; exits non-zero on any failure
uvicorn app.api:app                # officer workbench at http://localhost:8000/ , API docs at /docs
```

Or with Docker: `docker compose up --build`, then open http://localhost:8000/ (the model trains at startup, so allow about 15 seconds).

| Setting | Meaning |
|---|---|
| `PLANNER=llm` | Use the LLM tool-calling planner. Needs `pip install -r requirements-llm.txt` and `ANTHROPIC_API_KEY`. Default is the deterministic planner. |
| `LLM_MODEL` | Model name for the LLM planner. |
| `AUDIT_DB` | Path of the SQLite audit database. Default is in-memory. |

## How it works
document
  -> extract_fields
  -> score_credit          (skipped if extraction is unreliable)
  -> retrieve_policy
  -> draft_recommendation
  -> apply_gate
       requires human?  yes: PENDING_HUMAN (no decision released)
                        no:  CLEARED
| Control | Where | Behaviour |
|---|---|---|
| Human approval | `guardrails.py`, `agent.py` | Declines, manual-review cases, loans over KES 1M, medium or high risk bands, out-of-range inputs and suspected injection never get a final decision without a named officer. Overrides need a written justification. |
| Fallback | `agent.py` | If extraction is missing, invalid or low-confidence, no score is produced and the case goes to manual review. |
| Bounded agent | `agent.py`, `llm_planner.py` | The planner can only pick from an allow-list of tools, steps are capped, preconditions are enforced by the orchestrator, and the gate always runs. The LLM planner sees only a document-free state summary. |
| Prompt-injection screening | `guardrails.py` | Document text is treated as data. Injection patterns are flagged and cannot change the outcome. |
| Explainability | `credit_model.py` | Exact SHAP contributions for each applicant, shown as the principal reasons. |
| Fairness by design | `credit_model.py` | Gender and region are never model inputs, and the form does not collect them. A test and an eval check this. |
| Model-risk check | `credit_model.py`, `guardrails.py` | Inputs outside the range the model was trained on are escalated to an officer. |
| Policy over model | `agent.py` | Policy rules (affordability, late payments, employment) can decline what the model alone would approve. |
| Audit trail | `audit.py` | Hash-chained SQLite log of every tool call and human decision. It stores a hash of the document, not its contents. |
| Safe UI | `app/static/` | DOM built without `innerHTML`, strict content-security policy. A test fails if unsafe DOM APIs are introduced. |

## The model

The scorer is the **MDA Pillar 1** model (`app/pillar1/`): a gradient-boosted classifier on synthetic Kenyan lending data, with SHAP explanations and a fairness and drift audit. The deployed variant removes region and reweights the training data by region, chosen from four strategies compared in the **Model audit** tab. It predicts whether the historical process would approve (those labels carry injected bias), so the score is an *approval probability*, not a default probability. Region disparity is reduced but **not eliminated**; the audit tab shows what remains.

## Evaluation (300 synthetic applications, latest run)

Regenerate with `python evals/run_evals.py --out evals/latest_report.json`.

| Check | Result |
|---|---|
| Adverse recommendations never finalised without human review | 248 / 248 |
| Injection attempts did not change the decision, were flagged, and were held for review | 60 / 60 |
| Missing-field documents fell back to unscored manual review | 60 / 60 |
| Policy citations resolve to real clauses | 300 / 300 |
| Large loans (above KES 1M) escalated | 7 / 7 |
| Protected attributes used as model inputs | none |
| Audit chain intact | yes |

Decision mix: about 52 approve, 180 decline, 68 manual review (it can shift by a case or two with different library versions). Model hold-out AUC 0.772. Remaining fairness flags (four-fifths screening rule): rural 0.72, peri-urban 0.78.

## Limitations

- **Synthetic data only.** Nothing here has been validated on real lending data.
- **Extraction accuracy (300 / 300) is on documents rendered by the same generator,** so it shows the pipeline is wired correctly, not real-world OCR or messy-scan robustness.
- **The model predicts historical approval, not repayment,** and the historical labels carry injected bias. It also underweights late payments, which is why a policy rule backs it up.
- **Region disparity remains** after mitigation (see the flagged rows in the Model audit tab). The four-fifths rule is a screening heuristic, not a Kenyan legal standard.
- **Age is a model input.** Its reason text would need legal review before any real use. SHAP reason codes are not legal adverse-action notices.
- **The LLM planner is tested with a simulated model client.** It has not been exercised against the live API in the test suite.
- **No authentication.** The reviewer name is self-declared. A real deployment needs identity, roles and an immutable external audit store.

## Roadmap

- [x] Core pipeline, guardrails, audit log, API, tests, CI, eval harness
- [x] LLM tool-calling planner behind the same interface
- [x] Officer review workbench
- [x] MDA Pillar 1 model with SHAP reasons and a model-audit tab
- [x] Docker image
- [ ] LLM-based extraction for messy documents, with a noisy test set
- [ ] Hybrid retrieval (Qdrant + BM25) over a larger policy corpus
- [ ] Authentication and role-based officer permissions

## Layout

```
app/            API, orchestrator, guardrails, audit log, extraction, scorer adapter, workbench UI
app/pillar1/    MDA Pillar 1 model, fairness, drift and mitigation code
evals/          evaluation harness and the latest report
tests/          34 automated tests
DEMO.md         90-second demo script
```
