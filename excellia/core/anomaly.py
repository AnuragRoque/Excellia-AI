"""Anomaly detection: statistical flags for what rules cannot catch.

Isolation Forest lifted from the old Excellia GUI; near-duplicate
matching ported from the KYC tool's SequenceMatcher approach.

Row numbering convention matches ``validate``: ``Flag.row`` is the
Excel row number (header = 1, first data row = 2).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from excellia.core.ingest import nonempty
from excellia.core.models import Flag

# Compare each row only to its k nearest neighbours in sorted order so
# near-duplicate detection stays O(n·k) instead of O(n²).
_NEAR_DUP_NEIGHBOURS = 3
_NEAR_DUP_THRESHOLD = 0.9


def _numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Numeric view of df: native numeric columns plus object columns
    that are mostly coercible. Missing values filled with the median."""
    out = pd.DataFrame(index=df.index)
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            coerced = df[col].astype(float)
        else:
            coerced = pd.to_numeric(df[col], errors="coerce")
            if coerced.notna().mean() < 0.5:
                continue
        med = coerced.median()
        out[col] = coerced.fillna(0.0 if pd.isnull(med) else med)
    return out


def _excel_row(df: pd.DataFrame, idx_label) -> int:
    return df.index.get_loc(idx_label) + 2


def _isolation_forest_flags(df: pd.DataFrame, X: pd.DataFrame, sensitivity: float) -> list[Flag]:
    from sklearn.ensemble import IsolationForest

    if X.shape[1] == 0 or len(X) < 10:
        return []

    forest = IsolationForest(contamination=sensitivity, random_state=42, n_jobs=-1)
    predictions = forest.fit_predict(X)
    scores = forest.decision_function(X)  # lower = more anomalous

    # z-scores per feature, used only to explain WHY a row was flagged
    std = X.std().replace(0, 1)
    z = (X - X.mean()) / std

    flags: list[Flag] = []
    outlier_scores = scores[predictions == -1]
    score_span = (scores.max() - outlier_scores.min()) or 1.0
    for pos, idx in enumerate(X.index):
        if predictions[pos] != -1:
            continue
        top = z.loc[idx].abs().nlargest(3)
        culprits = [c for c in top.index if top[c] > 1.5] or list(top.index[:1])
        detail = "; ".join(f"{c}={df.at[idx, c]}" for c in culprits)
        confidence = float(np.clip((scores.max() - scores[pos]) / score_span, 0.0, 1.0))
        flags.append(Flag(
            row=_excel_row(df, idx),
            kind="multivariate_outlier",
            confidence=round(confidence, 3),
            reason=f"Row doesn't fit the overall data pattern; most unusual fields: {detail}",
            columns=culprits,
        ))
    return flags


def _column_outlier_flags(df: pd.DataFrame, X: pd.DataFrame) -> list[Flag]:
    flags: list[Flag] = []
    for col in X.columns:
        series = X[col]
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
        for idx in series.index[(series < lo) | (series > hi)]:
            val = series.at[idx]
            dist = (lo - val) if val < lo else (val - hi)
            confidence = float(np.clip(0.5 + 0.5 * (dist / (3 * iqr)), 0.5, 1.0))
            flags.append(Flag(
                row=_excel_row(df, idx),
                kind="column_outlier",
                confidence=round(confidence, 3),
                reason=f"'{col}' value {df.at[idx, col]} is far outside the column's "
                       f"typical range ({q1:g}–{q3:g})",
                columns=[col],
            ))
    return flags


def _rare_category_flags(df: pd.DataFrame) -> list[Flag]:
    flags: list[Flag] = []
    for col in df.columns:
        values = nonempty(df[col]).astype(str).str.strip()
        n = len(values)
        if n < 20:
            continue
        counts = values.value_counts()
        # only treat as categorical when a handful of values dominate
        if len(counts) > max(10, n * 0.1):
            continue
        threshold = max(1, int(n * 0.01))
        for category, count in counts[counts <= threshold].items():
            for idx in values.index[values == category]:
                flags.append(Flag(
                    row=_excel_row(df, idx),
                    kind="rare_category",
                    confidence=round(1.0 - count / n, 3),
                    reason=f"'{col}' value '{category}' appears only {count} of {n} times "
                           f"in an otherwise repetitive column",
                    columns=[col],
                ))
    return flags


def _near_duplicate_flags(df: pd.DataFrame) -> list[Flag]:
    """KYC-tool approach: SequenceMatcher similarity between row strings.
    Rows are sorted so near-identical strings land next to each other."""
    joined = df.fillna("").astype(str).apply(
        lambda r: " | ".join(v.strip().lower() for v in r), axis=1)
    order = joined.sort_values().index.tolist()

    flags: list[Flag] = []
    seen: set[frozenset] = set()
    for i, idx_a in enumerate(order):
        for j in range(i + 1, min(i + 1 + _NEAR_DUP_NEIGHBOURS, len(order))):
            idx_b = order[j]
            a, b = joined.at[idx_a], joined.at[idx_b]
            if a == b:
                continue  # exact duplicates are validate()'s job
            matcher = SequenceMatcher(None, a, b)
            if matcher.real_quick_ratio() < _NEAR_DUP_THRESHOLD:
                continue
            ratio = matcher.ratio()
            if ratio < _NEAR_DUP_THRESHOLD:
                continue
            pair = frozenset((idx_a, idx_b))
            if pair in seen:
                continue
            seen.add(pair)
            row_a, row_b = _excel_row(df, idx_a), _excel_row(df, idx_b)
            differing = [c for c in df.columns
                         if str(df.at[idx_a, c]).strip().lower() != str(df.at[idx_b, c]).strip().lower()]
            flags.append(Flag(
                row=row_a,
                kind="near_duplicate",
                confidence=round(ratio, 3),
                reason=f"Row {row_a} is {ratio:.0%} similar to row {row_b}; "
                       f"they differ only in: {', '.join(differing[:5])}",
                columns=differing[:5],
            ))
    return flags


def _pattern_break_flags(df: pd.DataFrame) -> list[Flag]:
    """A column that is 'always 10 digits' suddenly has an 8-digit entry."""

    def shape(v: str) -> str:
        return re.sub(r"[A-Za-z]", "A", re.sub(r"[0-9]", "9", v))

    flags: list[Flag] = []
    for col in df.columns:
        values = nonempty(df[col]).astype(str).str.strip()
        if len(values) < 20 or pd.api.types.is_numeric_dtype(df[col]):
            continue
        shapes = values.map(shape)
        counts = shapes.value_counts()
        dominant, dominant_count = counts.index[0], counts.iloc[0]
        share = dominant_count / len(shapes)
        if share < 0.9 or share == 1.0:
            continue
        for idx in shapes.index[shapes != dominant]:
            flags.append(Flag(
                row=_excel_row(df, idx),
                kind="pattern_break",
                confidence=round(share, 3),
                reason=f"'{col}' values almost always look like '{dominant}' but this "
                       f"one ('{df.at[idx, col]}') looks like '{shapes.at[idx]}'",
                columns=[col],
            ))
    return flags


def detect_anomalies(df: pd.DataFrame, sensitivity: float = 0.05) -> list[Flag]:
    """Find statistically suspicious rows.

    Combines: Isolation Forest (multivariate), IQR per numeric column,
    rare-category flagging, near-duplicate rows, and pattern-break
    detection. Every Flag carries a confidence score and a "why
    flagged" explanation. ``sensitivity`` is the Isolation Forest
    contamination (expected outlier fraction, 0–0.5).
    """
    if not 0 < sensitivity < 0.5:
        raise ValueError("sensitivity must be between 0 and 0.5 (exclusive)")
    if df.empty:
        return []

    X = _numeric_frame(df)
    flags = _isolation_forest_flags(df, X, sensitivity)
    flags += _column_outlier_flags(df, X)
    flags += _rare_category_flags(df)
    flags += _near_duplicate_flags(df)
    flags += _pattern_break_flags(df)

    flags.sort(key=lambda f: (f.row, -f.confidence))
    return flags
