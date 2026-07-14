"""Instructive-error contract: an AI caller must be able to read any
error and know what to fix. These strings are part of the interface."""

import asyncio

from fastapi.testclient import TestClient

from excellia.api.main import app
from excellia.mcp_server import server as mcp_server

client = TestClient(app)
MESSY = "examples/messy_vendors.xlsx"


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_missing_file_tells_how_to_fix():
    r = client.post("/profile", json={"file": "no_such_file.xlsx"})
    assert r.status_code == 404
    assert "Provide an absolute path" in r.json()["detail"]


def test_unknown_ruleset_lists_available(tmp_path):
    r = client.post("/validate", json={"file": MESSY, "ruleset": "nope"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "Unknown ruleset" in detail and "default" in detail


def test_unsupported_extension_names_supported(tmp_path):
    bad = tmp_path / "data.parquet"
    bad.write_bytes(b"x")
    r = client.post("/profile", json={"file": str(bad)})
    assert r.status_code == 400
    assert "Supported" in r.json()["detail"]


def test_bad_sensitivity_is_a_422_from_schema():
    # pydantic bounds catch it before core does
    r = client.post("/anomalies", json={"file": MESSY, "contamination": 0.9})
    assert r.status_code == 422


def test_reconcile_missing_key_lists_columns():
    r = client.post("/reconcile", json={"a": MESSY, "b": MESSY, "keys": ["not_a_key"]})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "not found" in detail and "vendor_id" in detail


def test_validate_summary_carries_row_convention():
    r = client.post("/validate", json={"file": MESSY})
    assert r.status_code == 200
    assert "Excel rows" in r.json()["summary"]["note"]


def test_string_null_sheet_is_coerced_to_none():
    # local models routinely pass the literal string "null" for optional params
    for sentinel in ("null", "none", "", "NaN"):
        r = client.post("/validate", json={"file": MESSY, "sheet": sentinel})
        assert r.status_code == 200, f"sheet={sentinel!r} should behave as no sheet"


def test_string_null_ruleset_falls_back_to_default():
    r = client.post("/validate", json={"file": MESSY, "ruleset": "null"})
    assert r.status_code == 200
    assert r.json()["summary"]["total"] > 0


# --- MCP server (no live API needed) -----------------------------------

def test_mcp_registers_all_four_tools():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    assert {t.name for t in tools} == {
        "profile_sheet", "validate", "detect_anomalies", "reconcile",
    }
    for t in tools:
        assert len(t.description) > 80, f"{t.name} docstring too thin to guide a model"


def test_mcp_reports_api_down_instructively(monkeypatch):
    monkeypatch.setattr(mcp_server, "_ensure_api", lambda: "API is down; run `excellia-api`.")
    out = mcp_server._post("/validate", {})
    assert out == {"error": "API is down; run `excellia-api`."}


def test_mcp_forwards_http_error_detail(monkeypatch):
    class FakeResp:
        status_code = 404

        @staticmethod
        def json():
            return {"detail": "File not found: x.xlsx. Provide an absolute path."}

    monkeypatch.setattr(mcp_server, "_ensure_api", lambda: None)
    monkeypatch.setattr(mcp_server.requests, "post", lambda *a, **k: FakeResp())
    out = mcp_server._post("/profile", {"file": "x.xlsx"})
    assert "Provide an absolute path" in out["error"]
