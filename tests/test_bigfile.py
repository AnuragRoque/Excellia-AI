"""Big-file path: chunked iteration, streaming profile and validate.

The 500K-row memory-budget test is opt-in (slow): EXCELLIA_BIG=1 pytest.
"""

import os

import pandas as pd
import pytest

from excellia.core import ingest, validate

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")
MESSY = os.path.join(EXAMPLES, "messy_vendors.xlsx")


@pytest.fixture()
def csv_file(tmp_path):
    df = pd.DataFrame({
        "pan": [f"ABCDE{i:04d}F" for i in range(200)],
        "amount": [100 + i for i in range(200)],
    })
    df.loc[5, "pan"] = "not-a-pan"          # format break
    df.loc[7, "pan"] = df.loc[3, "pan"]     # duplicate id
    path = tmp_path / "big.csv"
    df.to_csv(path, index=False)
    return str(path)


def test_iter_chunks_csv(csv_file):
    chunks = list(ingest.iter_chunks(csv_file, chunk_size=60))
    assert [len(c) for c in chunks] == [60, 60, 60, 20]
    assert all(list(c.columns) == ["pan", "amount"] for c in chunks)


def test_iter_chunks_xlsx():
    chunks = list(ingest.iter_chunks(MESSY, chunk_size=20))
    assert sum(len(c) for c in chunks) == 50
    assert len(chunks) == 3
    whole = ingest.load(MESSY)
    assert list(chunks[0].columns) == list(whole.columns)


def test_iter_chunks_missing_and_unsupported(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(ingest.iter_chunks(str(tmp_path / "nope.csv")))
    bad = tmp_path / "x.json"
    bad.write_text("{}")
    with pytest.raises(ingest.IngestError):
        list(ingest.iter_chunks(str(bad)))


def test_profile_large_matches_profile_on_demo():
    exact = ingest.profile(MESSY)
    streamed = ingest.profile_large(MESSY, chunk_size=15)
    assert streamed.row_count == exact.row_count
    assert streamed.column_count == exact.column_count
    assert [c.name for c in streamed.columns] == [c.name for c in exact.columns]
    exact_by_name = {c.name: c for c in exact.columns}
    for col in streamed.columns:
        ref = exact_by_name[col.name]
        assert col.null_rate == ref.null_rate, col.name
        assert col.cardinality == ref.cardinality, col.name
        assert col.detected_format == ref.detected_format, col.name


def test_validate_large_finds_cross_chunk_issues(csv_file):
    issues = validate.validate_large(csv_file, chunk_size=50)
    rules = {i.rule_name for i in issues}
    assert "format_pan" in rules
    dup_rows = sorted(i.row for i in issues if i.rule_name == "duplicate_id")
    # pandas positions 3 and 7 -> Excel rows 5 and 9; both sides reported
    assert dup_rows == [5, 9]
    bad_format = [i for i in issues if i.rule_name == "format_pan"]
    assert [i.row for i in bad_format] == [7]  # position 5 -> Excel row 7


def test_validate_large_explicit_unique_across_chunks(tmp_path):
    df = pd.DataFrame({"pan": ["AAAAA1111A"] * 3 + ["BBBBB2222B"] * 97})
    path = tmp_path / "u.csv"
    df.to_csv(path, index=False)
    issues = validate.validate_large(
        str(path), ruleset={"unique": ["pan"], "auto": False}, chunk_size=2)
    rows = sorted(i.row for i in issues if i.rule_name == "unique")
    assert rows[:3] == [2, 3, 4]


def test_validate_large_duplicate_rows_across_chunks(tmp_path):
    df = pd.DataFrame({"a": ["x", "y", "z", "x"], "b": [1, 2, 3, 1]})
    path = tmp_path / "d.csv"
    df.to_csv(path, index=False)
    issues = validate.validate_large(str(path), chunk_size=2)
    rows = sorted(i.row for i in issues if i.rule_name == "duplicate_row")
    assert rows == [2, 5]  # both copies, found in different chunks


@pytest.mark.skipif(not os.environ.get("EXCELLIA_BIG"),
                    reason="slow 500K-row memory test; set EXCELLIA_BIG=1 to run")
def test_500k_rows_within_memory_budget(tmp_path):
    import tracemalloc

    n = 500_000
    path = tmp_path / "huge.csv"
    with open(path, "w", encoding="utf-8") as f:
        f.write("id,vendor,amount\n")
        for i in range(n):
            f.write(f"V{i:06d},vendor {i % 997},{(i * 37) % 100000}\n")

    tracemalloc.start()
    prof = ingest.profile_large(str(path))
    issues = validate.validate_large(str(path), ruleset={"unique": ["id"], "auto": False})
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert prof.row_count == n
    assert issues == []
    # Python-heap budget well under the ~1.5 GB RSS gate
    assert peak < 1_000 * 1024 * 1024, f"peak heap {peak / 1e6:.0f} MB"
