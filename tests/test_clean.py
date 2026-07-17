"""clean.py: every recipe atom is deterministic and instructive on misuse."""

import pandas as pd
import pytest

from excellia.core import clean


@pytest.fixture()
def df():
    return pd.DataFrame({
        "name": ["  ram   kumar ", "SITA DEVI", None],
        "amount": ["₹1,200.50", "$300", "bad"],
        "address": ["12 MG Road | Pune | 411001", "5 Park St | Kolkata | 700016", None],
        "dept": ["sales", "sales", "hr"],
        "when": ["01/02/2024", "2024-03-15", None],
    })


def test_trim_collapses_whitespace(df):
    out = clean.trim(df, columns=["name"])
    assert out["name"][0] == "ram kumar"
    assert df["name"][0] == "  ram   kumar "  # input untouched


def test_case_variants(df):
    assert clean.case(df, "name", to="title")["name"][0] == "  Ram   Kumar "
    assert clean.case(df, "name", to="sentence")["name"][1] == "Sita devi"
    with pytest.raises(clean.CleanError, match="upper, lower, title, sentence"):
        clean.case(df, "name", to="shouty")


def test_replace_and_remove(df):
    out = clean.replace_text(df, "dept", find="hr", replace="people")
    assert out["dept"][2] == "people"
    out = clean.remove_chars(df, "amount", chars="₹$,")
    assert out["amount"][0] == "1200.50"


def test_split_column(df):
    out = clean.split_column(df, "address", delimiter="|", into=["street", "city", "pin"])
    assert out.loc[0, "city"] == "Pune"
    assert out.loc[0, "pin"] == "411001"
    assert pd.isna(out.loc[2, "city"])


def test_concat_columns(df):
    out = clean.concat_columns(df, ["dept", "name"], into="tag", separator=":")
    assert out["tag"][1] == "sales:SITA DEVI"


def test_math_and_absolute():
    df = pd.DataFrame({"a": [1, 2], "b": [10, -20]})
    assert clean.math(df, into="c", left="b", op="/", right="a")["c"].tolist() == [10.0, -10.0]
    assert clean.absolute(df, "b")["b"].tolist() == [10, 20]
    with pytest.raises(clean.CleanError):
        clean.math(df, into="c", left="a", op="%", right="b")


def test_strip_currency(df):
    out = clean.strip_currency(df, "amount")
    assert out["amount"][0] == 1200.50
    assert out["amount"][1] == 300.0
    assert pd.isna(out["amount"][2])


def test_parse_date_mixed(df):
    out = clean.parse_date(df, "when")
    assert out["when"][0] == "2024-02-01"  # dayfirst
    assert out["when"][1] == "2024-03-15"


def test_structure_ops():
    df = pd.DataFrame({"a": [None, "x", None], "b": [None, "y", None]})
    assert len(clean.drop_empty_rows(df)) == 1
    df2 = pd.DataFrame({"a": ["1"], "empty": [None]})
    assert list(clean.drop_empty_columns(df2).columns) == ["a"]


def test_set_header():
    df = pd.DataFrame({"c1": ["junk", "name", "ram"], "c2": ["junk", "amt", "5"]})
    out = clean.set_header(df, row=3)  # Excel row 3 = second data row
    assert list(out.columns) == ["name", "amt"]
    assert out.iloc[0].tolist() == ["ram", "5"]
    with pytest.raises(clean.CleanError, match="rows 2"):
        clean.set_header(df, row=99)


def test_fill_down():
    df = pd.DataFrame({"grp": ["A", None, "", "B", None]})
    assert clean.fill_down(df, "grp")["grp"].tolist() == ["A", "A", "A", "B", "B"]


def test_dedupe_keep_and_aggregate():
    df = pd.DataFrame({"id": ["1", "1", "2"], "amt": [10, 5, 7], "note": ["a", "b", "c"]})
    assert len(clean.dedupe(df, columns=["id"], keep="first")) == 2
    agg = clean.dedupe(df, columns=["id"], aggregate={"amt": "sum"})
    assert agg.set_index("id").loc["1", "amt"] == 15
    assert agg.set_index("id").loc["1", "note"] == "a"  # unlisted cols keep first
    with pytest.raises(clean.CleanError, match="Unknown aggregate"):
        clean.dedupe(df, columns=["id"], aggregate={"amt": "median"})


def test_slice_text():
    df = pd.DataFrame({"code": ["AB1234", "XY9876"]})
    assert clean.slice_text(df, "code", side="left", length=2)["code"].tolist() == ["AB", "XY"]
    assert clean.slice_text(df, "code", side="right", length=4)["code"].tolist() == ["1234", "9876"]
    assert clean.slice_text(df, "code", side="mid", start=3, length=2)["code"].tolist() == ["12", "98"]


def test_apply_ops_pipeline(df):
    steps = [
        {"op": "trim", "params": {"columns": ["name"]}},
        {"op": "case", "params": {"columns": "name", "to": "title"}},
        {"op": "strip_currency", "params": {"columns": "amount"}},
    ]
    out = clean.apply_ops(df, steps)
    assert out["name"][0] == "Ram Kumar"
    assert out["amount"][0] == 1200.50


def test_apply_ops_unknown_op_lists_available(df):
    with pytest.raises(clean.CleanError) as e:
        clean.apply_ops(df, [{"op": "sparkle"}])
    assert "Step 1" in str(e.value) and "trim" in str(e.value)


def test_apply_ops_bad_params_name_the_step(df):
    with pytest.raises(clean.CleanError, match=r"Step 1 \(case\)"):
        clean.apply_ops(df, [{"op": "case", "params": {"columns": "name", "wat": 1}}])


def test_missing_column_lists_actual(df):
    with pytest.raises(clean.CleanError) as e:
        clean.trim(df, columns=["nope"])
    assert "Actual columns" in str(e.value) and "name" in str(e.value)


def test_list_ops_covers_registry():
    ops = clean.list_ops()
    assert set(ops) == set(clean.OPS)
    assert all(desc for desc in ops.values())
