"""Fairness metrics. Reference group = highest-approval group per attribute."""
import numpy as np
import pandas as pd


def _rates(y_true, y_pred):
    tpr = y_pred[y_true == 1].mean() if (y_true == 1).any() else np.nan
    fpr = y_pred[y_true == 0].mean() if (y_true == 0).any() else np.nan
    return tpr, fpr


def audit(df, y_true, y_pred, attr):
    d = pd.DataFrame({"g": df[attr].values, "y": y_true, "p": y_pred})
    sel = d.groupby("g")["p"].mean()
    ref = sel.idxmax()
    rows = []
    ref_tpr, ref_fpr = _rates(d.y[d.g == ref].values, d.p[d.g == ref].values)
    for g, sub in d.groupby("g"):
        tpr, fpr = _rates(sub.y.values, sub.p.values)
        rows.append({
            "attribute": attr, "group": g, "n": len(sub),
            "selection_rate": round(float(sel[g]), 3),
            "disparate_impact_ratio": round(float(sel[g] / sel[ref]), 3),
            "demographic_parity_diff": round(float(sel[g] - sel[ref]), 3),
            "tpr_gap": round(float(tpr - ref_tpr), 3),
            "fpr_gap": round(float(fpr - ref_fpr), 3),
            "flag_four_fifths": bool(sel[g] / sel[ref] < 0.8),
            "reference": g == ref,
        })
    return pd.DataFrame(rows)
