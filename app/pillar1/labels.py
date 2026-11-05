"""Shared human-readable names for features and groups."""
import re

LABELS = {"monthly_income_kes": "Monthly income (KES)", "loan_amount_kes": "Loan amount (KES)",
          "loan_term_months": "Term (months)", "employment_years": "Years employed",
          "existing_loans": "Existing loans", "mpesa_txn_per_month": "M-Pesa txns / month",
          "savings_balance_kes": "Savings (KES)", "late_payments_12m": "Late payments (12m)",
          "age": "Age", "employment_type": "Employment type", "region": "Region"}


def pretty(f):
    if f in LABELS:
        return LABELS[f]
    if f.startswith("region_"):
        return "Region: " + f[7:].replace("_", "-")
    if f.startswith("employment_type_"):
        return "Employment: " + f[16:].replace("_", " ")
    return f


def pretty_group(g):
    return str(g).replace("_", "-")


def pretty_rule(text):
    """Replace raw column names inside a LIME rule string with readable ones."""
    names = sorted(LABELS, key=len, reverse=True)
    for n in names:
        text = re.sub(rf"\b{n}\b", LABELS[n], text)
    for raw in ["region_rural", "region_peri_urban", "region_urban", "employment_type_informal",
                "employment_type_self_employed", "employment_type_salaried"]:
        text = text.replace(raw, pretty(raw))
    return text
