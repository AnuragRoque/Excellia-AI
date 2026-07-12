"""Ingest & profiling: load a spreadsheet and describe its shape.

Lifted from the old Excellia GUI's ``load_dataframe`` (routes.py) and
generalised: no Flask, no session state, no print-based logging.
"""

from __future__ import annotations

import os

import pandas as pd

from excellia.core.models import ColumnProfile, Profile
from excellia.core.rules.builtin import FORMATS

SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm", ".xls", ".csv", ".tsv")

_CSV_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")
_CSV_DELIMITERS = (",", ";", "\t", "|")

# Values treated as empty besides real NaN (mirrors the GUI's is_empty_value)
_EMPTY_STRINGS = {"", "nan", "null", "none", "n/a", "na"}


class IngestError(ValueError):
    """Raised when a file cannot be loaded as tabular data."""


def _read_csv(file_path: str, delimiter: str | None) -> pd.DataFrame | None:
    """One robust CSV read attempt per encoding; None if all fail."""
    for encoding in _CSV_ENCODINGS:
        try:
            df = pd.read_csv(
                file_path,
                encoding=encoding,
                sep=delimiter,
                engine="python",
                on_bad_lines="skip",
            )
        except Exception:
            continue
        # Reject fake parses: a single wide column whose name still
        # contains a delimiter means we picked the wrong separator.
        if df.shape[1] > 1 or (
            df.shape[1] == 1
            and not any(d in str(df.columns[0]) for d in _CSV_DELIMITERS)
        ):
            return df
    return None


def load(file_path: str, sheet: str | None = None) -> pd.DataFrame:
    """Load a spreadsheet into a DataFrame.

    Auto-detects delimiter and encoding for CSV/TSV. Raises
    FileNotFoundError for missing files and IngestError for
    unsupported or unparseable files.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise IngestError(
            f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    if ext in (".xlsx", ".xlsm", ".xls"):
        engine = "xlrd" if ext == ".xls" else "openpyxl"
        df = pd.read_excel(file_path, sheet_name=sheet or 0, engine=engine)
    elif ext == ".tsv":
        df = _read_csv(file_path, "\t")
    else:  # .csv — sniff first, then try explicit delimiters
        df = _read_csv(file_path, None)
        if df is None or df.empty:
            for delimiter in _CSV_DELIMITERS:
                df = _read_csv(file_path, delimiter)
                if df is not None and not df.empty:
                    break

    if df is None or df.empty:
        raise IngestError(f"Could not parse any tabular data from {file_path}")

    df.columns = [str(c) for c in df.columns]
    return df


def nonempty(series: pd.Series) -> pd.Series:
    """Values that are neither NaN nor an empty-like string."""
    s = series.dropna()
    if s.empty:
        return s
    mask = ~s.astype(str).str.strip().str.lower().isin(_EMPTY_STRINGS)
    return s[mask]


def _detect_format(values: pd.Series) -> str | None:
    """Name of the built-in format that >=90% of values match, if any."""
    sample = values.astype(str).str.strip().head(500)
    if sample.empty:
        return None
    for name, pattern in FORMATS.items():
        hits = sample.apply(lambda v: bool(pattern.fullmatch(v))).mean()
        if hits >= 0.9:
            return name
    return None


def _infer_type(
    series: pd.Series, values: pd.Series, detected_format: str | None
) -> str:
    if detected_format in ("gst", "pan", "aadhaar", "ifsc"):
        return "id"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if values.empty:
        return "text"

    sample = values.astype(str).str.strip().head(500)
    # currency: numbers wearing a symbol
    if sample.str.match(r"^[₹$€£]\s*-?[\d,]+(\.\d+)?$").mean() >= 0.8:
        return "currency"
    if pd.to_numeric(sample.str.replace(",", ""), errors="coerce").notna().mean() >= 0.9:
        return "number"
    try:
        if pd.to_datetime(sample, errors="coerce", format="mixed").notna().mean() >= 0.9:
            return "date"
    except (ValueError, TypeError):
        pass

    unique_ratio = values.nunique() / len(values)
    if unique_ratio > 0.95 and len(values) > 10:
        return "id"
    if values.nunique() <= max(20, int(0.05 * len(values))):
        return "categorical"
    return "text"


def profile(file_path: str, sheet: str | None = None) -> Profile:
    """Profile a spreadsheet: row/col counts, per-column type inference,
    null rates, cardinality, min/max/mean, top values, detected formats."""
    df = load(file_path, sheet=sheet)
    columns: list[ColumnProfile] = []

    for col in df.columns:
        series = df[col]
        values = nonempty(series)
        null_rate = 1.0 - (len(values) / len(series)) if len(series) else 0.0
        detected_format = _detect_format(values) if not values.empty else None
        inferred = _infer_type(series, values, detected_format)

        col_min = col_max = None
        col_mean = None
        numeric = pd.to_numeric(values, errors="coerce").dropna()
        if not numeric.empty:
            col_min, col_max = numeric.min().item(), numeric.max().item()
            col_mean = round(float(numeric.mean()), 4)
        elif not values.empty:
            try:
                col_min, col_max = str(values.min()), str(values.max())
            except TypeError:
                pass  # mixed types that won't order

        top = values.astype(str).value_counts().head(5).index.tolist()
        columns.append(
            ColumnProfile(
                name=col,
                inferred_type=inferred,
                null_rate=round(null_rate, 4),
                cardinality=int(values.nunique()),
                min=col_min,
                max=col_max,
                mean=col_mean,
                top_values=top,
                detected_format=detected_format,
            )
        )

    return Profile(
        file=file_path,
        sheet=sheet,
        row_count=len(df),
        column_count=len(df.columns),
        columns=columns,
    )
