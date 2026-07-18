"""Excel add-in: static delivery, manifest/metadata/runtime consistency,
and the /values endpoints the =XAI.* formulas call.

Excel itself can't run in CI — sideloading stays a documented manual
step — but everything mechanical about the add-in is asserted here.
"""

import json
import pathlib
import re
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

import excellia
from excellia.api.main import app
from excellia.core import transform, validate
from excellia.core.llm import Ollama
from tests.conftest import FakeOllama

client = TestClient(app)
STATIC = pathlib.Path(excellia.__file__).parent / "addin" / "static"


# --- static consistency ----------------------------------------------

def test_manifest_is_wellformed_and_selfconsistent():
    tree = ET.parse(STATIC / "manifest.xml")
    xml = (STATIC / "manifest.xml").read_text(encoding="utf-8")
    assert tree.getroot().tag.endswith("OfficeApp")
    # every referenced localhost URL resolves to a real shipped file
    for url in set(re.findall(r"https://localhost:8443/addin/([\w.\-]+)", xml)):
        assert (STATIC / url).exists(), f"manifest references missing file {url}"
    assert 'id="Fn.Namespace" DefaultValue="XAI"' in xml  # the formula namespace


def test_functions_metadata_matches_runtime():
    meta = json.loads((STATIC / "functions.json").read_text(encoding="utf-8"))
    js = (STATIC / "functions.js").read_text(encoding="utf-8")
    ids = {f["id"] for f in meta["functions"]}
    assert ids == {"RUN", "TAG", "SPLIT", "ASK", "VALIDATE", "MATCH"}
    for fid in ids:
        assert f'CustomFunctions.associate("{fid}"' in js, f"{fid} not associated in functions.js"
    for f in meta["functions"]:
        assert f["description"], f["id"]
        assert "=XAI." in f["description"], f"{f['id']} description lacks a usage example"


def test_static_files_served():
    for name in ("manifest.xml", "taskpane.html", "taskpane.js", "functions.js",
                 "functions.json", "functions.html", "icon-32.png", "icon-80.png"):
        r = client.get(f"/addin/{name}")
        assert r.status_code == 200, name


def test_addin_owns_zero_logic():
    for js in ("taskpane.js", "functions.js"):
        text = (STATIC / js).read_text(encoding="utf-8")
        assert "fetch(" in text
        assert "pandas" not in text


# --- /values endpoints (deterministic) --------------------------------

def test_values_validate():
    r = client.post("/values/validate", json={
        "values": ["ABCDE1234F", "not-a-pan", None], "format": "pan"})
    assert r.json()["results"] == [True, False, False]


def test_values_validate_unknown_format_lists_available():
    r = client.post("/values/validate", json={"values": ["x"], "format": "ssn"})
    assert r.status_code == 400
    assert "pan" in r.json()["detail"]


def test_values_similarity():
    r = client.post("/values/similarity", json={
        "a": ["Mohammed Iqbal"], "b": ["Mohammad Iqbal"]})
    assert r.json()["results"][0] >= 90


def test_values_similarity_length_mismatch_400():
    r = client.post("/values/similarity", json={"a": ["x", "y"], "b": ["x"]})
    assert r.status_code == 400
    assert "equal-length" in r.json()["detail"]


def test_values_ask_bad_rows_400():
    r = client.post("/values/ask", json={"columns": ["a"], "rows": [], "question": "?"})
    assert r.status_code == 400


# --- /values endpoints needing Ollama fail instructively --------------

@pytest.fixture()
def ollama_down(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:9")


def test_values_map_503_when_ollama_down(ollama_down):
    r = client.post("/values/map", json={"values": ["x"], "instruction": "shout"})
    assert r.status_code == 503
    assert "Ollama is not reachable" in r.json()["detail"]


def test_values_split_needs_parts(ollama_down):
    r = client.post("/values/split", json={"values": ["x"], "parts": []})
    assert r.status_code == 400


# --- core value functions (LLM paths with fakes) ----------------------

def test_check_format_core():
    assert validate.check_format(["ABCDE1234F", "nope", None, float("nan")], "pan") == \
        [True, False, False, False]
    with pytest.raises(ValueError, match="Available"):
        validate.check_format(["x"], "zzz")


def test_map_values_dedups_and_orders():
    llm = Ollama(model="fake", transport=FakeOllama(
        [json.dumps({"value": "A"}), json.dumps({"value": "B"})]))
    out = transform.map_values(["a", "b", "a", None], "upper", llm=llm)
    assert out == ["A", "B", "A", ""]


def test_split_values_pads_and_truncates():
    llm = Ollama(model="fake", transport=FakeOllama([
        json.dumps({"parts": ["12 MG Rd", "Pune"]}),          # short -> padded
        json.dumps({"parts": ["x", "y", "z", "extra"]}),       # long -> truncated
    ]))
    out = transform.split_values(["addr1", "addr2"], ["street", "city", "pin"], llm=llm)
    assert out == [["12 MG Rd", "Pune", ""], ["x", "y", "z"]]


def test_split_values_parse_failure_yields_blanks():
    llm = Ollama(model="fake", transport=FakeOllama(["junk", "junk again"]))
    out = transform.split_values(["v"], ["a", "b"], llm=llm)
    assert out == [["", ""]]


def test_serve_module_helpers():
    from excellia.addin import serve

    help_text = serve.sideload_help()
    assert "manifest.xml" in help_text
    assert "wef" in help_text          # the macOS path
    assert "Trusted Add-in Catalogs" in help_text
