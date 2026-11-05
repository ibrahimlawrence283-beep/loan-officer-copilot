import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from .data import FEATURES, CATEGORICAL


def encode(df, columns=None):
    X = pd.get_dummies(df[FEATURES], columns=CATEGORICAL, dtype=float)
    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.0)
    return X


def train(df, seed=42):
    X = encode(df)
    y = df["approved"].values
    idx_tr, idx_te = train_test_split(np.arange(len(df)), test_size=0.25, random_state=seed, stratify=y)
    model = GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.06,
                                       subsample=0.8, random_state=seed)
    model.fit(X.iloc[idx_tr], y[idx_tr])
    auc = roc_auc_score(y[idx_te], model.predict_proba(X.iloc[idx_te])[:, 1])
    return model, list(X.columns), idx_tr, idx_te, auc
