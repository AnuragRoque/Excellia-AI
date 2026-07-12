"""Reconciliation: match records across two sources by key columns.

Ported and generalised from Limestone's (TRPW) reconciliation
pipeline. Highest-value enterprise capability.
"""

from __future__ import annotations

from difflib import SequenceMatcher

import pandas as pd

from excellia.core.models import ReconcileResult


def _normalise_key(series: pd.Series) -> pd.Series:
    """Keys match case- and whitespace-insensitively."""
    return series.astype(str).str.strip().str.lower()


def _record(row: pd.Series) -> dict:
    """Row as a JSON-safe dict (NaN/NaT become None)."""
    return {k: (None if pd.isnull(v) else v) for k, v in row.items()}


def _values_equal(va, vb, tolerance: dict) -> bool:
    if pd.isnull(va) and pd.isnull(vb):
        return True
    if pd.isnull(va) or pd.isnull(vb):
        return False

    # numeric comparison with absolute tolerance (amount rounding)
    na, nb = pd.to_numeric(pd.Series([va, vb]), errors="coerce")
    if pd.notna(na) and pd.notna(nb):
        return abs(na - nb) <= tolerance.get("numeric", 0)

    # date comparison with a day window
    days = tolerance.get("days", 0)
    da, db = pd.to_datetime(pd.Series([va, vb]), errors="coerce", format="mixed")
    if pd.notna(da) and pd.notna(db):
        return abs((da - db).days) <= days

    # string comparison: case/space-insensitive, optionally fuzzy
    sa, sb = str(va).strip().lower(), str(vb).strip().lower()
    if sa == sb:
        return True
    fuzzy = tolerance.get("fuzzy", 0)
    return bool(fuzzy) and SequenceMatcher(None, sa, sb).ratio() >= fuzzy


def reconcile(
    a: pd.DataFrame,
    b: pd.DataFrame,
    keys: list[str],
    tolerance: dict | None = None,
) -> ReconcileResult:
    """Match rows of ``a`` against ``b`` on ``keys``.

    ``tolerance`` keys (all optional):
      numeric: absolute difference allowed between numeric fields
      days:    date fields may differ by up to this many days
      fuzzy:   0–1 similarity ratio; string fields at or above it match

    Handles many-to-one and one-to-many (every key-pair combination is
    compared). Returns four buckets: matched, only_in_a, only_in_b,
    and discrepancies (matched on keys but differing elsewhere, with
    the differing fields listed per record).
    """
    tolerance = tolerance or {}
    for key in keys:
        missing = [name for name, df in (("a", a), ("b", b)) if key not in df.columns]
        if missing:
            raise ValueError(
                f"Key column '{key}' not found in source(s): {', '.join(missing)}. "
                f"Columns in a: {list(a.columns)}; in b: {list(b.columns)}")

    a = a.copy()
    b = b.copy()
    for key in keys:
        a[f"__key_{key}"] = _normalise_key(a[key])
        b[f"__key_{key}"] = _normalise_key(b[key])
    norm_keys = [f"__key_{k}" for k in keys]

    # columns to compare beyond the keys: shared between both sources
    compare_cols = [c for c in a.columns
                    if c in b.columns and c not in keys and not c.startswith("__key_")]

    def _as_tuple(k) -> tuple:
        return k if isinstance(k, tuple) else (k,)

    b_groups = {_as_tuple(k): g for k, g in b.groupby(norm_keys, sort=False)}
    matched_b_keys: set = set()
    result = ReconcileResult()

    for key_vals, a_group in a.groupby(norm_keys, sort=False):
        key_vals = _as_tuple(key_vals)
        b_group = b_groups.get(key_vals)
        if b_group is None:
            for _, row in a_group.iterrows():
                result.only_in_a.append(_record(row.drop(norm_keys)))
            continue
        matched_b_keys.add(key_vals)

        for _, row_a in a_group.iterrows():
            diffs: dict[str, dict] = {}
            row_b = None
            # one-to-many: match this A row against the closest B row —
            # the one with the fewest field differences
            for _, candidate in b_group.iterrows():
                candidate_diffs = {
                    col: {"a": row_a[col], "b": candidate[col]}
                    for col in compare_cols
                    if not _values_equal(row_a[col], candidate[col], tolerance)
                }
                if row_b is None or len(candidate_diffs) < len(diffs):
                    row_b, diffs = candidate, candidate_diffs
                if not diffs:
                    break

            record = _record(row_a.drop(norm_keys))
            if diffs:
                result.discrepancies.append({
                    **{k: record.get(k) for k in keys},
                    "a": record,
                    "b": _record(row_b.drop(norm_keys)),
                    "differences": {
                        col: {"a": None if pd.isnull(d["a"]) else d["a"],
                              "b": None if pd.isnull(d["b"]) else d["b"]}
                        for col, d in diffs.items()
                    },
                })
            else:
                result.matched.append(record)

    for key_vals, b_group in b_groups.items():
        if key_vals not in matched_b_keys:
            for _, row in b_group.iterrows():
                result.only_in_b.append(_record(row.drop(norm_keys)))

    return result
