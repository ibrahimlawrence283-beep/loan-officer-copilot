# 90-second demo script

Record the screen at 1080p. Start the app first (`uvicorn app.api:app`, or `docker compose up`) and open http://localhost:8000/.

| Time | Do this | Say this |
|---|---|---|
| 0:00 | Show the empty workbench. | "This is a governed loan-underwriting copilot. All data is synthetic." |
| 0:10 | New assessment, load **Late payments**, run it. | "The model alone would approve this applicant, but a policy rule catches the late payments." |
| 0:25 | Point at the banner and the hold message. | "The recommendation is a decline, and nothing is released until an officer signs off." |
| 0:35 | Point at the score drivers and the policy clauses. | "Every recommendation shows the SHAP reasons and the policy clauses it relies on." |
| 0:45 | Enter a name, confirm the decline. | "The officer decides, and the decision is attributed." |
| 0:55 | Run **Injection attempt**. | "Text hidden in a document tries to force an approval. It is flagged, ignored and held for review." |
| 1:10 | Scroll to the audit trail, then open **Model audit**. | "Every step is in a tamper-evident log. The model audit shows fairness by group, and I report the region gap that remains." |
| 1:25 | Show the green CI badge or test output. | "34 tests and a 300-application evaluation run automatically." |
