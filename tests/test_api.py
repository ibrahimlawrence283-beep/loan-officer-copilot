from app.synthetic import render_application

from .conftest import GOOD


def test_end_to_end_api_flow(client):
    r = client.post("/cases", json={"document_text": render_application({**GOOD, "late_payments_12m": 4})})
    assert r.status_code == 200
    case = r.json()
    assert case["status"] == "pending_human" and case["final_decision"] is None
    cid = case["case_id"]

    bad = client.post(f"/cases/{cid}/review", json={"reviewer": "A", "action": "override", "note": "x"})
    assert bad.status_code == 409

    ok = client.post(f"/cases/{cid}/review", json={"reviewer": "Wanjiru M.", "action": "confirm"})
    assert ok.status_code == 200 and ok.json()["final_decision"] == "decline"

    trail = client.get(f"/audit/{cid}").json()
    assert trail[-1]["actor"] == "Wanjiru M."
    assert client.get("/audit/verify").json() == {"intact": True, "first_bad_entry": None}


def test_unknown_case_and_empty_document(client):
    assert client.get("/cases/NOPE").status_code == 404
    assert client.post("/cases", json={"document_text": ""}).status_code == 422


def test_workbench_ui_is_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "Loan officer workbench" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_ui_never_uses_innerhtml():
    """Document text is untrusted; the UI must build DOM with textContent only."""
    from pathlib import Path
    js = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text()
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert banned not in js


def test_case_list_is_newest_first(client):
    ids = [client.post("/cases", json={"document_text": render_application(GOOD)}).json()["case_id"] for _ in range(3)]
    listed = [c["case_id"] for c in client.get("/cases").json()]
    assert listed == ids[::-1]


def test_model_audit_endpoint(client):
    r = client.get("/model/audit")
    assert r.status_code == 200
    body = r.json()
    assert body["model"]["auc"] > 0.75 and "region" not in body["model"]["inputs"]
