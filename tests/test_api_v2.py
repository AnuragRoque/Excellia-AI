"""Stage B API surface: clean, transform (recipe path), report, workspace
CRUD, history, and the job queue — all through the HTTP contract.

LLM-dependent endpoints are unit-tested in core with fakes; here we only
assert their instructive 503 when Ollama is down.
"""

import os
import time

import pytest
from fastapi.testclient import TestClient

from excellia.api.main import app

client = TestClient(app)

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")
MESSY = os.path.abspath(os.path.join(EXAMPLES, "messy_vendors.xlsx"))


# --- clean ------------------------------------------------------------

def test_clean_writes_new_file(tmp_path):
    out = str(tmp_path / "clean.xlsx")
    r = client.post("/clean", json={
        "file": MESSY, "out_path": out,
        "steps": [{"op": "trim", "params": {"columns": ["vendor_name"]}}],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert os.path.exists(body["out_path"])
    assert body["rows"] == 50
    assert "not modified" in body["note"]


def test_clean_bad_step_is_instructive():
    r = client.post("/clean", json={"file": MESSY, "steps": [{"op": "sparkle"}]})
    assert r.status_code == 400
    assert "trim" in r.json()["detail"]  # lists real ops


# --- transform via literal recipe (no LLM needed) ---------------------

def test_transform_apply_recipe_and_save(tmp_path):
    out = str(tmp_path / "t.xlsx")
    recipe = {"steps": [{"op": "case", "params": {"columns": "vendor_name", "to": "title"}}]}
    r = client.post("/transform/apply", json={
        "file": MESSY, "recipe": recipe, "out_path": out, "save_as": "title-vendors",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert os.path.exists(body["out_path"])
    assert "vendor_name_ai" in body["columns"]  # non-destructive default
    assert body["saved_recipe"]

    # saved recipe is now replayable by name
    out2 = str(tmp_path / "t2.xlsx")
    r2 = client.post("/transform/apply", json={
        "file": MESSY, "recipe_name": "title-vendors", "out_path": out2})
    assert r2.status_code == 200
    assert os.path.exists(r2.json()["out_path"])


def test_transform_apply_needs_exactly_one_source():
    r = client.post("/transform/apply", json={"file": MESSY})
    assert r.status_code == 400
    assert "exactly one" in r.json()["detail"]

    r = client.post("/transform/apply", json={
        "file": MESSY, "recipe_name": "x", "instruction": "y"})
    assert r.status_code == 400


def test_transform_unknown_recipe_404_lists_saved():
    r = client.post("/transform/apply", json={"file": MESSY, "recipe_name": "ghost"})
    assert r.status_code == 404
    assert "No saved recipe" in r.json()["detail"]


# --- report -----------------------------------------------------------

def test_report_endpoint(tmp_path):
    out = str(tmp_path / "rep.xlsx")
    r = client.post("/report", json={"file": MESSY, "out_path": out})
    assert r.status_code == 200, r.text
    body = r.json()
    assert os.path.exists(body["path"])
    assert "score" in body["health"] and body["health"]["breakdown"]


# --- rulesets CRUD ----------------------------------------------------

def test_ruleset_crud_and_validation_use():
    spec = {"formats": {"pan": "pan"}, "auto": False}
    assert client.post("/rulesets/my-pans", json={"spec": spec}).status_code == 200
    assert "my-pans" in client.get("/rulesets").json()["rulesets"]
    got = client.get("/rulesets/my-pans").json()
    assert got["spec"] == spec

    # the saved ruleset actually drives /validate
    r = client.post("/validate", json={"file": MESSY, "ruleset": "my-pans"})
    assert r.status_code == 200

    assert client.delete("/rulesets/my-pans").status_code == 200
    assert client.get("/rulesets/my-pans").status_code == 404


def test_ruleset_builtin_protected():
    assert client.post("/rulesets/kyc", json={"spec": {}}).status_code == 400
    assert client.delete("/rulesets/kyc").status_code == 400


def test_ruleset_unknown_keys_rejected():
    r = client.post("/rulesets/bad", json={"spec": {"formatz": {}}})
    assert r.status_code == 400
    assert "formats" in r.json()["detail"]


def test_starter_packs_present():
    names = client.get("/rulesets").json()["builtin"]
    assert {"kyc", "invoice", "payroll", "bank-statement"} <= set(names)


# --- recipes CRUD -----------------------------------------------------

def test_recipe_crud():
    spec = {"steps": [{"op": "trim", "params": {}}]}
    assert client.post("/recipes/std", json={"spec": spec}).status_code == 200
    assert "std" in client.get("/recipes").json()["recipes"]
    assert client.get("/recipes/std").json()["spec"] == spec
    assert client.delete("/recipes/std").status_code == 200
    assert client.get("/recipes/std").status_code == 404


def test_recipe_save_validates_shape():
    r = client.post("/recipes/bad", json={"spec": {"steps": [{"op": "sparkle"}]}})
    assert r.status_code == 400


# --- history ----------------------------------------------------------

def test_history_records_operations():
    client.post("/profile", json={"file": MESSY})
    entries = client.get("/history").json()["history"]
    assert entries and entries[0]["op"] == "profile"
    assert entries[0]["file"] == "messy_vendors.xlsx"
    assert "file_hash" in entries[0]


# --- jobs -------------------------------------------------------------

def _wait_job(job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.1)
    pytest.fail("job did not finish in time")


def test_job_validate_end_to_end():
    r = client.post("/jobs", json={"op": "validate", "params": {"file": MESSY}})
    assert r.status_code == 200
    job = _wait_job(r.json()["job_id"])
    assert job["status"] == "done", job.get("error")
    assert job["result"]["summary"]["total"] > 0
    # result parked on disk in the workspace
    from excellia.core import store
    assert (store.home() / "jobs" / f"{job['job_id']}.json").exists()


def test_job_error_is_instructive_not_a_crash():
    r = client.post("/jobs", json={"op": "validate",
                                   "params": {"file": "C:/nope/ghost.xlsx"}})
    job = _wait_job(r.json()["job_id"])
    assert job["status"] == "error"
    assert "File not found" in job["error"]


def test_job_unknown_op_lists_available():
    r = client.post("/jobs", json={"op": "teleport", "params": {}})
    assert r.status_code == 400
    assert "validate" in r.json()["detail"]


def test_job_unknown_id_404():
    assert client.get("/jobs/nope123").status_code == 404


def test_jobs_list():
    client.post("/jobs", json={"op": "profile", "params": {"file": MESSY}})
    assert len(client.get("/jobs").json()["jobs"]) >= 1


# --- LLM endpoints fail instructively when Ollama is down -------------

@pytest.fixture()
def ollama_down(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")


def test_ask_503_when_ollama_down(ollama_down):
    r = client.post("/ask", json={"file": MESSY, "question": "how many rows?"})
    assert r.status_code == 503
    assert "Ollama is not reachable" in r.json()["detail"]


def test_transform_preview_503_when_ollama_down(ollama_down):
    r = client.post("/transform/preview", json={"file": MESSY, "instruction": "tidy"})
    assert r.status_code == 503
    assert "profile/validate" in r.json()["detail"]  # names what still works
