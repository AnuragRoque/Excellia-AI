"""End-to-end tests for the four core pillars against the demo file.

Row convention: Issue.row / Flag.row are Excel row numbers, so a
DataFrame position ``i`` maps to row ``i + 2`` (header is row 1).
"""

import os

import pandas as pd
import pytest

from excellia.core import anomaly, ingest, reconcile, validate

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")
MESSY = os.path.join(EXAMPLES, "messy_vendors.xlsx")


@pytest.fixture(scope="module")
def df():
    return ingest.load(MESSY)


@pytest.fixture(scope="module")
def issues(df):
    return validate.validate(df)


@pytest.fixture(scope="module")
def flags(df):
    return anomaly.detect_anomalies(df)


# --- ingest -----------------------------------------------------------

def test_load_shape(df):
    assert df.shape == (50, 9)
    assert "gstin" in df.columns


def test_load_missing_file():
    with pytest.raises(FileNotFoundError):
        ingest.load(os.path.join(EXAMPLES, "nope.xlsx"))


def test_load_unsupported_extension(tmp_path):
    bad = tmp_path / "data.json"
    bad.write_text("{}")
    with pytest.raises(ingest.IngestError):
        ingest.load(str(bad))


def test_load_csv_roundtrip(df, tmp_path):
    path = tmp_path / "vendors.csv"
    df.to_csv(path, index=False)
    loaded = ingest.load(str(path))
    assert loaded.shape == df.shape


def test_profile_basics():
    prof = ingest.profile(MESSY)
    assert prof.row_count == 50
    assert prof.column_count == 9
    by_name = {c.name: c for c in prof.columns}
    assert by_name["gstin"].detected_format == "gst"
    assert by_name["pan"].detected_format == "pan"
    assert by_name["email"].detected_format == "email"
    assert by_name["gstin"].inferred_type == "id"
    assert by_name["amount"].inferred_type == "number"
    assert by_name["invoice_date"].inferred_type == "date"
    assert by_name["city"].inferred_type == "categorical"
    assert by_name["email"].null_rate == pytest.approx(1 / 50)
    assert by_name["amount"].max == pytest.approx(9_750_000.0)
    assert prof.to_dict()["columns"][0]["name"] == "vendor_id"


# --- validate ---------------------------------------------------------

def _rows(issues, rule_prefix):
    return sorted(i.row for i in issues if i.rule_name.startswith(rule_prefix))


def test_validate_finds_bad_gstins(issues):
    # planted at positions 3, 11, 19 -> Excel rows 5, 13, 21
    assert _rows(issues, "format_gst") == [5, 13, 21]


def test_validate_finds_bad_pans(issues):
    assert _rows(issues, "format_pan") == [9, 25]


def test_validate_finds_bad_emails_and_phone(issues):
    assert _rows(issues, "format_email") == [7, 16]
    assert _rows(issues, "format_phone") == [29]


def test_validate_finds_duplicate_pan(issues):
    # planted pair (4, 37) plus the duplicate/near-duplicate rows,
    # which necessarily repeat their PANs too (14/47 and 22/48)
    pan_dups = sorted(i.row for i in issues
                      if i.rule_name == "duplicate_id" and i.column == "pan")
    assert pan_dups == [4, 14, 22, 37, 47, 48]


def test_validate_finds_duplicate_rows(issues):
    assert _rows(issues, "duplicate_row") == [14, 47]


def test_validate_finds_missing_values(issues):
    assert set(_rows(issues, "missing_value")) == {11, 33, 42}


def test_every_issue_is_explained(issues):
    assert issues, "the messy file must produce issues"
    for issue in issues:
        assert issue.reason and issue.severity in ("error", "warning", "info")
        assert issue.row >= 2 or issue.column == "*"


def test_unknown_ruleset_is_instructive(df):
    with pytest.raises(ValueError, match="default"):
        validate.validate(df, ruleset="does-not-exist")


def test_explicit_ruleset(df):
    validate.RULESETS["_test"] = {
        "auto": False,
        "required": ["vendor_id", "not_a_column"],
        "ranges": {"amount": {"min": 0, "max": 100_000}},
        "unique": ["pan"],
    }
    try:
        found = validate.validate(df, ruleset="_test")
    finally:
        del validate.RULESETS["_test"]
    rules = {i.rule_name for i in found}
    assert "required_column" in rules          # not_a_column is absent
    assert "range" in rules                    # the 9.75M outlier
    assert "unique" in rules                   # duplicated PAN


# --- anomaly ----------------------------------------------------------

def test_amount_outlier_is_flagged(flags):
    amount_flags = [f for f in flags if f.row == 19 and "amount" in f.columns]
    assert amount_flags, "the 9.75M amount at row 19 must be flagged"


def test_near_duplicate_pair_is_found(flags):
    near = [f for f in flags if f.kind == "near_duplicate"]
    assert any(f.row == 22 and "row 48" in f.reason for f in near)


def test_pattern_break_in_vendor_id(flags):
    breaks = [f for f in flags if f.kind == "pattern_break" and "vendor_id" in f.columns]
    assert [f.row for f in breaks] == [31]     # VENDOR_30 at position 29


def test_rare_category_city(flags):
    rare = [f for f in flags if f.kind == "rare_category" and "city" in f.columns]
    assert any("Ranchi" in f.reason for f in rare)


def test_every_flag_is_explained(flags):
    for flag in flags:
        assert flag.reason
        assert 0.0 <= flag.confidence <= 1.0


def test_sensitivity_bounds(df):
    with pytest.raises(ValueError):
        anomaly.detect_anomalies(df, sensitivity=0.7)


# --- reconcile --------------------------------------------------------

@pytest.fixture()
def ledgers():
    a = pd.DataFrame({
        "invoice": ["INV-1", "INV-2", "INV-3", "INV-4"],
        "vendor": ["Sharma Traders", "Patel Exports", "Iyer Solutions", "Khan Industries"],
        "amount": [1000.00, 250.50, 78.25, 400.00],
        "date": ["2026-01-10", "2026-01-11", "2026-01-12", "2026-01-13"],
    })
    b = pd.DataFrame({
        "invoice": ["inv-1 ", "INV-2", "INV-3", "INV-5"],
        "vendor": ["Sharma Traders", "Patel Exports", "Iyer Solutionz", "Gupta Enterprises"],
        "amount": [1000.00, 250.51, 78.25, 900.00],
        "date": ["2026-01-10", "2026-01-12", "2026-01-12", "2026-01-14"],
    })
    return a, b


def test_reconcile_exact(ledgers):
    a, b = ledgers
    result = reconcile.reconcile(a, b, keys=["invoice"])
    assert result.summary() == {
        "matched": 1,          # INV-1 (keys match case/space-insensitively)
        "only_in_a": 1,        # INV-4
        "only_in_b": 1,        # INV-5
        "discrepancies": 2,    # INV-2 (amount+date), INV-3 (vendor typo)
    }
    diff_cols = {tuple(d["differences"]) for d in result.discrepancies}
    assert ("amount", "date") in diff_cols or ("date", "amount") in diff_cols


def test_reconcile_with_tolerance(ledgers):
    a, b = ledgers
    result = reconcile.reconcile(
        a, b, keys=["invoice"],
        tolerance={"numeric": 0.05, "days": 1, "fuzzy": 0.85},
    )
    # amount ±0.05, date ±1 day, and the vendor typo all forgiven
    assert result.summary()["matched"] == 3
    assert result.summary()["discrepancies"] == 0


def test_reconcile_missing_key_is_instructive(ledgers):
    a, b = ledgers
    with pytest.raises(ValueError, match="not found"):
        reconcile.reconcile(a, b, keys=["order_id"])


def test_reconcile_one_to_many():
    a = pd.DataFrame({"k": ["x", "x"], "v": [1, 2]})
    b = pd.DataFrame({"k": ["x"], "v": [1]})
    result = reconcile.reconcile(a, b, keys=["k"])
    assert result.summary() == {
        "matched": 1, "only_in_a": 0, "only_in_b": 0, "discrepancies": 1,
    }
