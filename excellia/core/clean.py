"""Deterministic cleaning ops — the recipe atoms.

Limestone's formula library + the GUI's edit panel, unified. Every op
is ``{"op": name, "params": {...}}`` JSON; ``apply_ops`` runs an
ordered list of them. Zero LLM anywhere in this module — if regex or
pandas can do it, the model must not.

All ops are pure: they take a DataFrame and return a NEW DataFrame.
Row-numbering caveat: ops that drop or reorder rows (dedupe,
drop_empty_rows, set_header) invalidate earlier Excel row references.
"""

from __future__ import annotations

import re
from typing import Any, Callable

import pandas as pd

from excellia.core.ingest import nonempty

OPS: dict[str, Callable] = {}


class CleanError(ValueError):
    """Bad op name, params, or missing column. Message is instructive."""


def _op(name: str):
    def deco(fn: Callable) -> Callable:
        OPS[name] = fn
        return fn
    return deco


def list_ops() -> dict[str, str]:
    """Op name -> one-line description (drawn from each op's docstring)."""
    return {name: (fn.__doc__ or "").strip().splitlines()[0] for name, fn in OPS.items()}


def _cols(df: pd.DataFrame, columns: list[str] | str | None) -> list[str]:
    """Resolve a columns param; instructive error on a miss."""
    if columns is None:
        return list(df.columns)
    if isinstance(columns, str):
        columns = [columns]
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise CleanError(
            f"Column(s) {missing} not found. Actual columns: {list(df.columns)}"
        )
    return columns


def _as_str(series: pd.Series) -> pd.Series:
    """String view that leaves real NaN alone."""
    return series.where(series.isna(), series.astype(str))


# --- whitespace & case ------------------------------------------------

@_op("trim")
def trim(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Strip leading/trailing whitespace and collapse internal runs to one space."""
    df = df.copy()
    for c in _cols(df, columns):
        # map unconditionally: pandas 3 stores text as StringDtype, not object,
        # and the isinstance guard already leaves non-strings alone
        df[c] = df[c].map(
            lambda v: re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v
        )
    return df


@_op("case")
def case(df: pd.DataFrame, columns: list[str] | str, to: str = "title") -> pd.DataFrame:
    """Change text case: to = upper | lower | title | sentence."""
    fns = {
        "upper": str.upper,
        "lower": str.lower,
        "title": str.title,
        "sentence": lambda s: s[:1].upper() + s[1:].lower() if s else s,
    }
    if to not in fns:
        raise CleanError(f"Unknown case '{to}'. Use one of: {', '.join(fns)}")
    df = df.copy()
    for c in _cols(df, columns):
        df[c] = df[c].map(lambda v: fns[to](v) if isinstance(v, str) else v)
    return df


# --- find / replace / remove -----------------------------------------

@_op("replace_text")
def replace_text(df: pd.DataFrame, columns: list[str] | str, find: str,
                 replace: str = "", regex: bool = False) -> pd.DataFrame:
    """Replace text in cells; set regex=true for pattern replaces."""
    df = df.copy()
    for c in _cols(df, columns):
        df[c] = _as_str(df[c]).str.replace(find, replace, regex=regex)
    return df


@_op("remove_chars")
def remove_chars(df: pd.DataFrame, columns: list[str] | str, chars: str) -> pd.DataFrame:
    """Delete every occurrence of the given characters from cells."""
    df = df.copy()
    pattern = "[" + re.escape(chars) + "]"
    for c in _cols(df, columns):
        df[c] = _as_str(df[c]).str.replace(pattern, "", regex=True)
    return df


# --- split / concat / slice ------------------------------------------

@_op("split_column")
def split_column(df: pd.DataFrame, column: str, delimiter: str,
                 into: list[str] | None = None) -> pd.DataFrame:
    """Split one column on a delimiter into new columns (named by `into`)."""
    (column,) = _cols(df, column)
    df = df.copy()
    parts = _as_str(df[column]).str.split(delimiter, expand=True)
    parts = parts.apply(
        lambda s: s.map(lambda v: v.strip() if isinstance(v, str) else v)
    )
    names = into or [f"{column}_{i + 1}" for i in range(parts.shape[1])]
    for i, name in enumerate(names):
        df[name] = parts[i] if i < parts.shape[1] else None
    return df


@_op("concat_columns")
def concat_columns(df: pd.DataFrame, columns: list[str], into: str,
                   separator: str = " ") -> pd.DataFrame:
    """Join several columns into one new column with a separator."""
    cols = _cols(df, columns)
    df = df.copy()
    df[into] = (
        df[cols]
        .apply(lambda r: separator.join(str(v) for v in r if pd.notna(v)), axis=1)
    )
    return df


@_op("slice_text")
def slice_text(df: pd.DataFrame, columns: list[str] | str, side: str = "left",
               start: int = 1, length: int = 1) -> pd.DataFrame:
    """Keep part of each cell: side = left | right | mid (1-based start)."""
    if side not in ("left", "right", "mid"):
        raise CleanError("side must be left, right, or mid")
    df = df.copy()
    for c in _cols(df, columns):
        s = _as_str(df[c])
        if side == "left":
            df[c] = s.str[:length]
        elif side == "right":
            df[c] = s.str[-length:]
        else:
            df[c] = s.str[start - 1 : start - 1 + length]
    return df


# --- numbers ----------------------------------------------------------

@_op("math")
def math(df: pd.DataFrame, into: str, left: str | float, op: str,
         right: str | float) -> pd.DataFrame:
    """Arithmetic between two columns (or a column and a number): op = + - * /."""
    if op not in ("+", "-", "*", "/"):
        raise CleanError("math op must be one of + - * /")

    def operand(x):
        if isinstance(x, str):
            (x,) = _cols(df, x)
            return pd.to_numeric(df[x], errors="coerce")
        return x

    a, b = operand(left), operand(right)
    df = df.copy()
    if op == "+":
        df[into] = a + b
    elif op == "-":
        df[into] = a - b
    elif op == "*":
        df[into] = a * b
    else:
        df[into] = a / b
    return df


@_op("absolute")
def absolute(df: pd.DataFrame, columns: list[str] | str) -> pd.DataFrame:
    """Absolute value of numeric cells."""
    df = df.copy()
    for c in _cols(df, columns):
        df[c] = pd.to_numeric(df[c], errors="coerce").abs()
    return df


@_op("strip_currency")
def strip_currency(df: pd.DataFrame, columns: list[str] | str) -> pd.DataFrame:
    """Remove currency symbols/commas and convert to numbers (₹1,200.50 -> 1200.5)."""
    df = df.copy()
    for c in _cols(df, columns):
        cleaned = _as_str(df[c]).str.replace(r"[₹$€£,\s]", "", regex=True)
        df[c] = pd.to_numeric(cleaned, errors="coerce")
    return df


# --- dates ------------------------------------------------------------

@_op("parse_date")
def parse_date(df: pd.DataFrame, columns: list[str] | str,
               output_format: str = "%Y-%m-%d") -> pd.DataFrame:
    """Parse mixed date strings and reformat them (default ISO yyyy-mm-dd)."""
    df = df.copy()
    for c in _cols(df, columns):
        parsed = pd.to_datetime(df[c], errors="coerce", format="mixed", dayfirst=True)
        df[c] = parsed.dt.strftime(output_format).where(parsed.notna(), df[c])
    return df


# --- structure --------------------------------------------------------

@_op("drop_empty_rows")
def drop_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Remove rows where every cell is empty."""
    keep = df.apply(lambda r: len(nonempty(r)) > 0, axis=1)
    return df[keep].copy()


@_op("drop_empty_columns")
def drop_empty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Remove columns where every cell is empty."""
    keep = [c for c in df.columns if len(nonempty(df[c])) > 0]
    return df[keep].copy()


@_op("set_header")
def set_header(df: pd.DataFrame, row: int) -> pd.DataFrame:
    """Use Excel row N as the header, discarding everything above it."""
    pos = row - 2  # Excel row -> current data position (header was row 1)
    if not (0 <= pos < len(df)):
        raise CleanError(f"Row {row} is outside the data (rows 2..{len(df) + 1})")
    new = df.iloc[pos + 1 :].copy()
    new.columns = [str(v) for v in df.iloc[pos]]
    return new.reset_index(drop=True)


@_op("fill_down")
def fill_down(df: pd.DataFrame, columns: list[str] | str) -> pd.DataFrame:
    """Fill empty cells with the nearest value above (merged-cell fix)."""
    df = df.copy()
    for c in _cols(df, columns):
        s = df[c]
        blank = s.isna() | s.astype(str).str.strip().isin(["", "nan", "none"])
        df[c] = s.mask(blank).ffill()
    return df


@_op("dedupe")
def dedupe(df: pd.DataFrame, columns: list[str] | None = None, keep: str = "first",
           aggregate: dict[str, str] | None = None) -> pd.DataFrame:
    """Drop duplicate rows by key columns; or aggregate them (sum/max/min/first/last)."""
    key_cols = _cols(df, columns) if columns else list(df.columns)
    if aggregate:
        allowed = {"sum", "max", "min", "first", "last", "mean"}
        bad = {fn for fn in aggregate.values() if fn not in allowed}
        if bad:
            raise CleanError(f"Unknown aggregate {sorted(bad)}. Use: {sorted(allowed)}")
        _cols(df, list(aggregate))
        spec = {c: aggregate.get(c, "first") for c in df.columns if c not in key_cols}
        return df.groupby(key_cols, as_index=False, dropna=False).agg(spec)
    if keep not in ("first", "last"):
        raise CleanError("keep must be 'first' or 'last'")
    return df.drop_duplicates(subset=key_cols, keep=keep).copy()


# --- runner -----------------------------------------------------------

def apply_ops(df: pd.DataFrame, steps: list[dict[str, Any]]) -> pd.DataFrame:
    """Run an ordered list of ``{"op": name, "params": {...}}`` steps.

    Unknown ops and bad params raise CleanError naming the step index,
    the problem, and the valid options."""
    if not isinstance(steps, list):
        raise CleanError("steps must be a list of {op, params} objects")
    for i, step in enumerate(steps):
        name = (step or {}).get("op")
        if name not in OPS:
            raise CleanError(
                f"Step {i + 1}: unknown op '{name}'. Available ops: "
                f"{', '.join(sorted(OPS))}"
            )
        params = step.get("params", {}) or {}
        try:
            df = OPS[name](df, **params)
        except CleanError as e:
            raise CleanError(f"Step {i + 1} ({name}): {e}") from e
        except TypeError as e:
            raise CleanError(
                f"Step {i + 1} ({name}): bad params {sorted(params)} — {e}"
            ) from e
    return df
