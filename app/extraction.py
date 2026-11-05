"""Document field extraction with per-field confidence.

Deterministic label-based parser for the demo. An LLM-based extractor can be added behind the
same ExtractionResult contract for messy scans; the confidence gate downstream stays the same.
Fields match the inputs of the MDA Pillar 1 model. Region and gender are deliberately not collected.
"""
from __future__ import annotations

import re

from .schemas import ExtractedField, ExtractionResult

LABELS: dict[str, list[str]] = {
    "age": ["age", "age (years)", "applicant age"],
    "monthly_income_kes": ["monthly income", "gross monthly salary", "gross monthly income"],
    "employment_type": ["employment type", "type of employment"],
    "employment_years": ["years in current employment", "employment length (years)", "years employed"],
    "loan_amount_kes": ["loan amount requested", "amount applied", "loan amount"],
    "loan_term_months": ["loan term (months)", "repayment period", "loan term"],
    "existing_loans": ["number of existing loans", "existing loans (count)", "existing loans"],
    "mpesa_txn_per_month": ["m-pesa transactions per month", "mobile money transactions per month",
                            "mpesa transactions per month"],
    "savings_balance_kes": ["savings balance", "savings account balance"],
    "late_payments_12m": ["late payments (last 12 months)", "late payments in past 12 months", "late payments"],
}
CATEGORICAL = {"employment_type": {"salaried": "salaried", "employed": "salaried",
                                   "self_employed": "self_employed", "informal": "informal"}}
RANGES: dict[str, tuple[float, float]] = {
    "age": (18, 80), "monthly_income_kes": (1_000, 10_000_000), "employment_years": (0, 60),
    "loan_amount_kes": (1_000, 50_000_000), "loan_term_months": (1, 120), "existing_loans": (0, 30),
    "mpesa_txn_per_month": (0, 5_000), "savings_balance_kes": (0, 100_000_000), "late_payments_12m": (0, 12),
}
_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_number(raw: str) -> float | None:
    m = _NUM.search(raw.replace(",", ""))
    return float(m.group()) if m else None


def _parse_category(field: str, raw: str) -> str | None:
    key = re.sub(r"[\s\-]+", "_", raw.strip().lower())
    return CATEGORICAL[field].get(key)


def _match(label: str) -> tuple[str, float] | None:
    norm = label.strip().lower()
    best: tuple[str, float] | None = None
    for field, synonyms in LABELS.items():
        for s in synonyms:
            if norm == s:
                return field, 1.0
            if len(norm) >= 8 and (s in norm or norm in s):
                best = (field, 0.7) if best is None or best[1] < 0.7 else best
    return best


def extract(text: str) -> ExtractionResult:
    fields: dict[str, ExtractedField] = {}
    invalid: list[str] = []
    notes = ""
    for line in text.splitlines():
        if ":" not in line:
            continue
        label, _, raw = line.partition(":")
        if label.strip().lower() == "notes":
            notes = raw.strip()
            continue
        hit = _match(label)
        if not hit:
            continue
        field, conf = hit
        if field in CATEGORICAL:
            cat = _parse_category(field, raw)
            if cat is None:
                if field not in invalid:
                    invalid.append(field)
                continue
            value: float | str | None = cat
        else:
            value = _parse_number(raw)
            if value is None:
                continue
        if field not in fields or conf > fields[field].confidence:
            fields[field] = ExtractedField(value=value, confidence=conf, raw_label=label.strip())

    missing = [f for f in LABELS if f not in fields and f not in invalid]
    for f, ef in fields.items():
        if f in RANGES:
            lo, hi = RANGES[f]
            if not (lo <= ef.value <= hi) and f not in invalid:
                invalid.append(f)
    conf = 0.0 if (missing or invalid) else min(ef.confidence for ef in fields.values())
    return ExtractionResult(fields=fields, missing=missing, invalid=invalid, confidence=conf, notes=notes)
