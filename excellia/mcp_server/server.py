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


def _forward(method: str, path: str, payload: dict | None = None) -> dict:
    """Forward to the API; turn HTTP errors into {'error': instructive text}."""
    err = _ensure_api()
    if err:
        return {"error": err}
    resp = requests.request(method, f"{API}{path}", json=payload, timeout=600)
    try:
        body = resp.json()
    except ValueError:
        return {"error": f"Core API returned a non-JSON response (HTTP {resp.status_code})."}
    if resp.status_code >= 400:
        return {"error": body.get("detail", str(body))}
    return body


def _post(path: str, payload: dict) -> dict:
    return _forward("POST", path, payload)


def _maybe_job(op: str, params: dict, async_: bool) -> dict:
    """Run an op sync, or queue it and return a job_id when async_ is true."""
    if async_:
        return _post("/jobs", {"op": op, "params": params})
    paths = {"transform_apply": "/transform/apply", "report": "/report",
             "clean": "/clean"}
    return _post(paths.get(op, f"/{op}"), params)


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


@mcp.tool()
def ask_data(file_path: str, question: str, sheet: str | None = None) -> dict:
    """Ask a natural-language question about a spreadsheet's contents ("total amount
    by vendor", "how many rows have a missing email"). A local LLM plans a query,
    deterministic pandas computes it, and every number in the answer comes from the
    returned evidence table — check it. Needs Ollama running locally; if it isn't,
    the error says how to start it. For rule violations use `validate`; for outliers
    use `detect_anomalies`."""
    return _post("/ask", {"file": file_path, "question": question, "sheet": sheet})


@mcp.tool()
def transform_preview(file_path: str, instruction: str, sheet: str | None = None) -> dict:
    """Turn a cleaning/transformation instruction ("split address into street, city,
    pin", "uppercase vendor names", "tag rows as corporate or individual") into a
    recipe and show before/after on a 20-row sample. NOTHING is changed yet — review
    the sample, then pass the returned recipe to `transform_apply`. Needs Ollama
    running locally. Deterministic ops are preferred; llm_map steps only where
    meaning is required."""
    return _post("/transform/preview", {"file": file_path, "instruction": instruction,
                                        "sheet": sheet})


@mcp.tool()
def transform_apply(
    file_path: str,
    recipe: dict | None = None,
    instruction: str | None = None,
    recipe_name: str | None = None,
    replace: bool = False,
    save_as: str | None = None,
    out_path: str | None = None,
    async_: bool = False,
) -> dict:
    """Apply a transformation and write the result to a NEW file (the input is never
    modified — undo is the original file). Pass exactly one of: `recipe` (from
    transform_preview — the confirmed path), `recipe_name` (a saved recipe), or
    `instruction` (one-shot). Changed values go to new `_ai`-suffixed columns unless
    replace=true. `save_as` also saves the recipe for replay via `run_recipe`.
    For big files pass async_=true and poll `job_status`."""
    params = {"file": file_path, "recipe": recipe, "instruction": instruction,
              "recipe_name": recipe_name, "replace": replace, "save_as": save_as,
              "out_path": out_path}
    return _maybe_job("transform_apply", params, async_)


@mcp.tool()
def run_recipe(file_path: str, recipe_name: str, out_path: str | None = None,
               async_: bool = False) -> dict:
    """Replay a SAVED cleanup recipe on a new file — next month's file gets last
    month's fixes in one call. Writes to a new file; the input is never modified.
    Unknown recipe -> error listing saved recipes (save one via transform_apply's
    save_as). For big files pass async_=true and poll `job_status`."""
    params = {"file": file_path, "recipe_name": recipe_name, "out_path": out_path}
    return _maybe_job("transform_apply", params, async_)


@mcp.tool()
def save_ruleset(name: str, spec: dict) -> dict:
    """Save a reusable validation ruleset for `validate`. Spec keys (all optional):
    required=[cols], formats={col: gst|pan|aadhaar|email|phone|ifsc},
    ranges={col: {min, max}}, unique=[cols], references={col: [allowed]},
    expressions=[{name, expr, severity}] (pandas-eval, e.g. "net_pay <= gross_pay"),
    auto=false to skip inferred checks. Read it back as the resource ruleset://<name>."""
    return _post(f"/rulesets/{name}", {"spec": spec})


@mcp.tool()
def export_report(file_path: str, ruleset: str = "default", sensitivity: float = 0.05,
                  out_path: str | None = None, sheet: str | None = None,
                  async_: bool = False) -> dict:
    """Write a highlighted xlsx quality report next to the file: Data sheet with
    problem cells coloured by kind, Issues + Anomalies sheets, and a Summary with
    the Data Health Score and its full deduction breakdown (never a bare number).
    Returns the report path and the health score. The input file is never modified.
    For big files pass async_=true and poll `job_status`."""
    params = {"file": file_path, "ruleset": ruleset, "sensitivity": sensitivity,
              "out_path": out_path, "sheet": sheet}
    return _maybe_job("report", params, async_)


@mcp.tool()
def job_status(job_id: str) -> dict:
    """Check a background job started with async_=true on another tool. Status is
    queued | running | done | error; when done, the full result is under 'result'.
    Poll every few seconds — do not busy-loop. Unknown id -> error saying how to
    list jobs."""
    return _forward("GET", f"/jobs/{job_id}")


@mcp.resource("ruleset://{name}")
def ruleset_resource(name: str) -> str:
    """A saved or built-in validation ruleset spec as JSON."""
    import json

    return json.dumps(_forward("GET", f"/rulesets/{name}"), indent=2)


@mcp.resource("recipe://{name}")
def recipe_resource(name: str) -> str:
    """A saved transformation recipe as JSON."""
    import json

    return json.dumps(_forward("GET", f"/recipes/{name}"), indent=2)


def main() -> None:
    """Entry point for `excellia-mcp`."""
    mcp.run()


if __name__ == "__main__":
    main()
