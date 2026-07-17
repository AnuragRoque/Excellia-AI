"""Stage C API surface: fraud, reconciliation profiles + run, KYC —
through the HTTP contract, small synthetic files on disk."""

import os

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from excellia.api.main import app
from tests.test_fraud import make_labelled

client = TestClient(app)


@pytest.fixture()
def labelled_file(tmp_path):
    path = tmp_path / "labelled.csv"
    make_labelled(n=400).to_csv(path, index=False)
    return str(path)


@pytest.fixture()
def pair_files(tmp_path):
    a = pd.DataFrame({"txn_id": ["T1", "T2", "T3"], "amount": [10.0, 20.0, 30.0]})
    b = pd.DataFrame({"txn_id": ["T1", "T2", "T9"], "amount": [10.0, 25.0, 5.0]})
    pa, pb = tmp_path / "a.csv", tmp_path / "b.csv"
    a.to_csv(pa, index=False)
    b.to_csv(pb, index=False)
    return str(pa), str(pb)


# --- fraud ------------------------------------------------------------

def test_fraud_train_score_evaluate_roundtrip(labelled_file, tmp_path):
    r = client.post("/fraud/train", json={
        "file": labelled_file, "label_column": "label", "model_name": "api-model"})
    assert r.status_code == 200, r.text
    card = r.json()["model_card"]
    assert card["cv_metrics"]["f1"] > 0.5

    assert "api-model" in [c["name"] for c in
                           client.get("/fraud/models").json()["models"]]

    fresh = tmp_path / "fresh.csv"
    make_labelled(n=30).drop(columns=["label"]).to_csv(fresh, index=False)
    r = client.post("/fraud/score", json={"file": str(fresh),
                                          "model_name": "api-model"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["scores"]) == 30
    assert body["model_card"]["name"] == "api-model"

    holdout = tmp_path / "holdout.csv"
    make_labelled(n=250).to_csv(holdout, index=False)
    r = client.post("/fraud/evaluate", json={
        "file": str(holdout), "label_column": "label", "model_name": "api-model"})
    assert r.status_code == 200, r.text
    assert "holdout_metrics" in r.json()


def test_fraud_train_refusal_is_400(labelled_file):
    r = client.post("/fraud/train", json={
        "file": labelled_file, "label_column": "ghost", "model_name": "m"})
    assert r.status_code == 400
    assert "not found" in r.json()["detail"]


def test_fraud_score_unknown_model_400():
    r = client.post("/fraud/score", json={"file": "x.csv", "model_name": "ghost"})
    assert r.status_code in (400, 404)


# --- reconciliation profiles -----------------------------------------

def test_reconcile_profile_crud_and_run(pair_files, tmp_path):
    pa, pb = pair_files
    spec = {"keys": ["txn_id"], "tolerance": {"numeric": 0.01}}
    assert client.post("/reconcile/profiles/monthly",
                       json={"spec": spec}).status_code == 200
    assert "monthly" in client.get("/reconcile/profiles").json()["profiles"]
    assert client.get("/reconcile/profiles/monthly").json()["spec"]["keys"] == ["txn_id"]

    out = str(tmp_path / "recon.xlsx")
    r = client.post("/reconcile/run", json={
        "a": pa, "b": pb, "profile_name": "monthly", "out_path": out})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["matched"] == 1          # T1
    assert body["summary"]["discrepancies"] == 1    # T2 amount differs
    assert body["summary"]["only_in_a"] == 1        # T3
    assert os.path.exists(body["report_path"])

    assert client.delete("/reconcile/profiles/monthly").status_code == 200
    assert client.get("/reconcile/profiles/monthly").status_code == 404


def test_reconcile_run_needs_exactly_one_profile(pair_files):
    pa, pb = pair_files
    r = client.post("/reconcile/run", json={"a": pa, "b": pb})
    assert r.status_code == 400
    assert "exactly one" in r.json()["detail"]


def test_reconcile_profile_needs_keys():
    r = client.post("/reconcile/profiles/bad", json={"spec": {"tolerance": {}}})
    assert r.status_code == 400
    assert "keys" in r.json()["detail"]


# --- KYC --------------------------------------------------------------

def test_kyc_match_names_endpoint(tmp_path):
    path = tmp_path / "names.csv"
    pd.DataFrame({
        "declared": ["Mohammed Iqbal", "Amit Verma"],
        "registry": ["Mohammad Iqbal", "Rohit Sharma"],
    }).to_csv(path, index=False)
    r = client.post("/kyc/match_names", json={
        "file": str(path), "col_a": "declared", "col_b": "registry",
        "seq_threshold": 60})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["candidates"] == 1
    assert body["pairs"][0]["similarity"] >= 90


def test_kyc_dedupe_endpoint(tmp_path):
    path = tmp_path / "entities.csv"
    pd.DataFrame({
        "name": ["Ram Kumar", "Ram  Kumar.", "Sita Devi"],
        "pan": ["ABCDE1234F", None, "XYZAB5678K"],
    }).to_csv(path, index=False)
    out = str(tmp_path / "clean.csv")
    r = client.post("/kyc/dedupe", json={
        "file": str(path), "columns": ["name"], "out_path": out})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows_before"] == 3 and body["rows_after"] == 2
    assert os.path.exists(body["out_path"])
    assert len(pd.read_csv(body["out_path"])) == 2


def test_kyc_bad_column_400(tmp_path):
    path = tmp_path / "n.csv"
    pd.DataFrame({"name": ["x"]}).to_csv(path, index=False)
    r = client.post("/kyc/match_names", json={
        "file": str(path), "col_a": "ghost", "col_b": "name"})
    assert r.status_code == 400
    assert "Actual columns" in r.json()["detail"]


# --- job ops registered ----------------------------------------------

def test_stage_c_job_ops_available():
    r = client.post("/jobs", json={"op": "nope", "params": {}})
    detail = r.json()["detail"]
    for op in ("fraud_train", "fraud_score", "reconcile_run",
               "kyc_match_names", "kyc_dedupe"):
        assert op in detail
