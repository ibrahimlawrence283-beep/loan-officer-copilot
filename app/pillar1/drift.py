"""Population Stability Index + Wasserstein drift monitor."""
import numpy as np
from scipy.stats import wasserstein_distance


def psi(expected, actual, bins=10):
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(actual, edges)[0] / len(actual)
    e, a = np.clip(e, 1e-4, None), np.clip(a, 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def status(v):
    return "stable" if v < 0.10 else ("moderate" if v < 0.25 else "significant")


def monitor(ref_df, cur_df, numeric_cols):
    out = []
    for c in numeric_cols:
        p = psi(ref_df[c].values, cur_df[c].values)
        w = wasserstein_distance(ref_df[c], cur_df[c]) / (ref_df[c].std() or 1)
        out.append({"feature": c, "psi": round(p, 4), "wasserstein_norm": round(float(w), 4), "status": status(p)})
    return sorted(out, key=lambda r: -r["psi"])
