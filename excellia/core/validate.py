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
}


def list_rulesets() -> list[str]:
    """Names of saved, reusable rulesets."""
    return sorted(RULESETS)


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


def validate(df: pd.DataFrame, ruleset: str = "default") -> list[Issue]:
    """Check a DataFrame against a named ruleset.

    Runs the ruleset's explicit rules plus (unless the ruleset sets
    ``auto: False``) inferred checks: missing values, dominant-format
    violations, duplicate rows/IDs, and mixed types. Every Issue
    carries row, column, rule_name, severity, and a reason.
    """
    if ruleset not in RULESETS:
        raise ValueError(
            f"Unknown ruleset '{ruleset}'. Available: {', '.join(list_rulesets())}")
    spec = RULESETS[ruleset]

    issues = _explicit_checks(df, spec)
    if spec.get("auto", True):
        issues.extend(_auto_checks(df))

    issues.sort(key=lambda i: (i.row, i.column))
    return issues
