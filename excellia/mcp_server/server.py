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


@mcp.tool()
def train_fraud_model(file_path: str, label_column: str, model_name: str,
                      positive_label: str | None = None,
                      algorithm: str = "gradient_boosting",
                      async_: bool = False) -> dict:
    """Train a fraud-risk model from a LABELLED spreadsheet (a column marking which
    rows were fraud). Returns an honest ModelCard: cross-validated precision/recall/
    F1/ROC-AUC, confusion matrix, top features — never training-set scores. Refuses
    with the reason when the label is missing/single-class, rows < 200, or a feature
    leaks the label. No labelled history? Use detect_anomalies instead. Training can
    be slow — pass async_=true and poll job_status for big files."""
    params = {"file": file_path, "label_column": label_column, "model_name": model_name,
              "positive_label": positive_label, "algorithm": algorithm}
    if async_:
        return _post("/jobs", {"op": "fraud_train", "params": params})
    return _post("/fraud/train", params)


@mcp.tool()
def score_fraud(file_path: str, model_name: str, threshold: float | None = None,
                async_: bool = False) -> dict:
    """Score a fresh spreadsheet with a trained fraud model. Each row gets a
    fraud_probability (0-1), a risk_band (low/medium/high/critical), and its top_factors
    — the features that pushed THIS row's score up, with values. These are RISK
    estimates, never verdicts; the ModelCard with its metrics is attached to every
    response. Refuses if the file's columns don't match what the model was trained on
    (the error lists the difference). List models with list_fraud_models."""
    params = {"file": file_path, "model_name": model_name, "threshold": threshold}
    if async_:
        return _post("/jobs", {"op": "fraud_score", "params": params})
    return _post("/fraud/score", params)


@mcp.tool()
def evaluate_fraud_model(file_path: str, label_column: str, model_name: str) -> dict:
    """The honesty check: score a LABELLED holdout file the model never saw and get
    real-world precision/recall/F1/confusion, side by side with the training-time CV
    metrics. A big drop means drift or overfitting — retrain on fresher data. Use this
    before trusting score_fraud output on production files."""
    return _post("/fraud/evaluate", {"file": file_path, "label_column": label_column,
                                     "model_name": model_name})


@mcp.tool()
def list_fraud_models() -> dict:
    """List every trained fraud model's ModelCard: metrics, class balance, features
    used/dropped, top importances, trained-at, schema fingerprint. Cards never contain
    the training data. Use this to pick a model_name for score_fraud, or to check
    whether a model exists before training a new one."""
    return _forward("GET", "/fraud/models")


@mcp.tool()
def save_reconciliation_profile(name: str, spec: dict) -> dict:
    """Save a reusable reconciliation profile for one-click monthly runs. Spec:
    {"keys": [match columns] (required), "tolerance": {numeric/days/fuzzy},
    "fuzzy_keys": 0-1 (opt-in typo-tolerant key matching), "pre_recipe_a"/"pre_recipe_b":
    clean-op steps run before matching, "dedupe_a"/"dedupe_b": {columns, keep|aggregate}}.
    Read it back as the resource profile://<name>; run it with run_reconciliation_profile."""
    return _post(f"/reconcile/profiles/{name}", {"spec": spec})


@mcp.tool()
def run_reconciliation_profile(file_a: str, file_b: str,
                               profile_name: str | None = None,
                               profile: dict | None = None,
                               write_report: bool = True,
                               out_path: str | None = None,
                               async_: bool = False) -> dict:
    """Run a full reconciliation: pre-cleaning, dedupe, tolerant matching, and a
    5-sheet xlsx report (Summary / Matched with L1-L3 levels / Only-in-A / Only-in-B /
    Discrepancies with diff_abs+diff_pct variance). Pass profile_name (saved) or a
    literal profile spec — exactly one. Match levels: L1 exact, L2 within tolerance,
    L3 fuzzy key. For big file pairs pass async_=true and poll job_status."""
    params = {"a": file_a, "b": file_b, "profile_name": profile_name,
              "profile": profile, "report": write_report, "out_path": out_path}
    if async_:
        return _post("/jobs", {"op": "reconcile_run", "params": params})
    return _post("/reconcile/run", params)


@mcp.tool()
def match_names(file_path: str, col_a: str | None = None, col_b: str | None = None,
                group_by: str | None = None, llm_verify: bool = False,
                seq_threshold: float = 50.0, async_: bool = False) -> dict:
    """KYC name matching, two modes: col_a+col_b compares declared vs registry name
    per row; col_a alone (optionally with group_by to bucket) cross-compares all name
    pairs. Every pair gets a deterministic 0-100 similarity; with llm_verify=true a
    local-LLM verdict (match/no_match + reason) is added on top — parse failures
    degrade to 'unverified', never crash. Too many pairs -> error telling you to add
    group_by. Rows are Excel rows (data starts at 2)."""
    params = {"file": file_path, "col_a": col_a, "col_b": col_b, "group_by": group_by,
              "llm_verify": llm_verify, "seq_threshold": seq_threshold}
    if async_:
        return _post("/jobs", {"op": "kyc_match_names", "params": params})
    return _post("/kyc/match_names", params)


@mcp.tool()
def dedupe_rows(file_path: str, columns: list[str], threshold: float = 85.0,
                strategy: str = "most_complete", out_path: str | None = None,
                async_: bool = False) -> dict:
    """Entity-level dedupe: cluster near-duplicate rows by similarity on the given
    columns (name + address style), keep one canonical row per cluster (strategy:
    most_complete | first | last), and write the deduped copy to a NEW file — the
    input is never modified. Returns the merge log with Excel row numbers. This
    RESOLVES duplicates; detect_anomalies only FLAGS them."""
    params = {"file": file_path, "columns": columns, "threshold": threshold,
              "strategy": strategy, "out_path": out_path}
    if async_:
        return _post("/jobs", {"op": "kyc_dedupe", "params": params})
    return _post("/kyc/dedupe", params)


@mcp.resource("profile://{name}")
def profile_resource(name: str) -> str:
    """A saved reconciliation profile spec as JSON."""
    import json

    return json.dumps(_forward("GET", f"/reconcile/profiles/{name}"), indent=2)


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
