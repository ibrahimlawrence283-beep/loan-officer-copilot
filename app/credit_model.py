"""Adapter that plugs the MDA Pillar 1 model into the copilot.

Pillar 1 is a gradient-boosted classifier trained on synthetic Kenyan lending data. It predicts the
probability that the *historical process* would approve an application, so the output here is an
approval probability, not a probability of default. Region is removed from the inputs and the
training data is reweighted by region (strategy "both" in Pillar 1's mitigation comparison).
Gender is never an input. Explanations are exact SHAP values from the tree model.
"""
from __future__ import annotations

import json
from typing import Protocol

import pandas as pd
import shap

from .pillar1.data import FEATURES, generate
from .pillar1.drift import monitor
from .pillar1.fairness import audit
from .pillar1.labels import pretty
from .pillar1.mitigate import AUDIT_ATTRS, STRATEGIES, compare_strategies, summary_table
from .pillar1.model import encode, train
from .schemas import Reason, ScoreResult

MODEL_INPUTS = [f for f in FEATURES if f != "region"]
NUMERIC_INPUTS = [f for f in MODEL_INPUTS if f != "employment_type"]
EMPLOYMENT_TYPES = ["salaried", "self_employed", "informal"]
LOW_BAND, HIGH_BAND = 0.60, 0.40   # approval probability cut-offs for the risk band


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records"))


class CreditScorer(Protocol):
    version: str

    def predict(self, applicant: dict) -> ScoreResult: ...
    def out_of_range(self, applicant: dict) -> list[str]: ...


class Pillar1Scorer:
    def __init__(self, n: int = 8000, seed: int = 42, strategy: str = "both") -> None:
        self.strategy = strategy
        self.df = generate(n, seed=seed)
        _, cols, self.tr, self.te, _ = train(self.df)
        self.X = encode(self.df, cols)
        self.results = compare_strategies(self.df, self.X, cols, self.tr, self.te)
        chosen = self.results[strategy]
        self.model, self.cols, self.auc = chosen["model"], chosen["cols"], chosen["auc"]
        self.version = f"MDA Pillar 1 v3 ({STRATEGIES[strategy].lower()})"
        self._explainer = shap.TreeExplainer(self.model)
        train_df = self.df.iloc[self.tr]
        self.bounds = {c: (float(train_df[c].min()), float(train_df[c].max())) for c in NUMERIC_INPUTS}
        self._audit_cache: dict | None = None

    # ---- scoring ------------------------------------------------------------------------
    def _row(self, a: dict) -> pd.DataFrame:
        row = {k: a[k] for k in MODEL_INPUTS}
        row["region"] = "urban"  # placeholder: region columns are not model inputs and are dropped on encode
        return encode(pd.DataFrame([row]), self.cols)

    def out_of_range(self, a: dict) -> list[str]:
        """Inputs outside what the model saw in training (extrapolation is a model-risk issue)."""
        bad = [c for c, (lo, hi) in self.bounds.items() if not (lo <= float(a[c]) <= hi)]
        if a["employment_type"] not in EMPLOYMENT_TYPES:
            bad.append("employment_type")
        return bad

    def predict(self, applicant: dict) -> ScoreResult:
        x = self._row(applicant)
        p = float(self.model.predict_proba(x)[0, 1])
        shap_vals = self._explainer.shap_values(x)[0]       # log-odds toward approval
        reasons = [
            Reason(feature=c, label=pretty(c), contribution=round(float(-sv), 4),  # >0 = pushes toward decline
                   direction="increases risk" if sv < 0 else "reduces risk", value=round(float(x.iloc[0][c]), 4))
            for c, sv in zip(self.cols, shap_vals)
        ]
        reasons.sort(key=lambda r: abs(r.contribution), reverse=True)
        band = "low" if p >= LOW_BAND else "medium" if p >= HIGH_BAND else "high"
        return ScoreResult(approval_probability=round(p, 4), risk_band=band,
                           reasons=reasons[:4], model_version=self.version)

    # ---- model audit (shown in the workbench) --------------------------------------------
    def audit_summary(self) -> dict:
        if self._audit_cache is None:
            te_df, y = self.df.iloc[self.te], self.df.iloc[self.te]["approved"].values
            pred = self.model.predict(self.X.iloc[self.te][self.cols])
            fairness = pd.concat([audit(te_df, y, pred, a) for a in AUDIT_ATTRS], ignore_index=True)
            historical = pd.concat([audit(self.df, self.df["approved"].values, self.df["approved"].values, a)
                                    for a in AUDIT_ATTRS], ignore_index=True)
            drift = monitor(self.df.iloc[self.tr], generate(3000, seed=7, drift=True), NUMERIC_INPUTS)
            self._audit_cache = {
                "model": {"version": self.version, "auc": round(self.auc, 3), "strategy": STRATEGIES[self.strategy],
                          "inputs": MODEL_INPUTS, "n_train": int(len(self.tr)), "n_test": int(len(self.te))},
                "strategies": _records(summary_table(self.results)),
                "chosen_strategy": STRATEGIES[self.strategy],
                "fairness": _records(fairness[["attribute", "group", "n", "selection_rate",
                                               "disparate_impact_ratio", "flag_four_fifths"]]),
                "historical": _records(historical[["attribute", "group", "n", "selection_rate",
                                                   "disparate_impact_ratio", "flag_four_fifths"]]),
                "drift": drift,
                "limits": [
                    "All data is synthetic. Historical labels carry a deliberately injected bias so the audit has signal.",
                    "The model predicts historical approval, not repayment. Equalized-odds style gaps use biased labels as ground truth.",
                    "SHAP reason codes explain the model; they are not legal adverse-action notices and need legal review.",
                    "The four-fifths rule is a screening heuristic, not a Kenyan legal standard.",
                    "Residual region disparity remains after mitigation; see the flagged rows.",
                ],
            }
        return self._audit_cache


def train_default_model() -> Pillar1Scorer:
    return Pillar1Scorer()
