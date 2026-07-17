"""KYC: hybrid name matching and entity-level dedupe.

The KYC tool's algorithm, generalised: deterministic SequenceMatcher
similarity always runs first; an offline LLM verdict is opt-in on top
(``llm_verify``), and a parse failure degrades to the deterministic
score with ``verdict: "unverified"`` — never a crash. ID-format
validation is the existing ``kyc`` ruleset in ``validate``.

Entity dedupe here differs from ``anomaly``'s near-duplicate flags:
anomaly FLAGS suspicious row pairs; ``dedupe`` RESOLVES entities into
clusters and picks a canonical row per cluster.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from excellia.core.llm import Ollama

_MAX_PAIRS = 20_000  # nC2 guard: name the fix instead of hanging

_VERIFY_SYSTEM = (
    "You are a strict fraud-screening name assistant for KYC. Decide whether two "
    "personal/company names refer to the SAME entity, allowing for transliteration, "
    "initials, honorifics, and typos — but never guessing beyond the strings given. "
    'Reply with ONLY JSON: {"status": "match" or "no_match", "match_percent": 0-100, '
    '"reason": "one short sentence"}'
)


class KycError(ValueError):
    """Bad columns/params. Message names the fix."""


def _normalise(name: Any) -> str:
    s = str(name).strip().lower()
    s = re.sub(r"[^\w\s]", " ", s)      # strip punctuation
    return re.sub(r"\s+", " ", s).strip()  # collapse spaces


def name_similarity(a: Any, b: Any) -> float:
    """Deterministic 0-100 similarity between two names."""
    na, nb = _normalise(a), _normalise(b)
    if not na or not nb:
        return 0.0
    return round(SequenceMatcher(None, na, nb).ratio() * 100, 2)


def _col(df: pd.DataFrame, name: str) -> str:
    if name not in df.columns:
        raise KycError(
            f"Column '{name}' not found. Actual columns: {list(df.columns)}")
    return name


def _verify(pair: dict, llm: Ollama) -> dict:
    reply = llm.json_call(
        f'Name A: "{pair["name_a"]}"\nName B: "{pair["name_b"]}"\n'
        f"Deterministic similarity: {pair['similarity']}%",
        system=_VERIFY_SYSTEM,
    )
    if reply.get("reason") == "parse_failed" or reply.get("status") not in (
            "match", "no_match"):
        return {**pair, "verdict": "unverified",
                "reason": "LLM output unparseable; deterministic score stands"}
    return {
        **pair,
        "verdict": reply["status"],
        "llm_percent": reply.get("match_percent"),
        "reason": str(reply.get("reason", ""))[:300],
    }


def match_names(
    df: pd.DataFrame,
    col_a: str | None = None,
    col_b: str | None = None,
    group_by: str | None = None,
    llm_verify: bool = False,
    seq_threshold: float = 50.0,
    llm: Ollama | None = None,
) -> dict[str, Any]:
    """Bulk name matching, two modes.

    Pairwise: ``col_a`` vs ``col_b`` per row (declared vs registry name).
    Cross:    all name pairs within each ``group_by`` bucket over ``col_a``
              (or over the whole file when ``group_by`` is None — guarded).

    Pairs at/above ``seq_threshold`` similarity are candidates; with
    ``llm_verify`` each candidate also gets an offline-LLM verdict.
    """
    pairs: list[dict] = []
    if col_a and col_b:
        _col(df, col_a), _col(df, col_b)
        for i, (va, vb) in enumerate(zip(df[col_a], df[col_b])):
            if pd.isnull(va) or pd.isnull(vb):
                continue
            sim = name_similarity(va, vb)
            pairs.append({"row": i + 2, "name_a": str(va), "name_b": str(vb),
                          "similarity": sim})
    elif col_a:
        _col(df, col_a)
        groups = (df.groupby(df[group_by].astype(str).str.strip().str.lower())
                  if group_by and _col(df, group_by) else [("(all)", df)])
        n_pairs = 0
        for _, g in groups:
            names = [(i, v) for i, v in zip(g.index, g[col_a]) if pd.notnull(v)]
            n_pairs += len(names) * (len(names) - 1) // 2
        if n_pairs > _MAX_PAIRS:
            raise KycError(
                f"{n_pairs} name pairs to compare — too many for one call. Add a "
                "group_by column (branch, city, account bucket) to shrink the "
                f"comparison sets under {_MAX_PAIRS}.")
        for _, g in groups:
            names = [(i, v) for i, v in zip(g.index, g[col_a]) if pd.notnull(v)]
            for x in range(len(names)):
                for y in range(x + 1, len(names)):
                    ia, va = names[x]
                    ib, vb = names[y]
                    sim = name_similarity(va, vb)
                    if sim >= seq_threshold:
                        pairs.append({
                            "row_a": int(ia) + 2, "row_b": int(ib) + 2,
                            "name_a": str(va), "name_b": str(vb),
                            "similarity": sim})
    else:
        raise KycError(
            "Pass col_a+col_b (pairwise) or col_a [+ group_by] (cross-compare).")

    candidates = [p for p in pairs if p["similarity"] >= seq_threshold]
    if llm_verify and candidates:
        llm = llm or Ollama()
        candidates = [_verify(p, llm) for p in candidates]
    else:
        candidates = [{**p, "verdict": "candidate"} for p in candidates]

    return {
        "pairs": candidates,
        "summary": {
            "compared": len(pairs) if col_a and col_b else None,
            "candidates": len(candidates),
            "llm_verified": bool(llm_verify),
            "seq_threshold": seq_threshold,
            "note": "similarity is deterministic (0-100); verdict is "
                    "match/no_match when LLM-verified, else 'candidate'. "
                    "Rows are Excel rows (data starts at 2).",
        },
    }


def dedupe(
    df: pd.DataFrame,
    columns: list[str],
    threshold: float = 85.0,
    strategy: str = "most_complete",
) -> dict[str, Any]:
    """Entity resolution: cluster near-duplicate rows and pick a canonical one.

    Similarity runs on the concatenated ``columns`` per row, compared
    over a sorted neighbourhood (O(n·k), like anomaly's near-dup pass).
    ``strategy``: which row survives per cluster — ``first`` | ``last`` |
    ``most_complete`` (fewest empty cells). Returns clusters, merge log,
    and the deduped rows — the caller writes them; nothing is modified.
    """
    for c in columns:
        _col(df, c)
    if strategy not in ("first", "last", "most_complete"):
        raise KycError("strategy must be first, last, or most_complete")

    keys = df[columns].astype(str).agg(" ".join, axis=1).map(_normalise)
    order = keys.sort_values(kind="stable").index.tolist()

    parent = {i: i for i in df.index}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    window = 8
    for pos in range(len(order)):
        for nxt in range(pos + 1, min(pos + 1 + window, len(order))):
            i, j = order[pos], order[nxt]
            if SequenceMatcher(None, keys[i], keys[j]).ratio() * 100 >= threshold:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in df.index:
        clusters.setdefault(find(i), []).append(i)

    merges = []
    keep_rows = []
    for members in clusters.values():
        if len(members) == 1:
            keep_rows.append(members[0])
            continue
        if strategy == "first":
            canonical = members[0]
        elif strategy == "last":
            canonical = members[-1]
        else:
            canonical = max(members, key=lambda i: df.loc[i].notna().sum())
        keep_rows.append(canonical)
        merges.append({
            "canonical_row": int(canonical) + 2,
            "merged_rows": [int(m) + 2 for m in members if m != canonical],
            "values": {c: (None if pd.isnull(df.at[canonical, c])
                           else df.at[canonical, c]) for c in columns},
        })

    deduped = df.loc[sorted(keep_rows)]
    return {
        "rows_before": len(df),
        "rows_after": len(deduped),
        "clusters_merged": len(merges),
        "merges": merges,
        "deduped": deduped,
        "note": "Rows are Excel rows (data starts at 2). Nothing was modified — "
                "write 'deduped' where you want it.",
    }
