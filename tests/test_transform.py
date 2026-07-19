"""transform.py: preview never mutates, apply is non-destructive by default,
recipes replay deterministically."""

import json

import pandas as pd
import pytest

from excellia.core import store, transform
from excellia.core.llm import Ollama
from tests.conftest import FakeOllama


@pytest.fixture()
def df():
    return pd.DataFrame({
        "name": ["  ram ", "SITA  devi"],
        "address": ["12 MG Rd|Pune|411001", "5 Park St|Kolkata|700016"],
    })


def test_validate_recipe_shapes():
    with pytest.raises(transform.TransformError, match="steps"):
        transform.validate_recipe({"nope": 1})
    with pytest.raises(transform.TransformError, match="no steps"):
        transform.validate_recipe({"steps": []})
    with pytest.raises(transform.TransformError, match="unknown op"):
        transform.validate_recipe({"steps": [{"op": "sparkle"}]})
    with pytest.raises(transform.TransformError, match="llm_map needs params"):
        transform.validate_recipe({"steps": [{"op": "llm_map", "params": {"column": "x"}}]})
    # the flat-step mistake (op args at the top level) is named, not a TypeError
    with pytest.raises(transform.TransformError, match=r'inside "params"'):
        transform.validate_recipe(
            {"steps": [{"op": "case", "columns": ["name"], "to": "lower"}]})


def test_apply_bad_param_names_are_instructive(df):
    # right shape, wrong param name -> step number + params named, no raw TypeError
    recipe = {"steps": [{"op": "case", "params": {"columns": ["name"], "mode": "lower"}}]}
    with pytest.raises(transform.TransformError, match=r"Step 1 \(case\): bad params"):
        transform.apply(df, recipe)


def test_apply_value_op_goes_to_ai_columns(df):
    recipe = {"steps": [{"op": "trim", "params": {"columns": ["name"]}}]}
    out = transform.apply(df, recipe)
    assert out["name"][0] == "  ram "        # original preserved
    assert out["name_ai"][0] == "ram"        # cleaned copy beside it
    assert "name_ai" in out.columns


def test_apply_replace_true_edits_in_place(df):
    recipe = {"steps": [{"op": "trim", "params": {"columns": ["name"]}}]}
    out = transform.apply(df, recipe, replace=True)
    assert out["name"][0] == "ram"
    assert "name_ai" not in out.columns


def test_apply_structural_op_as_is(df):
    recipe = {"steps": [{"op": "split_column", "params": {
        "column": "address", "delimiter": "|", "into": ["street", "city", "pin"]}}]}
    out = transform.apply(df, recipe)
    assert out["city"].tolist() == ["Pune", "Kolkata"]
    assert out["address"].equals(df["address"])  # source column intact


def test_llm_map_strict_json_and_dedup(df):
    df2 = pd.DataFrame({"city": ["Pune", "Pune", "Kolkata"]})
    # only 2 DISTINCT values -> exactly 2 model calls
    fake = FakeOllama([json.dumps({"value": "west"}), json.dumps({"value": "east"})])
    llm = Ollama(model="fake", transport=fake)
    recipe = {"steps": [{"op": "llm_map", "params": {
        "column": "city", "into": "zone", "instruction": "east or west?"}}]}
    out = transform.apply(df2, recipe, llm=llm)
    assert out["zone"].tolist() == ["west", "west", "east"]
    assert len([r for r in fake.requests if r[0] == "/api/chat"]) == 2


def test_llm_map_parse_failure_yields_empty_not_crash():
    df2 = pd.DataFrame({"x": ["a"]})
    llm = Ollama(model="fake", transport=FakeOllama(["junk", "more junk"]))
    recipe = {"steps": [{"op": "llm_map", "params": {
        "column": "x", "into": "y", "instruction": "t"}}]}
    out = transform.apply(df2, recipe, llm=llm)
    assert out["y"][0] == ""


def test_preview_returns_recipe_and_sample_without_mutating(df):
    reply = json.dumps({"steps": [{"op": "trim", "params": {"columns": ["name"]}}],
                        "note": "trim the names"})
    llm = Ollama(model="fake", transport=FakeOllama([reply]))
    before_copy = df.copy()
    result = transform.preview(df, "clean up names", llm=llm)
    assert df.equals(before_copy)                      # nothing mutated
    assert result["recipe"]["steps"][0]["op"] == "trim"
    assert result["after"][0]["name_ai"] == "ram"
    assert "transform_apply" in result["next_step"]


def test_preview_invalid_model_recipe_is_instructive(df):
    llm = Ollama(model="fake", transport=FakeOllama(
        [json.dumps({"steps": [{"op": "hallucinated_op"}]})]))
    with pytest.raises(transform.TransformError, match="unknown op"):
        transform.preview(df, "do magic", llm=llm)


def test_recipe_save_load_replay_determinism(df):
    recipe = {"instruction": "std clean", "steps": [
        {"op": "trim", "params": {"columns": ["name"]}},
        {"op": "case", "params": {"columns": "name", "to": "title"}},
    ]}
    store.save("recipes", "monthly-clean", recipe)
    loaded = store.load("recipes", "monthly-clean")
    out1 = transform.apply(df, recipe, replace=True)
    out2 = transform.apply(df, loaded, replace=True)
    assert out1.equals(out2)
    assert out1["name"].tolist() == ["Ram", "Sita Devi"]
