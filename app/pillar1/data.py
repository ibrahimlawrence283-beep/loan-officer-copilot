"""Synthetic Kenyan retail-lending dataset.

SYNTHETIC ONLY - no real customer data. Historical approval labels carry a
deliberate bias against women and rural applicants so the fairness audit has a
genuine signal to detect. The protected attribute (gender) is NOT a model
feature, but proxies (employment type, region, mobile-money pattern) leak it.
"""
import numpy as np
import pandas as pd

FEATURES = [
    "age", "monthly_income_kes", "employment_years", "employment_type",
    "region", "loan_amount_kes", "loan_term_months", "existing_loans",
    "mpesa_txn_per_month", "savings_balance_kes", "late_payments_12m",
]
PROTECTED = ["gender", "age_group"]
CATEGORICAL = ["employment_type", "region"]


def generate(n=8000, seed=42, drift=False):
    rng = np.random.default_rng(seed)
    gender = rng.choice(["female", "male"], n, p=[0.48, 0.52])
    age = np.clip(rng.normal(36, 10, n), 21, 68).round()
    region = rng.choice(["urban", "peri_urban", "rural"], n, p=[0.45, 0.30, 0.25])
    # proxy leakage: women over-represented in informal / small-business work
    p_formal = np.where(gender == "female", 0.38, 0.55)
    emp_type = np.array([
        rng.choice(["salaried", "self_employed", "informal"],
                   p=[pf, (1 - pf) * 0.45, (1 - pf) * 0.55]) for pf in p_formal
    ])
    base_income = {"urban": 62000, "peri_urban": 41000, "rural": 26000}
    income = np.array([base_income[r] for r in region]) * rng.lognormal(0, 0.45, n)
    income *= np.where(emp_type == "salaried", 1.25, np.where(emp_type == "informal", 0.7, 1.0))
    income = income.round(-2)
    emp_years = np.clip(rng.gamma(2.2, 2.6, n), 0, 35).round(1)
    loan_amt = (income * rng.uniform(1.5, 9, n)).round(-3)
    term = rng.choice([6, 12, 18, 24, 36], n, p=[0.15, 0.3, 0.2, 0.2, 0.15])
    existing = rng.poisson(0.9, n)
    mpesa = np.clip(rng.normal(55, 25, n) + income / 4000, 3, 300).round()
    savings = (income * rng.gamma(1.5, 0.8, n)).round(-2)
    late = np.clip(rng.poisson(0.8, n) + (existing > 2), 0, 8)

    if drift:  # simulated post-deployment shift: inflation squeezes income, more loans
        income = (income * 0.82).round(-2)
        existing = existing + rng.binomial(1, 0.25, n)
        mpesa = np.clip(mpesa * 1.15, 3, 300).round()

    dti = (loan_amt / term) / np.maximum(income, 1)
    z = (
        1.1
        + 0.9 * np.log1p(income / 30000)
        + 0.05 * emp_years
        + 0.5 * np.log1p(savings / income.clip(1))
        + 0.004 * mpesa
        - 4.5 * dti
        - 0.45 * late
        - 0.25 * existing
        - 0.9
    )
    # --- injected historical bias (what the audit should surface) ---
    z -= np.where(gender == "female", 0.55, 0.0)
    z -= np.where(region == "rural", 0.35, 0.0)
    prob = 1 / (1 + np.exp(-z))
    approved = rng.binomial(1, prob)

    df = pd.DataFrame({
        "age": age, "monthly_income_kes": income, "employment_years": emp_years,
        "employment_type": emp_type, "region": region, "loan_amount_kes": loan_amt,
        "loan_term_months": term, "existing_loans": existing,
        "mpesa_txn_per_month": mpesa, "savings_balance_kes": savings,
        "late_payments_12m": late, "gender": gender,
    })
    df["age_group"] = pd.cut(df["age"], [0, 29, 44, 100], labels=["21-29", "30-44", "45+"]).astype(str)
    df["approved"] = approved
    return df
