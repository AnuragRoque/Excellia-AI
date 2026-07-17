"""Supervised fraud scoring: train on labelled history, score fresh files.

Honest by construction: metrics come from cross-validation only, every
model ships with a ModelCard (metrics, features, schema fingerprint —
never the data), leakage is detected and named, and the output wording
is always "risk score", never "this IS fraud". No labelled history?
Use ``detect_anomalies`` instead — that's the unsupervised fallback.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from excellia.core import store
from excellia.core.ingest import nonempty

MIN_ROWS = 200
MAX_ONEHOT_CARDINALITY = 20
_BANDS = ((0.75, "critical"), (0.5, "high"), (0.25, "medium"), (0.0, "low"))
_TOP_FACTOR_FEATURES = 10  # globally-important features probed per row
_WORDING = ("Scores are RISK estimates from patterns in the training data, "
            "not accusations. A high score means 'looks like past fraud', "
            "never 'this IS fraud'. Review before acting.")


class FraudError(ValueError):
    """Refusal with a reason and the fix. Message is the interface."""


def _schema_fingerprint(columns: list[str]) -> str:
    return hashlib.sha256("|".join(sorted(columns)).encode()).hexdigest()[:16]


def _split_features(df: pd.DataFrame, label_column: str) -> tuple[list[str], list[str], list[str]]:
    """(numeric, categorical, dropped) feature column names."""
    numeric, categorical, dropped = [], [], []
    for col in df.columns:
        if col == label_column:
            continue
        values = nonempty(df[col])
        if values.empty:
            dropped.append(col)
            continue
        as_num = pd.to_numeric(values, errors="coerce")
        if as_num.notna().mean() >= 0.9:
            numeric.append(col)
        elif values.nunique() <= MAX_ONEHOT_CARDINALITY:
            categorical.append(col)
        else:
            dropped.append(col)  # high-cardinality text (ids, names) — no signal, only leakage
    return numeric, categorical, dropped


def _labels(df: pd.DataFrame, label_column: str, positive_label) -> tuple[pd.Series, Any]:
    if label_column not in df.columns:
        raise FraudError(
            f"Label column '{label_column}' not found. Actual columns: "
            f"{list(df.columns)}. Pass the column that marks fraud/not-fraud."
        )
    raw = df[label_column]
    values = nonempty(raw)
    classes = sorted(values.astype(str).str.strip().str.lower().unique())
    if len(classes) < 2:
        raise FraudError(
            f"Label column '{label_column}' has a single class ({classes}). "
            "Training needs BOTH fraud and non-fraud examples. If you have no "
            "labelled history, use detect_anomalies instead."
        )
    if len(classes) > 10:
        raise FraudError(
            f"Label column '{label_column}' has {len(classes)} distinct values — "
            "that looks like data, not a fraud label. Pick a binary column."
        )
    norm = values.astype(str).str.strip().str.lower()  # only labelled rows count
    if positive_label is not None:
        pos = str(positive_label).strip().lower()
        if pos not in classes:
            raise FraudError(
                f"positive_label '{positive_label}' not in the label column. "
                f"Classes found: {classes}")
    else:
        for guess in ("fraud", "fraudulent", "yes", "true", "1", "positive"):
            if guess in classes:
                pos = guess
                break
        else:
            pos = classes[-1]  # deterministic fallback; named in the card
    return (norm == pos).astype(int), pos


def _leakage_check(df: pd.DataFrame, y: pd.Series, numeric: list[str],
                   categorical: list[str], label_column: str) -> None:
    """Refuse when a feature IS the label in disguise — name it."""
    for col in numeric:
        as_num = pd.to_numeric(df[col], errors="coerce")
        aligned = pd.concat([as_num, y], axis=1).dropna()
        if len(aligned) > 10 and aligned.iloc[:, 0].nunique() > 1:
            corr = abs(aligned.corr().iloc[0, 1])
            if corr > 0.99:
                raise FraudError(
                    f"Feature '{col}' correlates ~{corr:.2f} with the label — "
                    "that's leakage (the answer hiding in the inputs). Drop the "
                    "column and retrain, or the metrics will be a lie."
                )
    for col in categorical:
        norm = df[col].astype(str).str.strip().str.lower()
        # exact-encoding check: every category maps to exactly one class
        mapping = pd.crosstab(norm, y)
        if len(mapping) > 1 and (mapping.gt(0).sum(axis=1) == 1).all():
            raise FraudError(
                f"Feature '{col}' perfectly encodes the label (every value maps "
                "to one class) — that's leakage. Drop it and retrain."
            )


def _build_pipeline(numeric: list[str], categorical: list[str], algorithm: str):
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    if algorithm == "gradient_boosting":
        estimator = GradientBoostingClassifier(random_state=42)
    elif algorithm == "random_forest":
        estimator = RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=42)
    else:
        raise FraudError(
            f"Unknown algorithm '{algorithm}'. Use 'gradient_boosting' (default) "
            "or 'random_forest'.")

    pre = ColumnTransformer([
        ("num", Pipeline([
            ("to_num", _ToNumeric()),
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), numeric),
        ("cat", Pipeline([
            ("to_str", _ToString()),
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), categorical),
    ])
    return Pipeline([("pre", pre), ("clf", estimator)])


class _ToNumeric:
    """Coerce mixed columns ('₹1,200', '95') to floats inside the pipeline."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = pd.DataFrame(X)
        return X.apply(lambda s: pd.to_numeric(
            s.astype(str).str.replace(r"[₹$€£,\s]", "", regex=True), errors="coerce"))

    def get_feature_names_out(self, input_features=None):
        return np.asarray(input_features)


class _ToString:
    """Normalise categoricals to trimmed lowercase strings."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = pd.DataFrame(X)
        return X.astype(str).apply(lambda s: s.str.strip().str.lower())

    def get_feature_names_out(self, input_features=None):
        return np.asarray(input_features)


def train(df: pd.DataFrame, label_column: str, model_name: str,
          positive_label: str | None = None,
          algorithm: str = "gradient_boosting") -> dict[str, Any]:
    """Train a fraud classifier and save it with an honest ModelCard.

    Refuses (with the fix named) when: label column missing/single-class,
    fewer than 200 usable rows, or leakage is detected. Metrics are
    stratified 5-fold cross-validation — never training-set scores.
    """
    from sklearn.metrics import (confusion_matrix, f1_score, precision_score,
                                 recall_score, roc_auc_score)
    from sklearn.model_selection import StratifiedKFold

    y, positive = _labels(df, label_column, positive_label)
    X_df = df.loc[y.index]
    if len(X_df) < MIN_ROWS:
        raise FraudError(
            f"Only {len(X_df)} labelled rows — need at least {MIN_ROWS} to train "
            "anything honest. Collect more history, or use detect_anomalies "
            "(unsupervised) meanwhile."
        )
    numeric, categorical, dropped = _split_features(X_df, label_column)
    if not numeric and not categorical:
        raise FraudError(
            "No usable feature columns (everything is empty or high-cardinality "
            f"text). Columns dropped: {dropped}.")
    _leakage_check(X_df, y, numeric, categorical, label_column)

    pipeline = _build_pipeline(numeric, categorical, algorithm)
    X = X_df[numeric + categorical]

    # class imbalance: sample weights (GradientBoosting has no class_weight)
    pos_rate = y.mean()
    weights = np.where(y == 1, 0.5 / max(pos_rate, 1e-9), 0.5 / max(1 - pos_rate, 1e-9))

    # manual CV loop: full control over sample_weight without depending on
    # sklearn's fit-param routing API (which shifted across 1.x versions)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    proba = np.zeros(len(y), dtype=float)
    y_arr = y.to_numpy()
    for train_idx, test_idx in cv.split(X, y_arr):
        fold = _build_pipeline(numeric, categorical, algorithm)
        fold.fit(X.iloc[train_idx], y_arr[train_idx],
                 clf__sample_weight=weights[train_idx])
        proba[test_idx] = fold.predict_proba(X.iloc[test_idx])[:, 1]
    pred = (proba >= 0.5).astype(int)
    metrics = {
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y, proba)), 4),
    }
    tn, fp, fn, tp = confusion_matrix(y, pred).ravel()

    pipeline.fit(X, y, clf__sample_weight=weights)
    importances = _feature_importances(pipeline, top=15)
    baselines = {c: float(pd.to_numeric(X[c], errors="coerce").median()) for c in numeric}
    baselines.update({
        c: str(X[c].astype(str).str.strip().str.lower().mode().iat[0]) for c in categorical
    })

    card = {
        "name": model_name,
        "algorithm": algorithm,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(X_df)),
        "label_column": label_column,
        "positive_label": positive,
        "class_balance": {"positive": int(y.sum()), "negative": int(len(y) - y.sum())},
        "features_numeric": numeric,
        "features_categorical": categorical,
        "features_dropped": dropped,
        "cv_metrics": metrics,
        "confusion_at_0.5": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "threshold": 0.5,
        "top_features": importances,
        "feature_baselines": baselines,
        "schema_fingerprint": _schema_fingerprint(numeric + categorical),
        "wording": _WORDING,
    }
    store.save_model(model_name, pipeline, card)
    store.record("fraud_train", params={"model": model_name, "rows": len(X_df)},
                 summary=metrics)
    return card


def _feature_importances(pipeline, top: int) -> list[dict[str, float]]:
    clf = pipeline.named_steps["clf"]
    try:
        names = pipeline.named_steps["pre"].get_feature_names_out()
    except Exception:
        names = [f"f{i}" for i in range(len(clf.feature_importances_))]
    pairs = sorted(zip(names, clf.feature_importances_), key=lambda p: -p[1])[:top]
    return [{"feature": str(n).split("__", 1)[-1], "importance": round(float(v), 4)}
            for n, v in pairs if v > 0]


def _check_schema(df: pd.DataFrame, card: dict) -> list[str]:
    expected = card.get("features_numeric", []) + card.get("features_categorical", [])
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise FraudError(
            f"This file is missing columns the model '{card['name']}' was trained "
            f"on: {missing}. Expected features: {expected}. Score a file with the "
            "same schema, or retrain on this schema."
        )
    return [c for c in df.columns if c not in expected and c != card.get("label_column")]


def _band(p: float) -> str:
    for cut, name in _BANDS:
        if p >= cut:
            return name
    return "low"


def _py(value):
    """JSON-safe scalar: numpy types -> native Python, NaN -> None."""
    if pd.isnull(value):
        return None
    return value.item() if hasattr(value, "item") else value


def score(df: pd.DataFrame, model_name: str,
          threshold: float | None = None) -> dict[str, Any]:
    """Score fresh rows: probability, risk band, and the top factors per row.

    Factors come from occlusion: each globally-important feature is
    replaced by its training baseline and the probability drop is
    measured — the biggest drops are what pushed THIS row's score up.
    """
    pipeline, card = store.load_model(model_name)
    extra = _check_schema(df, card)
    features = card["features_numeric"] + card["features_categorical"]
    X = df[features]
    proba = pipeline.predict_proba(X)[:, 1]
    threshold = threshold if threshold is not None else card.get("threshold", 0.5)

    # occlusion contributions, one batch prediction per probed feature
    probe = [f["feature"] for f in card.get("top_features", [])[:_TOP_FACTOR_FEATURES]]
    probe = [p for p in dict.fromkeys(
        p if p in features else p.rsplit("_", 1)[0] for p in probe) if p in features]
    contributions: dict[str, np.ndarray] = {}
    baselines = card.get("feature_baselines", {})
    for feat in probe:
        if feat not in baselines:
            continue
        X_alt = X.copy()
        X_alt[feat] = baselines[feat]
        contributions[feat] = proba - pipeline.predict_proba(X_alt)[:, 1]

    scores = []
    for i in range(len(df)):
        p = float(proba[i])
        factors = sorted(
            ((feat, float(delta[i])) for feat, delta in contributions.items()
             if delta[i] > 0.001),
            key=lambda t: -t[1])[:3]
        scores.append({
            "row": i + 2,  # Excel numbering
            "fraud_probability": round(p, 4),
            "risk_band": _band(p),
            "flagged": p >= threshold,
            "top_factors": [
                {"feature": f, "value": _py(df.iloc[i][f]),
                 "contribution": round(c, 4)} for f, c in factors],
        })
    store.record("fraud_score", params={"model": model_name},
                 summary={"rows": len(df), "flagged": int((proba >= threshold).sum())})
    return {
        "scores": scores,
        "model_card": card,
        "summary": {
            "rows": len(df), "flagged": int((proba >= threshold).sum()),
            "threshold": threshold,
            "bands": {name: int(sum(1 for s in scores if s["risk_band"] == name))
                      for _, name in _BANDS},
            "extra_columns_ignored": extra,
            "note": _WORDING + " Row numbers are Excel rows (data starts at 2).",
        },
    }


def evaluate(df: pd.DataFrame, label_column: str, model_name: str) -> dict[str, Any]:
    """The 'for accuracy' step: honest metrics on a labelled holdout the
    model never saw. Compare against the card's CV metrics — a big drop
    means drift or an over-fit."""
    from sklearn.metrics import (confusion_matrix, f1_score, precision_score,
                                 recall_score, roc_auc_score)

    pipeline, card = store.load_model(model_name)
    y, _ = _labels(df, label_column, card.get("positive_label"))
    _check_schema(df, card)
    features = card["features_numeric"] + card["features_categorical"]
    proba = pipeline.predict_proba(df.loc[y.index, features])[:, 1]
    pred = (proba >= card.get("threshold", 0.5)).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    holdout = {
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y, proba)), 4) if y.nunique() > 1 else None,
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
    store.record("fraud_evaluate", params={"model": model_name},
                 summary={"f1": holdout["f1"]})
    return {
        "holdout_metrics": holdout,
        "cv_metrics_at_training": card.get("cv_metrics"),
        "rows_evaluated": int(len(y)),
        "note": "Holdout metrics well below the CV metrics mean drift or "
                "overfitting — retrain on fresher data.",
    }


def list_models() -> list[dict[str, Any]]:
    """Every saved ModelCard (metrics + features, never data)."""
    return store.model_cards()
