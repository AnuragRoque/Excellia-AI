# Excellia

![License: MIT](https://img.shields.io/badge/License-MIT-informational)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-240%20passing-brightgreen)
![Privacy](https://img.shields.io/badge/privacy-air--gapped-success)
![Status](https://img.shields.io/badge/stages%20A–D-done-blueviolet)
![Version](https://img.shields.io/badge/version-0.6.0-lightgrey)

**Air-gapped spreadsheet intelligence.** Profile, validate, anomaly-check, reconcile, transform,
fraud-score, and KYC-match Excel/CSV files — with AI assistance — while **not a single row leaves
your machine**.

> **One engine, six doors.** A pure-Python core does the work; a FastAPI server, an MCP server, a
> web app, an Excel add-in (`=XAI.*` formulas + a chatbot pane), and an offline Ollama agent are
> just faces on it. This is multi-tool software: pick the door that fits your workflow.

**Contents:** [Products](#the-products-in-this-repo) · [Install](#install) ·
[Pick your door](#pick-your-door) · [Screenshots](#screenshots) · [Tools](#nineteen-tools) ·
[Privacy](#privacy--the-honest-version) · [Layout](#repository-layout) · [Status](#status)

One core engine (pure Python), many doors: point **Claude Desktop** at it for convenience, or a
fully offline **Ollama** agent for regulated environments — the same server, zero code changes,
the only difference is where the reasoning happens. Humans get a **web app** and an **Excel
add-in** with `=XAI.*` formulas; agents get a thin **MCP server** with 19 tools.

```
            HUMAN DOORS                                  AI DOORS
 ┌─────────────────┐ ┌───────────────┐      ┌──────────────┐ ┌───────────────────┐
 │  Excel add-in   │ │    Web app    │      │Claude Desktop│ │ excellia-agent    │
 │  =XAI.* + pane  │ │  big & bulk   │      │ (cloud brain)│ │ (Ollama, offline) │
 └────────┬────────┘ └───────┬───────┘      └──────┬───────┘ └────────┬──────────┘
          │ HTTPS            │ HTTP                │ MCP (stdio)      │ MCP (stdio)
          └──────────┬───────┘               ┌─────▼──────────────────▼─────┐
                     │                       │   MCP server — thin, 0 logic │
                     ▼                       └──────────────┬───────────────┘
        ┌────────────────────────────────────────────────── ▼ ─────┐
        │            CORE API — FastAPI (jobs · uploads · CRUD)    │
        ├──────────────────────────────────────────────────────────┤
        │            CORE ENGINE — pure Python + pandas + sklearn  │
        │  ingest · validate · anomaly · reconcile · clean · ask   │
        │  transform · fraud · kyc · report  (+ the one LLM door)  │
        └──────────────────────────────────────────────────────────┘
```

**The governing rule:** deterministic code does the work; the LLM only assists, explains, and
proposes — it never silently decides and never invents numbers. Every answer from `ask` carries
the evidence rows and the query plan that actually ran.

---

## The products in this repo

| Product | What it is | Guide |
|---|---|---|
| **Core engine** | All the logic, pure Python — profiling, validation, anomalies, reconciliation, fraud ML, KYC matching, cleaning recipes, reports | [excellia/core/README.md](excellia/core/README.md) |
| **Core API** | FastAPI HTTP server — the single door to the engine; job queue for big files, uploads, saved-config CRUD | [excellia/api/README.md](excellia/api/README.md) |
| **MCP server** | Thin stdio server (19 tools + resources) so any AI agent — Claude Desktop, Claude Code, Cursor, or your own — can drive the engine | [excellia/mcp_server/README.md](excellia/mcp_server/README.md) |
| **Web app** | Point-and-click UI at `http://127.0.0.1:8000/app/` — quality checks, chat with evidence, transforms, reconciliation, fraud, KYC, bulk runs | [excellia/webapp/README.md](excellia/webapp/README.md) |
| **Excel add-in** | `=XAI.*` formula family + task-pane copilot inside Excel, Windows and Mac, no Node | [excellia/addin/README.md](excellia/addin/README.md) |
| **Offline agent** | Our own air-gapped MCP host: a local Ollama model drives the same server, zero bytes leave the machine | [excellia/local_agent/README.md](excellia/local_agent/README.md) |

## Install

```bash
git clone <this repo> && cd excellia_codebase
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -e .[dev]
pytest                     # should pass, fast, no network needed
```

(PyPI `pip install excellia` is planned; from source is the way today.) A bare venv takes a
couple of minutes because of the pandas/scikit-learn wheels; with scientific Python already
present it resolves in seconds. Demo file with seeded errors: `examples/messy_vendors.xlsx`.

## Pick your door

### 1 · Claude Desktop (cloud brain, local data)

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config) — use the **absolute
path** to the entry point inside your venv — then fully restart Claude Desktop (quit from the
system tray):

```json
{
  "mcpServers": {
    "excellia": { "command": "C:\\path\\to\\excellia_codebase\\.venv\\Scripts\\excellia-mcp.exe" }
  }
}
```

Try: *"Profile examples/messy_vendors.xlsx and tell me what's wrong with it."* (absolute path).
The MCP server auto-starts the core API when the first tool call needs it.

### 2 · Fully offline (regulated / air-gapped)

Needs [Ollama](https://ollama.com) with a tool-capable model (`ollama pull qwen2.5:7b`):

```bash
excellia-agent                                # interactive REPL
excellia-agent check examples/messy_vendors.xlsx   # one-shot
```

Same MCP server as door 1, zero code changes between the two brains. That is the point.

### 3 · The web app (no AI host needed)

```bash
excellia-api        # then open http://127.0.0.1:8000/app/
```

Drag-drop a file and use the views: Quality · Ask (chat with evidence) · Transform · Reconcile ·
Fraud · KYC · Bulk · Jobs & History — plus a **sidebar chat** available from every view. Flip
**Big file mode** for 100K+ row files: heavy work runs as background jobs so the page never freezes.

### 4 · Inside Excel — the `=XAI.*` formulas (Windows and Mac)

```bash
pip install -e .[addin]
excellia-addin      # HTTPS server + certificate + printed sideload steps
```

Then, in any cell: `=XAI.VALIDATE(C2:C99,"pan")` (deterministic, zero AI) · `=XAI.MATCH(A2,B2)` ·
`=XAI.RUN(A2:A99,"extract pin")` · `=XAI.TAG(B2:B99,"corporate?")` ·
`=XAI.SPLIT(A2,"street|city|pin")` (spills) · `=XAI.ASK("total per city?",A1:D99)`.
Formulas batch and cache — recalcs and even workbook reopen never re-run the LLM on unchanged
cells. The task pane validates / transforms / matches / chats over the selection, writing only
to empty adjacent columns.

### 5 · Raw HTTP API (scripts, curl, your own client)

```bash
excellia-api        # interactive docs at http://127.0.0.1:8000/docs
```

### 6 · Any other MCP host

Cursor, Windsurf, VS Code, Claude Code (`claude mcp add excellia <path to excellia-mcp>`), or a
raw stdio client: configure a **stdio** server whose command is the `excellia-mcp` entry point.
No args, no ports.

**Every door with exact commands and troubleshooting:** [docs/RUNNING.md](docs/RUNNING.md) ·
per-server runner's guide: [README_RUNNER.md](README_RUNNER.md).

## Nineteen tools

| Tool | What it does |
|---|---|
| `profile_sheet` | Row/column counts, inferred types, null rates, stats, auto-detected formats |
| `validate` | Deterministic rule checks: required fields, GST/PAN/Aadhaar/email/phone/IFSC formats, ranges, duplicates, mixed types. Rulesets: `default`, `kyc`, `invoice`, `payroll`, `bank-statement`, plus your own saved ones |
| `detect_anomalies` | Isolation Forest + column outliers + rare categories + near-duplicates + pattern breaks — every flag has a confidence and a reason |
| `reconcile` | Match two spreadsheets by key columns; tolerances for amounts, date windows, fuzzy names; four buckets incl. field-level discrepancies |
| `ask_data` | Chat with your data, hallucination-proof: the LLM plans a query, pandas computes it, and the evidence table always comes back with the answer |
| `transform_preview` | Instruction → cleaning recipe + before/after on a 20-row sample. Nothing changes yet |
| `transform_apply` | Apply a recipe to a NEW file (originals are never touched); new values land in `_ai`-suffixed columns unless you say replace |
| `run_recipe` | Replay a saved cleanup on next month's file in one call |
| `save_ruleset` | Persist a custom validation ruleset (also readable as the `ruleset://` MCP resource) |
| `export_report` | Highlighted xlsx report + Data Health Score with its full deduction breakdown |
| `job_status` | Poll long-running work started with `async_=true` (big files run on a job queue) |
| `train_fraud_model` | Labelled history → risk model with an honest ModelCard (CV metrics, leakage detection, refusals that name the fix) |
| `score_fraud` | Fresh file → per-row fraud probability, risk band, and the top factors pushing each score up |
| `evaluate_fraud_model` | Labelled holdout → real-world accuracy next to the training metrics |
| `list_fraud_models` | Every saved ModelCard (metrics and features — never your data) |
| `save_reconciliation_profile` / `run_reconciliation_profile` | One-click monthly reconciliation: pre-cleaning, dedupe, tolerant matching with L1/L2/L3 levels, variance, 5-sheet xlsx report |
| `match_names` | KYC hybrid name matching — deterministic similarity, optional offline-LLM verdicts |
| `dedupe_rows` | Entity resolution: cluster near-duplicates, keep a canonical row, log every merge |

`ask_data`, the transform tools, and `match_names` with `llm_verify` need a local
[Ollama](https://ollama.com); everything else is pure deterministic code. Row numbers everywhere
are Excel rows: header is row 1, data starts at row 2. Big files stream in chunks — a 500K-row
file runs profile → validate → transform → report through the job queue without a freeze. Saved
rulesets, recipes, profiles, models, and the append-only audit trail live in `~/.excellia/`
(override with `EXCELLIA_HOME`).

## Privacy — the honest version

| | File contents | Computation | What the AI host sees |
|---|---|---|---|
| **Claude Desktop / Code** | stay local | stays local | your prompt, the file *path*, and tool *results* (counts, flagged rows, reasons) |
| **`excellia-agent` + Ollama** | stay local | stays local | nothing leaves the machine — the model is local too |
| **Web app / add-in / raw API** | stay local | stays local | no AI host involved (LLM features use local Ollama) |

Tool results can themselves be sensitive — for regulated production, use the offline agent.
Full threat model: [SECURITY.md](SECURITY.md).

## Repository layout

```
excellia/
  core/         the engine — all logic, pure Python (imports nothing outward)
  api/          FastAPI server — jobs, uploads, CRUD; every endpoint = one core call
  mcp_server/   thin MCP server — 19 tools, zero pandas, forwards to the API
  webapp/       static SPA served by the API at /app — zero logic, no build step
  addin/        Excel add-in — Office.js manifest, =XAI.* functions, task pane, HTTPS server
  local_agent/  offline Ollama agent — our own MCP host, the privacy proof
examples/       demo data with seeded errors + regenerator
tests/          the whole suite (fast, offline; two opt-in live/big tests)
docs/           RUNNING.md · recording scripts · the architecture post · agent demo transcript
```

## Development

```bash
pip install -e .[dev]
pytest                                  # fast, no network, no Ollama needed
EXCELLIA_RUN_MCP_IT=1 pytest            # + live MCP stdio round-trip
EXCELLIA_BIG=1 pytest                   # + 500K-row memory-budget test (~90s)
```

Contributions: [CONTRIBUTING.md](CONTRIBUTING.md) · changes: [CHANGELOG.md](CHANGELOG.md) ·
the full staged build plan and status board: [EXCELLIA_FEATURES.md](EXCELLIA_FEATURES.md) ·
the original thesis: [EXCELLIA_MCP_PLAN.md](EXCELLIA_MCP_PLAN.md) · why the whole thing is an
MCP server and not an app: [docs/architecture_post.md](docs/architecture_post.md).

## Status

Stages A (working MCP loop), B (ask/transform/recipes/reports/jobs/big files), C (fraud,
reconciliation pro, KYC), and D (web app + Excel add-in, both full-featured) are **done** —
verified live including a 500K-row run through the background-job path. Remaining before 1.0:
the two inherently manual demos (Excel sideload on a real machine, Claude Desktop paste-and-
restart), the screen recordings, and the PyPI release. Deliberately unbuilt (scope discipline):
OCR, cloud LLMs, auth/multi-tenant — see §7 of [EXCELLIA_FEATURES.md](EXCELLIA_FEATURES.md).

## License

MIT © Anurag Singh
