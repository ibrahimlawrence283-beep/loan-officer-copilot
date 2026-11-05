import pytest
from fastapi.testclient import TestClient

from app.agent import Orchestrator
from app.api import create_app
from app.audit import AuditLog
from app.credit_model import Pillar1Scorer


@pytest.fixture(scope="session")
def model():
    return Pillar1Scorer()


@pytest.fixture()
def orch(model):
    return Orchestrator(model, AuditLog())


@pytest.fixture()
def client(orch):
    return TestClient(create_app(orch))


GOOD = dict(age=40, monthly_income_kes=150_000, employment_type="salaried", employment_years=8,
            loan_amount_kes=600_000, loan_term_months=24, existing_loans=0, mpesa_txn_per_month=120,
            savings_balance_kes=300_000, late_payments_12m=0)
