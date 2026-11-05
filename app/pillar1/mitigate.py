"""Bias mitigation strategies + before/after comparison.

Strategies (pre-processing only, so no group-specific decision rules):
  baseline  - model as audited
  drop      - remove the region feature (fairness through unawareness)
  reweigh   - Kamiran & Calders reweighing: sample weights that make the
              approval label statistically independent of region in training
  both      - drop + reweigh
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from .fairness import audit

STRATEGIES = {
    "baseline": "No mitigation (baseline)",
    "drop": "Remove the region feature",
    "reweigh": "Reweight training data by region",
    "both": "Remove region and reweight",
}
AUDIT_ATTRS = ["gender", "age_group", "region"]


def reweigh(df_train, attr):
    """w(g, y) = P(g) * P(y) / P(g, y)"""
    w = np.ones(len(df_train))
    grp, lab = df_train[attr].values, df_train["approved"].values
    for g in np.unique(grp):
        for y in (0, 1):
            m = (grp == g) & (lab == y)
            if m.any():
                w[m] = (np.mean(grp == g) * np.mean(lab == y)) / m.mean()
    return w


def _fit(X_tr, y_tr, w, seed=42):
    m = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.06,
                                   subsample=0.8, random_state=seed)
    return m.fit(X_tr, y_tr, sample_weight=w)


def compare_strategies(df, X, cols, tr, te, attr="region"):
    """Train every strategy on the same split; return {name: result dict}."""
    y = df["approved"].values
    no_region = [c for c in cols if not c.startswith(f"{attr}_")]
    w = reweigh(df.iloc[tr], attr)
    plan = {"baseline": (cols, None), "drop": (no_region, None),
            "reweigh": (cols, w), "both": (no_region, w)}
    dte, out = df.iloc[te], {}
    for name, (cu, sw) in plan.items():
        model = _fit(X.iloc[tr][cu], y[tr], sw)
        pred = model.predict(X.iloc[te][cu])
        auc = roc_auc_score(y[te], model.predict_proba(X.iloc[te][cu])[:, 1])
        audits = pd.concat([audit(dte, y[te], pred, a) for a in AUDIT_ATTRS], ignore_index=True)
        out[name] = {"label": STRATEGIES[name], "model": model, "cols": cu, "auc": float(auc),
                     "approval_rate": float(pred.mean()), "audit": audits}
    return out


def summary_table(results):
    rows = []
    for name, r in results.items():
        a = r["audit"]
        reg = a[a.attribute == "region"].set_index("group")["disparate_impact_ratio"]
        gen = a[a.attribute == "gender"]["disparate_impact_ratio"]
        rows.append({"strategy": r["label"], "AUC": round(r["auc"], 3),
                     "approval_rate": round(r["approval_rate"], 3),
                     "rural_DIR": reg.get("rural"), "peri_urban_DIR": reg.get("peri_urban"),
                     "worst_gender_DIR": round(float(gen.min()), 3)})
    return pd.DataFrame(rows)
