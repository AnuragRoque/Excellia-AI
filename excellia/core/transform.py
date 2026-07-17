"""AI-assisted transformation: propose -> preview -> confirm -> apply.

The LLM maps an instruction ("split address into street/city/pin") to a
RECIPE: an ordered list of deterministic ``clean`` ops, plus ``llm_map``
steps only where semantics demand a model (categorise, extract meaning).
Nothing is ever applied silently: ``preview`` shows before/after on a
sample; ``apply`` writes to NEW ``_ai``-suffixed columns unless
``replace=True``. Recipes are JSON, saved via the workspace store, and
replayable on next month's file.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd

from excellia.core import clean
from excellia.core.llm import Ollama

_SAMPLE_ROWS = 20
_LLM_MAP_WORKERS = 4

# clean ops that transform cell VALUES in-place (the _ai redirect applies);
# everything else changes structure (new/dropped columns or rows) and is
# applied as-is — the preview step is the safety net there.
_VALUE_OPS = {"trim", "case", "replace_text", "remove_chars", "slice_text",
              "absolute", "strip_currency", "parse_date", "fill_down"}


class TransformError(ValueError):
    """Invalid recipe or step. Message names the fix."""


def _ops_help() -> str:
    return "\n".join(f"  - {name}: {desc}" for name, desc in sorted(clean.list_ops().items()))


_SYSTEM = """You translate a data-cleaning instruction into a JSON recipe of \
deterministic operations. Use deterministic ops for everything mechanical; use \
"llm_map" ONLY when the step needs semantic understanding (classify, extract \
meaning, rewrite text).

Available deterministic ops (op -> params are keyword arguments):
{ops}
llm_map params: {{"column": source column, "into": new column name, \
"instruction": what to produce per cell}}

Reply with ONLY JSON:
{{"steps": [{{"op": name, "params": {{...}}}}, ...], "note": "one sentence on the approach"}}
Use ONLY column names that exist in the data. Prefer ONE precise step over many."""


def validate_recipe(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    """Check recipe shape and op names; returns the steps. Instructive errors."""
    if not isinstance(recipe, dict) or not isinstance(recipe.get("steps"), list):
        raise TransformError('A recipe is {"steps": [{"op": ..., "params": {...}}]}')
    steps = recipe["steps"]
    if not steps:
        raise TransformError("Recipe has no steps — nothing to do")
    for i, step in enumerate(steps):
        name = (step or {}).get("op")
        if name != "llm_map" and name not in clean.OPS:
            raise TransformError(
                f"Step {i + 1}: unknown op '{name}'. Available: "
                f"llm_map, {', '.join(sorted(clean.OPS))}"
            )
        if name == "llm_map":
            params = step.get("params", {}) or {}
            missing = {"column", "into", "instruction"} - set(params)
            if missing:
                raise TransformError(
                    f"Step {i + 1}: llm_map needs params {sorted(missing)} "
                    "(column, into, instruction)"
                )
    return steps


def _llm_map(df: pd.DataFrame, column: str, into: str, instruction: str,
             llm: Ollama) -> pd.DataFrame:
    """Per-row LLM op with a strict output schema; parse failure -> ''.

    Runs threaded; identical input values are computed once."""
    if column not in df.columns:
        raise TransformError(
            f"llm_map: column '{column}' not found. Actual columns: {list(df.columns)}"
        )
    distinct = df[column].astype(str).fillna("").unique().tolist()

    def one(value: str) -> str:
        if not value.strip() or value.strip().lower() in ("nan", "none"):
            return ""
        reply = llm.json_call(
            f"Input value: {json.dumps(value)}\nTask: {instruction}\n"
            'Reply with ONLY JSON: {"value": "the result"}',
            system="You transform one spreadsheet cell at a time. Output only the "
                   "requested value, never an explanation.",
        )
        out = reply.get("value")
        return str(out) if out is not None and reply.get("reason") != "parse_failed" else ""

    with ThreadPoolExecutor(max_workers=_LLM_MAP_WORKERS) as pool:
        mapped = dict(zip(distinct, pool.map(one, distinct)))
    df = df.copy()
    df[into] = df[column].astype(str).fillna("").map(mapped)
    return df


def apply(df: pd.DataFrame, recipe: dict[str, Any], replace: bool = False,
          llm: Ollama | None = None) -> pd.DataFrame:
    """Execute a recipe on a DataFrame, returning a NEW DataFrame.

    Non-destructive by default: value-transforming ops write to
    ``<column>_ai`` copies; pass ``replace=True`` to modify the columns
    themselves. Structural ops (split/concat/dedupe/...) always apply
    as previewed. The caller's DataFrame and file are never mutated.
    """
    steps = validate_recipe(recipe)
    for step in steps:
        name, params = step["op"], dict(step.get("params", {}) or {})
        if name == "llm_map":
            df = _llm_map(df, llm=llm or Ollama(), **params)
        elif not replace and name in _VALUE_OPS:
            targets = params.get("columns") or params.get("column")
            if targets is None:
                df = clean.OPS[name](df, **params)
                continue
            targets = [targets] if isinstance(targets, str) else list(targets)
            missing = [c for c in targets if c not in df.columns]
            if missing:
                raise TransformError(
                    f"{name}: column(s) {missing} not found. "
                    f"Actual columns: {list(df.columns)}"
                )
            df = df.copy()
            renamed = []
            for col in targets:
                df[f"{col}_ai"] = df[col]
                renamed.append(f"{col}_ai")
            key = "columns" if "columns" in params else "column"
            params[key] = renamed if key == "columns" else renamed[0]
            df = clean.OPS[name](df, **params)
        else:
            df = clean.OPS[name](df, **params)
    return df


def preview(df: pd.DataFrame, instruction: str, llm: Ollama | None = None,
            sample_rows: int = _SAMPLE_ROWS) -> dict[str, Any]:
    """Ask the LLM for a recipe and dry-run it on a sample. Changes nothing.

    Returns {recipe, before, after, note}. The caller confirms by
    passing the recipe to ``apply`` (or saving it for ``run_recipe``).
    """
    llm = llm or Ollama()
    sample_csv = df.head(sample_rows).to_csv(index=False)
    if len(sample_csv) > 4000:
        sample_csv = sample_csv[:4000] + "\n...truncated..."
    reply = llm.json_call(
        f"Columns: {list(df.columns)}\nFirst rows (CSV):\n{sample_csv}\n\n"
        f"Instruction: {instruction}",
        system=_SYSTEM.format(ops=_ops_help()),
    )
    if reply.get("reason") == "parse_failed":
        raise TransformError(
            "The local model could not produce a valid recipe. Rephrase the "
            "instruction naming exact columns, or build the recipe by hand from "
            f"these ops: {', '.join(sorted(clean.OPS))}"
        )
    recipe = {"instruction": instruction, "steps": reply.get("steps"),
              "note": reply.get("note", "")}
    validate_recipe(recipe)

    sample = df.head(sample_rows).copy()
    after = apply(sample, recipe, replace=False, llm=llm)
    return {
        "recipe": recipe,
        "before": json.loads(sample.astype(object).where(sample.notna(), None)
                             .to_json(orient="records")),
        "after": json.loads(after.astype(object).where(after.notna(), None)
                            .to_json(orient="records")),
        "note": recipe["note"],
        "next_step": "If this looks right, run transform_apply with this exact recipe.",
    }
