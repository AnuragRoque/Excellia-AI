"""kyc.py: golden name pairs, LLM-verified matching, entity dedupe."""

import json

import pandas as pd
import pytest

from excellia.core import kyc
from excellia.core.llm import Ollama
from tests.conftest import FakeOllama


# --- similarity golden pairs -----------------------------------------

@pytest.mark.parametrize("a,b,low,high", [
    ("Mohammed Iqbal", "Mohammad Iqbal", 90, 100),   # transliteration variant
    ("RAM KUMAR", "ram   kumar", 100, 100),          # case/space only
    ("Sh. Ram Kumar", "Ram Kumar", 75, 100),         # honorific
    ("Priya Sharma", "Priya  Sharma-", 95, 100),     # stray punctuation
    ("Ram Kumar", "Shyam Sundar", 0, 65),            # different people
    ("", "Ram", 0, 0),                               # empty side scores zero
])
def test_similarity_golden_pairs(a, b, low, high):
    sim = kyc.name_similarity(a, b)
    assert low <= sim <= high, f"{a!r} vs {b!r} -> {sim}"


# --- pairwise mode ----------------------------------------------------

def test_match_names_pairwise():
    df = pd.DataFrame({
        "declared": ["Mohammed Iqbal", "Priya Sharma", "Amit Verma"],
        "registry": ["Mohammad Iqbal", "Priya Sharma", "Rohit Verma"],
    })
    out = kyc.match_names(df, col_a="declared", col_b="registry", seq_threshold=60)
    pairs = {p["row"]: p for p in out["pairs"]}
    assert pairs[2]["similarity"] >= 90
    assert pairs[2]["verdict"] == "candidate"  # no LLM asked for
    assert out["summary"]["compared"] == 3


def test_match_names_cross_group():
    df = pd.DataFrame({
        "name": ["Ram Kumar", "R Kumar", "Sita Devi", "Ram  Kumar"],
        "branch": ["mum", "mum", "mum", "del"],
    })
    out = kyc.match_names(df, col_a="name", group_by="branch", seq_threshold=70)
    # only within-branch pairs: Ram Kumar vs R Kumar (mum); the del row is alone
    names = {(p["name_a"], p["name_b"]) for p in out["pairs"]}
    assert ("Ram Kumar", "R Kumar") in names
    assert all("Sita Devi" not in pair for pair in names)


def test_match_names_pair_explosion_guarded(monkeypatch):
    monkeypatch.setattr(kyc, "_MAX_PAIRS", 10)
    df = pd.DataFrame({"name": [f"Name {i}" for i in range(10)]})
    with pytest.raises(kyc.KycError, match="group_by"):
        kyc.match_names(df, col_a="name")


def test_match_names_bad_column_lists_actual():
    df = pd.DataFrame({"name": ["x"]})
    with pytest.raises(kyc.KycError, match="Actual columns"):
        kyc.match_names(df, col_a="nope", col_b="name")


def test_match_names_needs_a_mode():
    with pytest.raises(kyc.KycError, match="col_a"):
        kyc.match_names(pd.DataFrame({"n": ["x"]}))


# --- LLM verification -------------------------------------------------

def test_llm_verify_verdicts():
    df = pd.DataFrame({"declared": ["Mohammed Iqbal"], "registry": ["Mohammad Iqbal"]})
    llm = Ollama(model="fake", transport=FakeOllama([
        json.dumps({"status": "match", "match_percent": 96,
                    "reason": "transliteration variant of the same name"})]))
    out = kyc.match_names(df, col_a="declared", col_b="registry",
                          llm_verify=True, llm=llm)
    p = out["pairs"][0]
    assert p["verdict"] == "match"
    assert p["llm_percent"] == 96
    assert "transliteration" in p["reason"]


def test_llm_verify_parse_failure_degrades_to_unverified():
    df = pd.DataFrame({"a": ["Ram Kumar"], "b": ["Ram Kumar"]})
    llm = Ollama(model="fake", transport=FakeOllama(["garbage", "more garbage"]))
    out = kyc.match_names(df, col_a="a", col_b="b", llm_verify=True, llm=llm)
    p = out["pairs"][0]
    assert p["verdict"] == "unverified"
    assert p["similarity"] == 100.0  # deterministic score survives


# --- entity dedupe ----------------------------------------------------

@pytest.fixture()
def entities():
    return pd.DataFrame({
        "name": ["Ram Kumar", "Ram  Kumar.", "RAM KUMAR", "Sita Devi", "Amit Verma"],
        "city": ["Pune", "Pune", "Pune", "Delhi", "Mumbai"],
        "pan": ["ABCDE1234F", None, "ABCDE1234F", "XYZAB5678K", "PQRST9012L"],
    })


def test_dedupe_clusters_and_canonical(entities):
    out = kyc.dedupe(entities, columns=["name", "city"], threshold=85)
    assert out["rows_before"] == 5
    assert out["rows_after"] == 3
    assert out["clusters_merged"] == 1
    merge = out["merges"][0]
    # most_complete keeps a row that has the PAN filled
    assert merge["values"]["name"] in ("Ram Kumar", "RAM KUMAR")
    assert len(merge["merged_rows"]) == 2
    assert set(out["deduped"]["name"]).issuperset({"Sita Devi", "Amit Verma"})


def test_dedupe_strategy_first(entities):
    out = kyc.dedupe(entities, columns=["name", "city"], threshold=85,
                     strategy="first")
    assert out["merges"][0]["canonical_row"] == 2  # Excel row of the first copy


def test_dedupe_bad_strategy():
    with pytest.raises(kyc.KycError, match="most_complete"):
        kyc.dedupe(pd.DataFrame({"n": ["x"]}), columns=["n"], strategy="best")


def test_dedupe_untouched_input(entities):
    before = entities.copy()
    kyc.dedupe(entities, columns=["name"], threshold=90)
    assert entities.equals(before)
