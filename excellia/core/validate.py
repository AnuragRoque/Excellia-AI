"""Rule-based validation. Deterministic. No LLM. Fast. Explainable.

Lifted from the old Excellia GUI's data-quality checks (routes2.py)
and rebuilt around named, reusable rulesets. Built-in format patterns
(GST, PAN, email, ...) live in ``rules/builtin.py``.

Row numbering convention: ``Issue.row`` is the spreadsheet row as a
user sees it in Excel — the header is row 1, the first data row is 2.
"""

from __future__ import annotations

from numbers import Number

import pandas as pd

from excellia.core.ingest import nonempty
from excellia.core.models import Issue
from excellia.core.rules.builtin import FORMATS

# A ruleset is a declarative spec. Keys (all optional):
#   required:   [col, ...]            -> error on missing/empty cells
#   formats:    {col: format_name}    -> error when a value breaks the format
#   ranges:     {col: {min, max}}     -> error when outside bounds
#   unique:     [col, ...]            -> error on duplicate values
#   references: {col: [allowed, ...]} -> error when value not in lookup list
#   expressions: [{name, expr, severity?}] -> pandas-eval cross-column logic;
#                rows where expr is False get an issue
#   auto:       bool (default True)   -> also run the inferred checks below
RULESETS: dict[str, dict] = {
    "default": {},
    "kyc": {
        "formats": {"pan": "pan", "aadhaar": "aadhaar", "email": "email", "phone": "phone"},
        "unique": ["pan", "aadhaar"],
    },
    "invoice": {
        "formats": {"gstin": "gst", "gst": "gst", "ifsc": "ifsc", "email": "email"},
        "expressions": [
            {"name": "amount_positive", "expr": "amount > 0", "severity": "error"},
        ],
    },
    "payroll": {
        "formats": {"pan": "pan", "email": "email", "phone": "phone", "ifsc": "ifsc"},
        "unique": ["employee_id", "pan"],
        "expressions": [
            {"name": "net_not_above_gross", "expr": "net_pay <= gross_pay",
             "severity": "error"},
        ],
    },
    "bank-statement": {
        "formats": {"ifsc": "ifsc"},
        "expressions": [
            {"name": "amount_nonzero", "expr": "amount != 0", "severity": "warning"},
        ],
    },
}


def list_rulesets() -> list[str]:
    """Built-in ruleset names plus any saved in the workspace."""
    from excellia.core import store

    return sorted(set(RULESETS) | set(store.list_names("rulesets")))


def resolve_ruleset(ruleset: str | dict) -> dict:
    """A ruleset spec from a name (built-in, then workspace) or a literal dict."""
    if isinstance(ruleset, dict):
        return ruleset
    if ruleset in RULESETS:
        return RULESETS[ruleset]
    from excellia.core import store

    try:
        return store.load("rulesets", ruleset)
    except store.StoreError:
        raise ValueError(
            f"Unknown ruleset '{ruleset}'. Available: {', '.join(list_rulesets())}. "
            "Save a custom one with save_ruleset / POST /rulesets/<name>."
        )


def _excel_row(df: pd.DataFrame, idx_label) -> int:
    return df.index.get_loc(idx_label) + 2


def _type_category(val) -> str | None:
    if pd.isnull(val):
        return None
    if isinstance(val, bool):
        return "bool"
    if isinstance(val, Number):
        return "number"
    if isinstance(val, pd.Timestamp):
        return "datetime"
    if isinstance(val, str):
        return "string"
    return "other"


def _explicit_checks(df: pd.DataFrame, spec: dict) -> list[Issue]:
    issues: list[Issue] = []

    for col in spec.get("required", []):
        if col not in df.columns:
            issues.append(Issue(1, col, "required_column", "error",
                                f"Required column '{col}' is missing from the file"))
            continue
        present = nonempty(df[col])
        for idx in df.index.difference(present.index):
            issues.append(Issue(_excel_row(df, idx), col, "required_field", "error",
                                f"Required field '{col}' is empty"))

    for col, fmt in spec.get("formats", {}).items():
        if col not in df.columns:
            continue
        pattern = FORMATS[fmt]
        for idx, val in nonempty(df[col]).items():
            if not pattern.fullmatch(str(val).strip()):
                issues.append(Issue(_excel_row(df, idx), col, f"format_{fmt}", "error",
                                    f"Value does not match the {fmt.upper()} format", val))

    for col, bounds in spec.get("ranges", {}).items():
        if col not in df.columns:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        lo, hi = bounds.get("min"), bounds.get("max")
        for idx, val in numeric.dropna().items():
            if (lo is not None and val < lo) or (hi is not None and val > hi):
                issues.append(Issue(_excel_row(df, idx), col, "range", "error",
                                    f"Value {val} is outside the allowed range [{lo}, {hi}]",
                                    df.at[idx, col]))

    for col in spec.get("unique", []):
        if col not in df.columns:
            continue
        values = nonempty(df[col]).astype(str).str.strip()
        dup_mask = values.duplicated(keep=False)
        for idx, val in values[dup_mask].items():
            issues.append(Issue(_excel_row(df, idx), col, "unique", "error",
                                f"Duplicate value in column '{col}' that must be unique", val))

    for col, allowed in spec.get("references", {}).items():
        if col not in df.columns:
            continue
        allowed_set = {str(a).strip().lower() for a in allowed}
        for idx, val in nonempty(df[col]).items():
            if str(val).strip().lower() not in allowed_set:
                issues.append(Issue(_excel_row(df, idx), col, "reference", "error",
                                    f"Value not found in the allowed list for '{col}'", val))

    for rule in spec.get("expressions", []):
        name, expr = rule["name"], rule["expr"]
        severity = rule.get("severity", "error")
        try:
            ok = df.eval(expr)
        except Exception as e:
            issues.append(Issue(1, "*", name, "warning",
                                f"Could not evaluate rule expression '{expr}': {e}"))
            continue
        for idx in df.index[~ok.fillna(True)]:
            issues.append(Issue(_excel_row(df, idx), "*", name, severity,
                                f"Row fails rule '{name}' ({expr})"))

    return issues


def _auto_checks(df: pd.DataFrame) -> list[Issue]:
    """Inferred checks lifted from the GUI: missing values, dominant-format
    violations, duplicate rows, duplicate IDs, and mixed types."""
    issues: list[Issue] = []

    for col in df.columns:
        series = df[col]
        values = nonempty(series)
        fill_rate = len(values) / len(series) if len(series) else 0.0

        # Missing values in mostly-populated columns
        if 0.5 <= fill_rate < 1.0:
            for idx in df.index.difference(values.index):
                issues.append(Issue(_excel_row(df, idx), col, "missing_value", "warning",
                                    f"Empty cell in mostly-populated column '{col}'"))

        if values.empty:
            continue

        # Dominant built-in format: flag the minority that breaks it,
        # and flag duplicates when the format is an identifier
        stripped = values.astype(str).str.strip()
        for fmt, pattern in FORMATS.items():
            match_mask = stripped.apply(lambda v: bool(pattern.fullmatch(v)))
            if match_mask.mean() < 0.8:
                continue
            for idx, val in stripped[~match_mask].items():
                issues.append(Issue(
                    _excel_row(df, idx), col, f"format_{fmt}", "error",
                    f"Column '{col}' is mostly {fmt.upper()} values but this one is not",
                    val))
            if fmt in ("gst", "pan", "aadhaar", "ifsc"):
                ids = stripped[match_mask]
                for idx, val in ids[ids.duplicated(keep=False)].items():
                    issues.append(Issue(_excel_row(df, idx), col, "duplicate_id", "warning",
                                        f"{fmt.upper()} value appears more than once", val))
            break

        # Mixed types within a column
        cats = values.map(_type_category)
        if cats.nunique() > 1:
            primary = cats.mode().iat[0]
            for idx in cats.index[cats != primary]:
                issues.append(Issue(_excel_row(df, idx), col, "mixed_types", "warning",
                                    f"Column '{col}' is mostly {primary} but this cell is "
                                    f"{cats.at[idx]}", df.at[idx, col]))

    # Exact duplicate rows
    dup_mask = df.duplicated(keep=False)
    if dup_mask.any():
        for idx in df.index[dup_mask]:
            issues.append(Issue(_excel_row(df, idx), "*", "duplicate_row", "warning",
                                "Entire row is an exact duplicate of another row"))

    return issues


def validate(df: pd.DataFrame, ruleset: str | dict = "default") -> list[Issue]:
    """Check a DataFrame against a ruleset (a name or a literal spec dict).

    Runs the ruleset's explicit rules plus (unless the ruleset sets
    ``auto: False``) inferred checks: missing values, dominant-format
    violations, duplicate rows/IDs, and mixed types. Every Issue
    carries row, column, rule_name, severity, and a reason.
    """
    spec = resolve_ruleset(ruleset)

    issues = _explicit_checks(df, spec)
    if spec.get("auto", True):
        issues.extend(_auto_checks(df))

    issues.sort(key=lambda i: (i.row, i.column))
    return issues


# --- big files: streaming validation ---------------------------------

def validate_large(
    file_path: str,
    ruleset: str | dict = "default",
    sheet: str | None = None,
    chunk_size: int | None = None,
) -> list[Issue]:
    """Streaming ``validate`` for files too big to hold in memory.

    Full fidelity for the explicit rules (uniqueness tracked across
    chunks). The inferred checks run a streaming subset: dominant-format
    violations (format decided from each column's first well-populated
    chunk), duplicate IDs, and exact duplicate rows — cross-chunk, via
    value/row maps. Mixed-type and missing-value inference need global
    statistics, so they only run on the in-memory path.
    """
    from excellia.core import ingest

    spec = resolve_ruleset(ruleset)
    chunk_size = chunk_size or ingest.DEFAULT_CHUNK_SIZE
    per_chunk_spec = {k: v for k, v in spec.items() if k != "unique"}

    issues: list[Issue] = []
    # value -> first Excel row; None once the duplicate was already reported
    seen_unique: dict[str, dict[str, int | None]] = {c: {} for c in spec.get("unique", [])}
    seen_ids: dict[str, dict[str, int | None]] = {}
    seen_rows: dict[int, int | None] = {}
    fmt_decisions: dict[str, str | None] = {}  # column -> dominant format (None = no dominant)
    offset = 0  # rows before the current chunk

    def _dup_check(book: dict[str, int | None], value: str, row: int, col: str,
                   rule: str, severity: str, reason: str) -> None:
        first = book.get(value, -1)
        if first == -1:
            book[value] = row
            return
        if first is not None:  # second sighting — report the first row too
            issues.append(Issue(first, col, rule, severity, reason, value))
            book[value] = None
        issues.append(Issue(row, col, rule, severity, reason, value))

    for chunk in ingest.iter_chunks(file_path, sheet=sheet, chunk_size=chunk_size):
        chunk = chunk.reset_index(drop=True)
        for issue in _explicit_checks(chunk, per_chunk_spec):
            issue.row += offset
            issues.append(issue)

        for col in spec.get("unique", []):
            if col not in chunk.columns:
                continue
            for idx, val in nonempty(chunk[col]).astype(str).str.strip().items():
                _dup_check(seen_unique[col], val, idx + offset + 2, col, "unique",
                           "error", f"Duplicate value in column '{col}' that must be unique")

        if spec.get("auto", True):
            for col in chunk.columns:
                stripped = nonempty(chunk[col]).astype(str).str.strip()
                if col not in fmt_decisions:
                    if len(stripped) < 20:
                        continue  # wait for a better-populated chunk
                    fmt_decisions[col] = next(
                        (f for f, p in FORMATS.items()
                         if stripped.apply(lambda v: bool(p.fullmatch(v))).mean() >= 0.8),
                        None,
                    )
                fmt = fmt_decisions[col]
                if fmt is None:
                    continue
                pattern = FORMATS[fmt]
                match_mask = stripped.apply(lambda v: bool(pattern.fullmatch(v)))
                for idx, val in stripped[~match_mask].items():
                    issues.append(Issue(
                        idx + offset + 2, col, f"format_{fmt}", "error",
                        f"Column '{col}' is mostly {fmt.upper()} values but this one is not",
                        val))
                if fmt in ("gst", "pan", "aadhaar", "ifsc"):
                    book = seen_ids.setdefault(col, {})
                    for idx, val in stripped[match_mask].items():
                        _dup_check(book, val, idx + offset + 2, col, "duplicate_id",
                                   "warning", f"{fmt.upper()} value appears more than once")

            for idx, row_hash in enumerate(pd.util.hash_pandas_object(chunk, index=False)):
                first = seen_rows.get(row_hash, -1)
                if first == -1:
                    seen_rows[row_hash] = idx + offset + 2
                    continue
                if first is not None:
                    issues.append(Issue(first, "*", "duplicate_row", "warning",
                                        "Entire row is an exact duplicate of another row"))
                    seen_rows[row_hash] = None
                issues.append(Issue(idx + offset + 2, "*", "duplicate_row", "warning",
                                    "Entire row is an exact duplicate of another row"))

        offset += len(chunk)

    issues.sort(key=lambda i: (i.row, i.column))
    return issues
