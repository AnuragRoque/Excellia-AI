# Excellia — Build Plan

**Goal:** Refactor Excellia from a monolithic GUI application into a clean core engine exposed as an MCP server, so any AI agent — cloud or fully air-gapped — can drive spreadsheet validation without data leaving the machine.

**Owner:** Anurag
**Status:** Phases 1 & 2 complete (= Stage A in the master spec, done 2026-07-12, tagged `v0.2.0-stage-a`);
Phase 3 partially done (packaging/demo/README shipped; recordings + post pending — folded into Stage E)
**Target:** 3 focused weekends to public release of the v1 server

> **Master spec:** the complete product — full feature set (fraud analysis, KYC, reconciliation pro,
> web app, Excel add-in with `=XAI()` formulas + task pane, ask/transform), stage gates, API/MCP/tool
> placement, and live checkboxes — now lives in **`EXCELLIA_FEATURES.md`**. That file is the project's
> checkpoint/saved memory; this file remains the original thesis and the v1 shipping plan.
> Order of work is locked: **working MCP server + agent loop first (Stage A), features after.**

---

## 1. Context

### What exists today

Excellia AI is a working, monolithic Flask application:

- GUI for spreadsheet upload and preview
- Rule-based validation
- ML anomaly detection (Isolation Forest, scikit-learn)
- Local LLM chatbot via Ollama (Gemma3 / Phi3)
- Threaded job queues for large files
- Handles 100K+ row datasets
- Fully on-premise, zero cloud calls

**Problem:** All logic is trapped inside the GUI. It can only be reached by a human clicking buttons in Excellia's own interface. No other system — including AI agents — can use it.

### Related prior work to draw from

- **Limestone (TRPW)** — financial reconciliation, 200K+ row memory-optimised pipeline. Its reconciliation logic should be folded into the Excellia core.
- **KYC Data Automation Tool** — SequenceMatcher-based fuzzy deduplication. Its near-duplicate matching should inform anomaly detection.

### The strategic thesis

> Point it at Claude for convenience, or at your own Ollama for a fully air-gapped deployment. Your data never leaves either way — the only difference is where the reasoning happens.

The MCP ecosystem in 2026 is saturated with wrappers around cloud APIs (GitHub, Slack, Notion). It is thin on servers that do **real local computation**, and nearly empty on servers built for **regulated, air-gapped environments**. That intersection is the entire point of this project.

**This is not another tool. It is a component other systems depend on.**

---

## 2. Architecture

### Principle: one brain, many faces

Extract the logic once. Everything else is a thin caller.

```
                 Human doors                    AI door
            ┌──────────────────┐          ┌──────────────┐
            │  Web app (later) │          │  AI host     │
            │  Excel add-in    │          │  (brain)     │
            │  (much later)    │          └──────┬───────┘
            └────────┬─────────┘                 │
                     │ HTTP                ┌─────▼───────┐
                     │                     │ MCP client  │  (not ours)
                     │                     └─────┬───────┘
                     │                           │ MCP
                     │                     ┌─────▼───────┐
                     │                     │ MCP server  │  (thin, ~60 lines)
                     │                     └─────┬───────┘
                     │                           │ HTTP
              ┌──────▼───────────────────────────▼──────┐
              │        Core API (FastAPI)               │
              │        POST /profile /validate ...      │
              └──────────────────┬──────────────────────┘
                                 │
              ┌──────────────────▼──────────────────────┐
              │   Core engine (pure Python)             │
              │   + Ollama (local LLM)                  │
              └─────────────────────────────────────────┘
```

### The governing rule

> **Human clicks a button → direct HTTP (no MCP).**
> **AI decides on its own → MCP.**

The web app and Excel add-in are **not** MCP clients. They are ordinary HTTP clients hitting the core API directly. MCP exists solely as the door for AI callers, which cannot click buttons and must instead *discover* what tools exist.

### What we build vs. what we never build

| Component | Do we build it? |
|---|---|
| Core engine | **Yes** — the crown jewel |
| Core API (FastAPI) | **Yes** — the glue |
| MCP server | **Yes** — ~60 lines, thin adapter |
| Local offline agent | **Yes** — ~60 lines, proves the air-gapped story |
| MCP client | **No** — always belongs to the caller (Claude Desktop's, or the SDK's) |
| Web app | Later. Not in scope for v1. |
| Excel add-in | Much later. Not in scope for v1. |

### Critical design constraint: the MCP server must stay thin

The MCP server contains **zero** validation logic, zero pandas, zero Ollama. It only forwards to the core API and describes the tools.

> **If the MCP server ever gets fat, the architecture is wrong.**

Its smallness is the *evidence* the refactor succeeded. Logic lives in exactly one place; fix a bug in the core and the API, the MCP server, and every future face get the fix simultaneously.

---

## 3. Repository structure

```
excellia/
  core/                    # pure Python. no HTTP, no GUI, no file dialogs.
    __init__.py
    ingest.py              # load + profile
    validate.py            # rule engine
    anomaly.py             # Isolation Forest + outlier detection
    reconcile.py           # from Limestone
    llm.py                 # Ollama client (used by ask/transform later)
    models.py              # dataclasses: Issue, Profile, ReconcileResult
    rules/
      builtin.py           # GST, PAN, email, phone, IFSC regex etc.

  api/                     # FastAPI. thin. calls core.
    main.py
    schemas.py             # pydantic request/response models

  mcp_server/              # ~60 lines. calls api.
    server.py

  local_agent/             # ~60 lines. Ollama + mcp client. fully offline.
    agent.py

  tests/
  examples/
    messy_vendors.xlsx     # demo file with deliberate errors
  README.md
  pyproject.toml
```

**Rule:** `core/` must never import from `api/`, `mcp_server/`, or `local_agent/`. Dependencies point inward only.

---

## 4. The core engine — full capability spec

Six pillars. **v1 ships the first four.** `ask` and `transform` are deferred.

### 4.1 Ingest & profiling — `profile(file) -> Profile`

- Read xlsx, xlsm, csv, tsv
- Auto-detect delimiter, encoding, header row
- Handle multi-sheet workbooks (select sheet or process all)
- Type inference per column: number, date, currency, categorical, ID, free text
- Profile output: row/col counts, null rate per column, cardinality, min/max/mean, top values, detected format
- Chunked/streaming reads — must handle 200K+ rows without memory blowup (reuse Limestone's memory pipeline approach)

### 4.2 Rule-based validation — `validate(df, ruleset) -> list[Issue]`

Deterministic. No LLM. Fast. Explainable.

- Required-field checks
- Format validation via regex: GST, PAN, Aadhaar, email, phone, IFSC
- Range and bound checks
- Uniqueness / duplicate detection
- Referential checks (value must exist in a lookup list)
- Cross-column logic (`if status == "paid" then amount > 0`; `end_date >= start_date`)
- **Rule library**: named, savable, reusable rulesets shareable as templates ("KYC ruleset", "invoice ruleset")
- Custom rules via a simple expression language

Every `Issue` carries: `row`, `column`, `rule_name`, `severity`, `reason` (human-readable).

### 4.3 Anomaly detection — `detect_anomalies(df, sensitivity) -> list[Flag]`

Statistical. Catches what rules cannot.

- Isolation Forest for multivariate outliers (existing implementation)
- Per-column outlier detection (z-score / IQR for numerics)
- Rare-category flagging
- Near-duplicate row detection via similarity (port SequenceMatcher approach from the KYC tool)
- Pattern-break detection (a column that is always 10 digits suddenly has an 8-digit entry)

Every `Flag` carries a **confidence score** and a **"why flagged"** explanation. Never a black box.

### 4.4 Reconciliation — `reconcile(a, b, keys) -> ReconcileResult`

Port and generalise from Limestone.

- Match records across two sources by key columns
- **Tolerance**: date windows, amount rounding, fuzzy name matching
- Output four buckets: `matched`, `only_in_a`, `only_in_b`, `discrepancies` (matched but a field differs)
- Many-to-one and one-to-many handling
- Configurable match strategies

This is the highest-value enterprise capability.

### 4.5 AI chat over data — `ask(df, question) -> str` — **DEFERRED to v2**

Ollama-powered natural-language Q&A grounded in the dataframe.

**Critical:** the LLM must never invent numbers. It sees schema + samples + computed stats, and calls back into the engine for real aggregates.

### 4.6 AI-assisted transformation — `transform(df, instruction) -> df` — **DEFERRED to v2**

Plain-English column operations. The LLM **proposes** reviewable steps, shows a before/after preview on a sample, and only applies after human confirmation. **Never silent mutation.** Undo/redo stack.

### 4.7 Reporting & export

- Export cleaned data (xlsx/csv)
- Issues report, anomaly report, reconciliation report
- One-page data-quality summary (score, top issues, before/after)
- Export applied transformations as a reusable **recipe** so next month's file runs the same cleanup automatically

### What is explicitly NOT core

These belong to the faces, not the engine. Keeping them out is what makes the architecture clean.

- GUI / preview tables → web app
- File upload widgets, buttons → each face
- Job queues / threading → the API layer (core stays synchronous and pure)
- Auth, RBAC, sessions → the API layer
- Writing flags back into Excel cells → the Excel add-in

---

## 5. The core API (FastAPI)

Thin. Every endpoint calls exactly one core function and returns its result.

```
POST /profile        {file}                     -> Profile
POST /validate       {file, ruleset}            -> {issues: [...], summary}
POST /anomalies      {file, contamination}      -> {flags: [...]}
POST /reconcile      {a, b, keys, tolerance}    -> ReconcileResult
GET  /rulesets                                  -> list of saved rulesets
```

Add async job queue + progress only when file sizes demand it. Not in v1.

---

## 6. The MCP server

**Target: under 60 lines.** Uses FastMCP (bundled in the official Python SDK as `mcp.server.fastmcp`).

### Terminology, once and for all

- **MCP** = the protocol (JSON-RPC message format, `tools/list`, `tools/call`). A spec, not code.
- **FastMCP** = the Python library that implements it via decorators. Turns docstrings into tool descriptions and type hints into JSON schemas.

Same relationship as HTTP vs Flask. Learn MCP conceptually, build with FastMCP. Not a choice.

### The implementation

```python
# mcp_server/server.py
import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("excellia")
API = "http://localhost:8000"

@mcp.tool()
def profile_sheet(file_path: str) -> dict:
    """Get a data profile of a spreadsheet: row/column counts, types, null rates,
    and basic stats. Use this first to understand an unfamiliar file."""
    return requests.post(f"{API}/profile", json={"file": file_path}).json()

@mcp.tool()
def validate(file_path: str, ruleset: str = "default") -> dict:
    """Check a spreadsheet against validation rules (required fields, formats like
    GST/PAN/email, ranges, duplicates). Returns each violation with its row,
    column, and reason."""
    return requests.post(f"{API}/validate",
                         json={"file": file_path, "ruleset": ruleset}).json()

@mcp.tool()
def detect_anomalies(file_path: str, sensitivity: float = 0.05) -> dict:
    """Find statistically suspicious rows using Isolation Forest — outliers that
    break no explicit rule but don't fit the data's pattern. Returns flagged rows
    with confidence scores."""
    return requests.post(f"{API}/anomalies",
                         json={"file": file_path, "contamination": sensitivity}).json()

@mcp.tool()
def reconcile(file_a: str, file_b: str, key_columns: list[str]) -> dict:
    """Compare two spreadsheets and return matched records, records only in A,
    records only in B, and matched-but-differing records."""
    return requests.post(f"{API}/reconcile",
                         json={"a": file_a, "b": file_b, "keys": key_columns}).json()

if __name__ == "__main__":
    mcp.run()
```

### The craft is in the docstrings

The docstring is the **entire interface** the AI sees. It never reads the code.

```python
"""Validates a sheet."""                                    # bad
"""Check a spreadsheet against validation rules (required   # good
fields, formats like GST/PAN/email, ranges, duplicates).
Returns each violation with its row, column, and reason."""
```

The good one tells the model **when to reach for it** and **what it gets back**. A well-described mediocre tool gets used correctly; a badly-described brilliant tool gets ignored. This is prompt engineering applied to function documentation.

Also: return structured data with clear keys, one job per tool, and **instructive error messages** — the model reads those and will retry intelligently if told what went wrong.

### Transport

Use **stdio** (subprocess, local, zero config). Correct choice for on-prem. Claude Desktop literally launches `python server.py` as a subprocess and talks over stdin/stdout. No ports, no deployment, no cloud infrastructure.

---

## 7. The local agent (the air-gapped proof)

**Target: ~60 lines.** Ollama + the `mcp` client library. Zero network calls.

This exists to prove the thesis. Same MCP server, different brain:

| Host (brain) | Where the model runs | Offline? |
|---|---|---|
| Claude Desktop | Anthropic cloud | No |
| `local_agent/` + Ollama | This machine | **Yes** |
| Client's on-prem LLM | Their datacenter | **Yes** |

**Zero changes to `server.py` between them.** That is the entire point of the standard.

### The privacy nuance — state this honestly in the README

Using Claude Desktop:

- **Stays local:** the .xlsx file, every row, pandas processing, Isolation Forest, Ollama inference
- **Goes to Anthropic:** the prompt, the file *path*, and whatever the tool *returns* (e.g. `{"violations": 47, "rows": [4812], "reasons": ["invalid GST"]}`)

Findings can themselves be sensitive. So: Claude Desktop is right for **demos and portfolio**. `local_agent/` is right for **regulated production**. Ship both. Let the user choose the brain.

---

## 8. Phased plan

### Phase 1 — Extract the core (weekend 1)

- [x] Create `core/` package. Pure Python, zero Flask/HTTP/GUI imports.
- [x] Lift validation logic out of the existing Excellia GUI into `core/validate.py`
- [x] Lift Isolation Forest logic into `core/anomaly.py`
- [x] Lift ingest + profiling into `core/ingest.py`
- [x] Port Limestone's reconciliation into `core/reconcile.py` (implemented from the §4.4 spec — Limestone source not present on this machine)
- [x] Define dataclasses in `core/models.py`: `Issue`, `Flag`, `Profile`, `ReconcileResult`
- [x] Write tests against `examples/messy_vendors.xlsx` (60 tests passing; file regenerable via `examples/make_messy_vendors.py`)
- [x] **Nothing user-facing changes yet.** The logic is now free.

### Phase 2 — API + MCP server + local agent (weekend 2) — ✅ DONE 2026-07-12 (= Stage A)

- [x] `api/main.py` — FastAPI, six endpoints (`/health /profile /validate /anomalies /reconcile /rulesets`), each calling one core function
- [ ] Point the existing Excellia GUI at the API. Prove nothing broke. — *skipped deliberately: legacy GUI
      stays read-only reference; superseded by the Stage D web app in the master spec*
- [x] `mcp_server/server.py` — four tools, still thin (zero pandas); grew past 60 lines only for the
      Windows detached-API-spawn fix and instructive error text, not logic
- [~] Add to Claude Desktop config, restart, **watch it work** — config block written into README; chain
      proven via live stdio client (`tests/test_mcp_integration.py`); the GUI paste+restart is a manual user step
- [x] `local_agent/agent.py` — Ollama + mcp client, fully offline (verified live with `llama3.2:latest`)
- [x] Verify: same server, both brains, zero code changes between them (transcript in `docs/local_agent_demo.md`)

### Phase 3 — Ship it (weekend 3) — partially done; remainder folded into Stage E of the master spec

- [x] `pyproject.toml` → `pip install excellia`, entry point `excellia-mcp` (+ `excellia-api`, `excellia-agent`)
- [~] **Installs in under 60 seconds.** `pip install`, paste config block, restart. — *honest result: ~2.5 min
      from a bare venv (scientific-stack wheels dominate); seconds when pandas/sklearn already installed.
      README states the truthful timing.*
- [x] `examples/messy_vendors.xlsx` — a demo file with deliberate GST errors, duplicates, and outliers (+ regenerator script)
- [x] README with the thesis line as the first sentence
- [ ] **90-second screen recording**: Claude Desktop validating the messy spreadsheet and explaining what's wrong. Not a diagram. A screen recording. Highest-leverage artifact; takes an afternoon. *(→ Stage E)*
- [ ] One post: *"Why enterprise AI logic should be an MCP server, not an app"* — written as an architect who learned it across five platforms, not a student who read the spec. *(→ Stage E)*

### Later (do not build now)

- v2: `ask` and `transform` tools, saved rulesets as MCP *resources*, reports and recipes
- v3: web app (React + the same API)
- v4: Excel add-in (Office.js task pane, writes flags into real cells)

---

## 9. Scope discipline — what NOT to do

Three temptations, each of which kills the project:

**Do not build the Excel add-in first because it is flashy.** It is a *face*, not a component. Faces do not get depended on. Month three, after the core has users.

**Do not make it general.** "Works with any data source!" is noise. **Spreadsheets. Excel and CSV. That is it.** Specificity is what makes a tool trustworthy. "Validates spreadsheets, fully offline" is a sentence someone can act on.

**Do not wait for perfection.** Ship at four tools: `profile`, `validate`, `detect_anomalies`, `reconcile`. Skip `ask` and `transform` — the LLM ones are the riskiest and least differentiated. Add them when someone asks.

Also rejected:
- Building a general AI agent framework (two hundred exist; no advantage)
- Building a big platform with auth and multi-tenancy (nobody stars a platform)
- Building six shallow MCP servers, one per project (**one deep server reads as a specialist; six shallow ones read as scattered**)

---

## 10. Definition of success

Not stars. **Someone else's agent imports this server.**

A finance team's AI assistant calls `reconcile` because they cannot send transactions to a cloud API. One real dependent user is worth more than a thousand stars.

Three requirements to get there:

1. Installs in under 60 seconds
2. A 90-second video showing it working in Claude Desktop
3. One post explaining *why*, not *how*

### The downside case

If nobody uses it, three weekends were still spent refactoring a monolith into a clean core with an interface layer — the exact skill senior interviews probe for. **The floor is becoming a better architect.** That is an unusually good floor.

---

## 11. Cross-cutting requirements

- **Privacy-first / fully on-prem.** Nothing leaves the machine from the core or API.
- **Deterministic-first.** Rules and math do the work. The LLM only assists and explains — it never silently decides.
- **Explainability everywhere.** Every flag carries a reason. No black boxes.
- **Audit trail** of every check and transformation.
- **Scale:** 200K+ rows without choking.

---

## 12. The one sentence

> Build one deep, boring, air-gapped MCP server that does spreadsheet validation with a local model, ship it so a stranger can install it in a minute, and record yourself using it in Claude Desktop.

Everything else — web app, extension, the other five projects — comes after, or never, and it will not matter.
