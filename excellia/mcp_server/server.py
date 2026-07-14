"""Excellia MCP server. Thin adapter: forwards to the core API.

Zero validation logic, zero pandas, zero Ollama. If this file ever
gets fat, the architecture is wrong. Transport is stdio — the host
(Claude Desktop, local_agent) launches this as a subprocess.

The only non-forwarding behaviour here is convenience: if the core
API isn't running, we spawn it as a child process (stdout/stderr
silenced — stdout carries the MCP protocol) and wait for /health.
"""

import atexit
import os
import subprocess
import sys
import tempfile
import time

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("excellia")
API = os.environ.get("EXCELLIA_API", "http://127.0.0.1:8000")

_api_process: subprocess.Popen | None = None


def _api_up() -> bool:
    try:
        return requests.get(f"{API}/health", timeout=2).ok
    except requests.RequestException:
        return False


def _ensure_api() -> str | None:
    """Start the core API if it isn't running. Returns an error string on failure."""
    global _api_process
    if _api_up():
        return None
    if "127.0.0.1" not in API and "localhost" not in API:
        return (
            f"The Excellia core API at {API} is not reachable, and it is not local "
            "so it cannot be auto-started. Start it on that machine, or unset "
            "EXCELLIA_API to use a local one."
        )
    if _api_process is None or _api_process.poll() is not None:
        log = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", prefix="excellia-api-", delete=False
        )
        # Launch fully detached. Spawned inline as a grandchild of the stdio
        # MCP server (which itself inherits the host's JSON-RPC pipes),
        # uvicorn silently fails to finish binding on Windows. Giving the API
        # its own process group + no inherited console/pipes fixes that.
        kwargs: dict = dict(
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,  # stdout carries our MCP protocol; keep it clean
            stderr=log,
            close_fds=True,
        )
        if os.name == "nt":
            # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
            kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
        else:
            kwargs["start_new_session"] = True
        _api_process = subprocess.Popen(
            [sys.executable, "-m", "excellia.api.main"], **kwargs
        )
        _api_process._excellia_log = log.name  # type: ignore[attr-defined]
        atexit.register(_api_process.terminate)
    # Cold start loads pandas+sklearn and may compete with an LLM loading
    # into RAM — allow a generous window, but fail fast if the child dies.
    for _ in range(160):  # ~40s
        if _api_up():
            return None
        if _api_process.poll() is not None:
            tail = ""
            log_path = getattr(_api_process, "_excellia_log", None)
            if log_path and os.path.exists(log_path):
                with open(log_path, encoding="utf-8", errors="replace") as f:
                    tail = f.read()[-500:]
            return (
                f"The Excellia core API crashed on startup (exit code "
                f"{_api_process.returncode}). Last output: {tail or 'none'}. "
                "Fix the cause or run `excellia-api` in a terminal to see the full log."
            )
        time.sleep(0.25)
    return (
        "The Excellia core API did not start in time. Run `excellia-api` in a "
        "terminal, wait for it to report startup, then retry this tool."
    )


def _post(path: str, payload: dict) -> dict:
    """Forward to the API; turn HTTP errors into {'error': instructive text}."""
    err = _ensure_api()
    if err:
        return {"error": err}
    resp = requests.post(f"{API}{path}", json=payload, timeout=600)
    try:
        body = resp.json()
    except ValueError:
        return {"error": f"Core API returned a non-JSON response (HTTP {resp.status_code})."}
    if resp.status_code >= 400:
        return {"error": body.get("detail", str(body))}
    return body


@mcp.tool()
def profile_sheet(file_path: str, sheet: str | None = None) -> dict:
    """Get a data profile of a spreadsheet: row/column counts, per-column inferred
    types, null rates, cardinality, stats, and auto-detected formats (GST, PAN,
    email, ...). Use this FIRST on any unfamiliar file to learn its shape before
    validating or transforming. Accepts .xlsx/.xlsm/.xls/.csv/.tsv; pass `sheet`
    to pick a worksheet. On error, returns {"error": what to fix}."""
    return _post("/profile", {"file": file_path, "sheet": sheet})


@mcp.tool()
def validate(file_path: str, ruleset: str = "default", sheet: str | None = None) -> dict:
    """Check a spreadsheet against deterministic validation rules: required fields,
    format checks (GST/PAN/Aadhaar/email/phone/IFSC), ranges, uniqueness, duplicate
    rows/IDs, mixed types. Returns issues each with row (Excel numbering: header=1,
    data starts at 2), column, rule_name, severity, and a human-readable reason,
    plus a summary. The 'default' ruleset auto-infers checks from the data; pass a
    named ruleset for domain rules. Unknown ruleset -> error listing available ones."""
    return _post("/validate", {"file": file_path, "ruleset": ruleset, "sheet": sheet})


@mcp.tool()
def detect_anomalies(file_path: str, sensitivity: float = 0.05, sheet: str | None = None) -> dict:
    """Find statistically suspicious rows that break no explicit rule: Isolation
    Forest multivariate outliers, per-column outliers, rare categories, near-duplicate
    rows, and pattern breaks. Each flag carries a confidence (0-1), the columns
    involved, and a 'why flagged' reason; rows use Excel numbering (data starts at 2).
    `sensitivity` is the expected outlier fraction (0-0.5, default 0.05); raise it to
    flag more rows. Use `validate` instead for rule violations."""
    return _post("/anomalies", {"file": file_path, "contamination": sensitivity, "sheet": sheet})


@mcp.tool()
def reconcile(
    file_a: str,
    file_b: str,
    key_columns: list[str],
    tolerance: dict | None = None,
) -> dict:
    """Compare two spreadsheets by key column(s) and bucket every record:
    matched, only_in_a, only_in_b, and discrepancies (key matched but other fields
    differ — each lists the differing fields with both values). Keys match
    case/whitespace-insensitively. Optional `tolerance`: {"numeric": 0.01} allows
    small amount differences, {"days": 1} allows date drift, {"fuzzy": 0.9} allows
    near-equal text (0-1 similarity). If a key column is missing, the error lists
    each file's actual columns — pick the right one and retry."""
    return _post("/reconcile", {"a": file_a, "b": file_b, "keys": key_columns, "tolerance": tolerance})


def main() -> None:
    """Entry point for `excellia-mcp`."""
    mcp.run()


if __name__ == "__main__":
    main()
