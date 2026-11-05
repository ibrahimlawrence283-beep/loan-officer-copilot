"""Application documents and lending-policy clauses for the demo.

Applicant records come from the MDA Pillar 1 synthetic generator (app/pillar1/data.py).
All data is fabricated. No real customer data is used.
"""
from __future__ import annotations

FIELDS = [
    "age", "monthly_income_kes", "employment_type", "employment_years", "loan_amount_kes",
    "loan_term_months", "existing_loans", "mpesa_txn_per_month", "savings_balance_kes", "late_payments_12m",
]
FORM_LABELS = {
    "form": {
        "age": "Age", "monthly_income_kes": "Monthly Income", "employment_type": "Employment Type",
        "employment_years": "Years in Current Employment", "loan_amount_kes": "Loan Amount Requested",
        "loan_term_months": "Loan Term (months)", "existing_loans": "Number of Existing Loans",
        "mpesa_txn_per_month": "M-Pesa Transactions per Month", "savings_balance_kes": "Savings Balance",
        "late_payments_12m": "Late Payments (last 12 months)",
    },
    "payslip": {
        "age": "Age (years)", "monthly_income_kes": "Gross Monthly Salary", "employment_type": "Type of Employment",
        "employment_years": "Employment Length (years)", "loan_amount_kes": "Amount Applied",
        "loan_term_months": "Repayment Period", "existing_loans": "Existing Loans (count)",
        "mpesa_txn_per_month": "Mobile Money Transactions per Month", "savings_balance_kes": "Savings Account Balance",
        "late_payments_12m": "Late Payments in Past 12 Months",
    },
}
MONEY = {"monthly_income_kes", "loan_amount_kes", "savings_balance_kes"}


def render_application(applicant: dict, ref: str = "APP-0001", style: str = "form", notes: str = "") -> str:
    labels = FORM_LABELS[style]
    title = "LOAN APPLICATION FORM" if style == "form" else "SALARY & OBLIGATIONS STATEMENT"
    lines = [title, f"Applicant Ref: {ref}"]
    for key in FIELDS:
        v = applicant[key]
        if key == "employment_type":
            lines.append(f"{labels[key]}: {str(v).replace('_', ' ')}")
        elif key in MONEY:
            lines.append(f"{labels[key]}: KES {int(v):,}")
        elif float(v).is_integer():
            lines.append(f"{labels[key]}: {int(v)}")
        else:
            lines.append(f"{labels[key]}: {v}")
    if notes:
        lines.append(f"Notes: {notes}")
    return "\n".join(lines)


POLICY_CLAUSES = [
    {"id": "LP-01", "title": "Affordability",
     "text": "The monthly instalment (loan amount divided by the term in months) must not exceed 50% of gross monthly income. Instalments between 35% and 50% of income require loan officer review."},
    {"id": "LP-02", "title": "Repayment history",
     "text": "Applicants with 3 or more late payments in the last 12 months must be declined or referred to the credit committee."},
    {"id": "LP-03", "title": "Employment stability",
     "text": "Applicants with less than 6 months in current employment require an employer confirmation letter and officer review."},
    {"id": "LP-04", "title": "Approval authority",
     "text": "Loans above KES 1,000,000 require approval by a credit officer. Loans above KES 2,500,000 are referred to the credit committee."},
    {"id": "LP-05", "title": "Explainability and fairness",
     "text": "Every adverse decision must be accompanied by the principal reasons communicated to the applicant. Decisions must not rely on gender, ethnicity, religion or region. Applicants have the right not to be subject to a decision based solely on automated processing (Data Protection Act, 2019, Section 35)."},
    {"id": "LP-06", "title": "Human oversight",
     "text": "No decline or other adverse decision may be finalised by an automated system without documented human review by an authorised officer."},
    {"id": "LP-07", "title": "Data handling",
     "text": "Personal data must be minimised, encrypted at rest, and retained only for as long as required for the lending decision and legal obligations."},
    {"id": "LP-08", "title": "Borderline model score",
     "text": "Where the credit model's approval probability is between 40% and 60% the case is borderline and requires officer review. Inputs outside the range the model was trained on also require officer review."},
]
