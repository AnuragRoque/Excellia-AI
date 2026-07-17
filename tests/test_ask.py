"""ask.py: the plan whitelist cannot be escaped, and answers carry evidence."""

import json

import pandas as pd
import pytest

from excellia.core import ask
from excellia.core.llm import Ollama
from tests.conftest import FakeOllama


@pytest.fixture()
def df():
    return pd.DataFrame({
        "vendor": ["Acme", "Acme", "Zen Corp", "Zen Corp", "Iota"],
        "amount": [100, 200, 50, 150, 999],
        "state": ["MH", "MH", "KA", None, "MH"],
    })


# --- executor ---------------------------------------------------------

def test_filter_group_aggregate_sort(df):
    plan = {
        "filters": [{"column": "state", "op": "eq", "value": "MH"}],
        "group_by": ["vendor"],
        "aggregates": [{"column": "amount", "fn": "sum", "as": "total"}],
        "sort": [{"by": "total", "desc": True}],
    }
    out = ask.execute_plan(df, plan)
    assert out.iloc[0]["vendor"] == "Iota" and out.iloc[0]["total"] == 999
    assert out.iloc[1]["total"] == 300


def test_aggregate_without_groupby(df):
    out = ask.execute_plan(df, {"aggregates": [{"column": "amount", "fn": "mean"}]})
    assert out.iloc[0]["mean_amount"] == pytest.approx(299.8)


def test_groupby_without_aggregates_counts(df):
    out = ask.execute_plan(df, {"group_by": ["vendor"]})
    assert set(out.columns) == {"vendor", "count"}
    assert out["count"].sum() == 5


def test_filters_contains_in_isnull(df):
    assert len(ask.execute_plan(df, {"filters": [
        {"column": "vendor", "op": "contains", "value": "corp"}]})) == 2
    assert len(ask.execute_plan(df, {"filters": [
        {"column": "vendor", "op": "in", "value": ["acme", "iota"]}]})) == 3
    assert len(ask.execute_plan(df, {"filters": [
        {"column": "state", "op": "isnull"}]})) == 1


def test_numeric_comparison_coerces(df):
    out = ask.execute_plan(df, {"filters": [
        {"column": "amount", "op": "gt", "value": "150"}]})
    assert len(out) == 2


def test_limit_bounds(df):
    assert len(ask.execute_plan(df, {"limit": 2})) == 2
    assert len(ask.execute_plan(df, {"limit": 999999})) == 5  # bad limit -> default 50


@pytest.mark.parametrize("plan,fragment", [
    ({"filters": [{"column": "evil", "op": "eq", "value": 1}]}, "unknown column"),
    ({"filters": [{"column": "amount", "op": "regex", "value": ".*"}]}, "not allowed"),
    ({"aggregates": [{"column": "amount", "fn": "eval"}]}, "not allowed"),
    ({"exec": "os.system"}, "Unknown plan keys"),
    ({"sort": [{"by": "__import__"}]}, "not in the result"),
])
def test_whitelist_cannot_be_escaped(df, plan, fragment):
    with pytest.raises(ask.PlanError) as e:
        ask.execute_plan(df, plan)
    assert fragment.lower() in str(e.value).lower()


def test_adversarial_filter_values_are_data_not_code(df):
    # hostile strings must be treated as literal values, never evaluated
    for evil in ["__import__('os').system('rm -rf /')", "amount > 0; DROP TABLE",
                 "@df.attrs", "`rm`"]:
        out = ask.execute_plan(df, {"filters": [
            {"column": "vendor", "op": "eq", "value": evil}]})
        assert len(out) == 0  # just a string nobody matches


# --- full ask() with a scripted model --------------------------------

def test_ask_computes_and_narrates(df):
    plan_reply = json.dumps({"plan": {
        "group_by": ["vendor"],
        "aggregates": [{"column": "amount", "fn": "sum", "as": "total"}],
        "sort": [{"by": "total", "desc": True}],
    }})
    narration = json.dumps({"answer": "Iota leads with 999, then Zen Corp at 200."})
    llm = Ollama(model="fake", transport=FakeOllama([plan_reply, narration]))
    result = ask.ask(df, "total amount by vendor?", llm=llm)
    assert result["refused"] is False
    assert result["answer"].startswith("Iota")
    totals = {r["vendor"]: r["total"] for r in result["evidence"]}
    assert totals == {"Iota": 999, "Zen Corp": 200, "Acme": 300}
    assert result["plan"]["group_by"] == ["vendor"]


def test_ask_refusal_path(df):
    llm = Ollama(model="fake", transport=FakeOllama(
        [json.dumps({"refuse": "This data has no dates; use profile_sheet first."})]))
    result = ask.ask(df, "what happened last Tuesday?", llm=llm)
    assert result["refused"] is True
    assert "profile_sheet" in result["answer"]
    assert result["evidence"] == []


def test_ask_invalid_plan_is_refused_not_crash(df):
    llm = Ollama(model="fake", transport=FakeOllama(
        [json.dumps({"plan": {"filters": [{"column": "ghost", "op": "eq", "value": 1}]}})]))
    result = ask.ask(df, "q", llm=llm)
    assert result["refused"] is True
    assert "invalid query plan" in result["answer"]


def test_ask_parse_failure_is_instructive(df):
    llm = Ollama(model="fake", transport=FakeOllama(["nope", "still nope"]))
    result = ask.ask(df, "q", llm=llm)
    assert result["refused"] is True
    assert "could not produce a valid query plan" in result["answer"]


def test_ask_bad_narration_falls_back_to_deterministic(df):
    plan_reply = json.dumps({"plan": {"limit": 3}})
    llm = Ollama(model="fake", transport=FakeOllama([plan_reply, "garbage", "garbage"]))
    result = ask.ask(df, "q", llm=llm)
    assert result["refused"] is False
    assert "3 result row" in result["answer"]  # numbers still real
    assert len(result["evidence"]) == 3
