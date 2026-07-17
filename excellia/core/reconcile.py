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


def _variance(va, vb) -> dict:
    """diff_abs / diff_pct for a differing numeric pair (else empty)."""
    na, nb = pd.to_numeric(pd.Series([va, vb]), errors="coerce")
    if pd.isna(na) or pd.isna(nb):
        return {}
    diff = float(nb - na)
    return {
        "diff_abs": round(diff, 6),
        "diff_pct": round(100.0 * diff / abs(na), 4) if na else None,
    }


def reconcile(
    a: pd.DataFrame,
    b: pd.DataFrame,
    keys: list[str],
    tolerance: dict | None = None,
    fuzzy_keys: float | None = None,
) -> ReconcileResult:
    """Match rows of ``a`` against ``b`` on ``keys``.

    ``tolerance`` keys (all optional):
      numeric: absolute difference allowed between numeric fields
      days:    date fields may differ by up to this many days
      fuzzy:   0–1 similarity ratio; string fields at or above it match

    ``fuzzy_keys`` (opt-in, 0–1): after exact key matching, leftover
    records whose concatenated keys are at least this similar are paired
    as level-``L3`` matches (typo'd invoice numbers, transliterated names).

    Every matched/discrepant record carries ``match_level``: ``L1`` exact
    on every field · ``L2`` within tolerance · ``L3`` fuzzy-key match.
    Numeric differences carry ``diff_abs``/``diff_pct`` variance.

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

    def _match_groups(a_group: pd.DataFrame, b_group: pd.DataFrame,
                      key_level: str, key_similarity: float | None = None) -> None:
        """Compare one key-group pair and file each A row into a bucket."""
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
                entry = {
                    **{k: record.get(k) for k in keys},
                    "match_level": key_level,
                    "a": record,
                    "b": _record(row_b.drop(norm_keys)),
                    "differences": {
                        col: {"a": None if pd.isnull(d["a"]) else d["a"],
                              "b": None if pd.isnull(d["b"]) else d["b"],
                              **_variance(d["a"], d["b"])}
                        for col, d in diffs.items()
                    },
                }
                if key_similarity is not None:
                    entry["key_similarity"] = round(key_similarity, 4)
                result.discrepancies.append(entry)
            else:
                # L1 only when every field matches with ZERO tolerance
                if key_level == "L3":
                    level = "L3"
                elif tolerance and any(
                    not _values_equal(row_a[c], row_b[c], {}) for c in compare_cols
                ):
                    level = "L2"
                else:
                    level = "L1"
                record["match_level"] = level
                if key_similarity is not None:
                    record["key_similarity"] = round(key_similarity, 4)
                result.matched.append(record)

    unmatched_a_groups: dict[tuple, pd.DataFrame] = {}
    for key_vals, a_group in a.groupby(norm_keys, sort=False):
        key_vals = _as_tuple(key_vals)
        b_group = b_groups.get(key_vals)
        if b_group is None:
            unmatched_a_groups[key_vals] = a_group
            continue
        matched_b_keys.add(key_vals)
        _match_groups(a_group, b_group, key_level="exact")

    # opt-in second pass: fuzzy-match leftover keys (L3)
    if fuzzy_keys:
        leftover_b = {k: g for k, g in b_groups.items() if k not in matched_b_keys}
        for key_vals, a_group in list(unmatched_a_groups.items()):
            a_key = " ".join(key_vals)
            best_key, best_sim = None, 0.0
            for b_key_vals in leftover_b:
                sim = SequenceMatcher(None, a_key, " ".join(b_key_vals)).ratio()
                if sim > best_sim:
                    best_key, best_sim = b_key_vals, sim
            if best_key is not None and best_sim >= fuzzy_keys:
                _match_groups(a_group, leftover_b.pop(best_key),
                              key_level="L3", key_similarity=best_sim)
                matched_b_keys.add(best_key)
                del unmatched_a_groups[key_vals]

    for a_group in unmatched_a_groups.values():
        for _, row in a_group.iterrows():
            result.only_in_a.append(_record(row.drop(norm_keys)))
    for key_vals, b_group in b_groups.items():
        if key_vals not in matched_b_keys:
            for _, row in b_group.iterrows():
                result.only_in_b.append(_record(row.drop(norm_keys)))

    return result


# --- reconciliation profiles: one-click monthly runs ------------------

def run_profile(a: pd.DataFrame, b: pd.DataFrame, profile: dict) -> dict:
    """Run a saved reconciliation profile end to end.

    Profile spec (all but ``keys`` optional):
      {name, keys, tolerance, fuzzy_keys,
       pre_recipe_a, pre_recipe_b,   # clean.py step lists run before matching
       dedupe_a, dedupe_b}           # {columns, keep | aggregate} per source

    Returns {result, summary} where summary adds match_rate, level
    counts, and per-field variance totals. The caller owns report
    writing and persistence.
    """
    from excellia.core import clean

    if not isinstance(profile, dict) or not profile.get("keys"):
        raise ValueError(
            'A reconciliation profile needs at least {"keys": [...]}. Optional: '
            "tolerance, fuzzy_keys, pre_recipe_a/b (clean steps), dedupe_a/b.")

    for side, df_name in (("a", "pre_recipe_a"), ("b", "pre_recipe_b")):
        steps = profile.get(df_name)
        if steps:
            if side == "a":
                a = clean.apply_ops(a, steps)
            else:
                b = clean.apply_ops(b, steps)
    for side, key in (("a", "dedupe_a"), ("b", "dedupe_b")):
        spec = profile.get(key)
        if spec:
            kwargs = {k: v for k, v in spec.items()
                      if k in ("columns", "keep", "aggregate")}
            if side == "a":
                a = clean.dedupe(a, **kwargs)
            else:
                b = clean.dedupe(b, **kwargs)

    result = reconcile(a, b, keys=profile["keys"],
                       tolerance=profile.get("tolerance"),
                       fuzzy_keys=profile.get("fuzzy_keys"))

    counts = result.summary()
    total_a = counts["matched"] + counts["discrepancies"] + counts["only_in_a"]
    levels: dict[str, int] = {}
    for rec in result.matched:
        levels[rec.get("match_level", "?")] = levels.get(rec.get("match_level", "?"), 0) + 1
    variance_totals: dict[str, float] = {}
    for d in result.discrepancies:
        for col, diff in d.get("differences", {}).items():
            if "diff_abs" in diff:
                variance_totals[col] = round(
                    variance_totals.get(col, 0.0) + abs(diff["diff_abs"]), 6)

    return {
        "result": result,
        "summary": {
            **counts,
            "match_rate": round(counts["matched"] / total_a, 4) if total_a else None,
            "match_levels": levels,
            "variance_totals_abs": variance_totals,
            "profile": profile.get("name"),
        },
    }
