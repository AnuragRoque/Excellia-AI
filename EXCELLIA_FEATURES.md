# Excellia — Complete Feature Specification & Master Checkpoint

> **This file is the saved memory of the project.** If a future session (or a future AI) gets ONLY this
> file, it must be able to continue building without asking what Excellia is, what exists, what is next,
> or where any feature belongs. Update the checkboxes here as work lands. The companion file
> `EXCELLIA_MCP_PLAN.md` holds the original thesis and Phase 1–3 shipping plan; this file goes further —
> it is the **full product**, staged so the boring working skeleton always ships before the exciting features.

**Owner:** Anurag Singh
**Repo:** `11 Excellia Core/excellia_codebase`
**Legacy source (read-only reference):** `../05 Excellia AI/Excellia-AI-Demo` (Flask monolith: `routes.py`, `routes2.py`)
**Concept docs (the requirements this file absorbs):** `project concept/` — add-in concept, KYC spec, Limestone spec, Excellia demo knowledge
**Last updated:** 2026-07-19 — evening pass: **Stage E writing deliverables DONE** (rewritten
GitHub-ready README with per-product doors, six per-component READMEs, `SECURITY.md` threat
model, `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE` (MIT), both recording scripts in
`docs/recording_script.md`, architecture post draft in `docs/architecture_post.md`) plus a new
web-app **sidebar chat** (the Ask thread, shared, reachable from every view — still one
`POST /ask` per message). Left: the manual demos (sideload + Claude Desktop paste), recording
the two videos (scripts ready, owner records), PyPI publish, and the git commit (owner said
don't commit yet). Earlier same day: (ALL Gate D automation teeth closed in two passes. Pass 1:
**async-job wiring** ("Big file mode" toggle → every heavy POST via `POST /jobs` + polling,
live status line), **formula cache persistence** (`OfficeRuntime.storage`, survives reopen),
**pane chat** (`/values/ask` + evidence), `README_RUNNER.md`, and a face restyle to the owner's
reference palette (near-black, pink→periwinkle gradient, serif numerals; Ask view rebuilt as a
chat thread — still one `POST /ask` per message). Pass 2: **web-app bulk mode** (N files × one
op → one job each, live matrix), **pane categorise/summarise** (`/values/map`), a **live
500K-row run** through the job path (profile 3s · validate 5s · transform 4.3s · report 216s),
and an instructive-errors fix in `transform.py` (flat recipe steps / bad param names now name
the step instead of leaking TypeError). 240 tests passing. Gate D now open ONLY on the manual
Excel sideload; deferred: keywords/simplify-JSON pane ops, abort button, formula cancellation.
See §3 D1/D2.)

---

## 0. The one paragraph

Excellia is a **privacy-first, air-gapped spreadsheet intelligence engine**. One core engine (pure
Python) does profiling, validation, anomaly detection, reconciliation, fraud scoring, KYC matching, and
AI-assisted transformation — all on-machine, nothing leaves. Around that one brain we hang many faces:
a **FastAPI core API**, a **thin MCP server** (so any AI agent — Claude Desktop or a fully offline
Ollama agent — can drive it), a **web app** for big/bulk files, and an **Excel add-in** with two modes
(a `=XAI()` formula family and a task-pane copilot). Deterministic code does the work; the LLM only
assists, explains, and proposes — it never silently decides and never invents numbers.

---

## 1. STATUS BOARD — what is DONE, what is NEXT, what is LEFT

### ✅ DONE — Phase 1 core + Stage A working loop (72 tests + live MCP demo, 2026-07-12)

- [x] **Core engine extracted** from the Flask monolith into `excellia/core/` — pure Python, zero
      HTTP/GUI imports (enforced by `tests/test_imports.py`)
  - [x] `ingest.py` — robust load (encodings, delimiter sniffing, fake-parse rejection) + full profiler
        (type inference: number/date/currency/id/categorical/text; null rates; cardinality; stats;
        auto-detection of GST/PAN/Aadhaar/email/phone/IFSC formats)
  - [x] `validate.py` — declarative ruleset engine (`default`, `kyc`, `invoice`) + auto-inferred checks
        (dominant-format violations, duplicate IDs/rows, missing values, mixed types); expression rules
        via `df.eval`
  - [x] `anomaly.py` — Isolation Forest with per-feature explanations, IQR column outliers,
        rare categories, SequenceMatcher near-duplicates (sorted-neighbour O(n·k)), pattern breaks
  - [x] `reconcile.py` — four buckets (matched / only_in_a / only_in_b / discrepancies) with
        numeric / date-window / fuzzy tolerances, one-to-many handling
  - [x] `models.py` — `Issue`, `Flag`, `Profile`, `ColumnProfile`, `ReconcileResult` dataclasses
  - [x] `rules/builtin.py` — GST/PAN/Aadhaar/email/phone/IFSC compiled regexes
- [x] **Core API** (`excellia/api/`) — `/health /profile /validate /anomalies /reconcile /rulesets`,
      all smoke-tested end to end
- [x] **MCP server** (`excellia/mcp_server/server.py`) — 4 tools, ~60 lines, thin (zero pandas/logic)
- [x] **Packaging** — `pyproject.toml` with entry points `excellia-mcp`, `excellia-api`
- [x] **Demo data** — `examples/messy_vendors.xlsx` (50 rows, seeded errors) + regenerator script
- [x] **Tests** — 72 passing + 1 opt-in live MCP integration test (`tests/`)

**Convention already locked in:** `Issue.row` / `Flag.row` are **Excel row numbers** (header = 1,
first data row = 2). Keep this everywhere a row is reported, in every layer, forever.

### ✅ Stage A — WORKING (the MCP loop breathes end to end) — DONE 2026-07-12, tagged `v0.2.0-stage-a`

- [x] A1. Initial git commit + tag `v0.1.0-core` (was zero commits)
- [~] A2. Claude Desktop: config block written in README + `docs/local_agent_demo.md`; MCP chain
       proven working via a live stdio client (`tests/test_mcp_integration.py`, opt-in). **Manual
       step left for the user:** paste the block into `claude_desktop_config.json` and restart —
       can't be automated from here (GUI app).
- [x] A3. `local_agent/agent.py` — Ollama + MCP stdio client, offline REPL + one-shot; entry point
       `excellia-agent`. Verified live with `llama3.2:latest`.
- [x] A4. Thesis proven: same unchanged `server.py` driven by (a) the offline Ollama agent and
       (b) a raw MCP stdio client (stands in for any host incl. Claude Desktop). Transcript in
       `docs/local_agent_demo.md`.
- [x] A5. Instructive errors through every layer + a robustness win: null-sentinel strings
       (`"null"`/`"none"`/`""`) that local models pass for optional params are coerced to real
       `None` at the API boundary. Error strings asserted in `tests/test_api_errors.py`.
- [~] A6. One-command install verified in a clean venv; all three entry points
       (`excellia-mcp/api/agent`) work. **Honest timing:** ~2.5 min from a bare venv because the
       pandas/scipy/scikit-learn wheels dominate — the literal "under 60s from scratch" target does
       NOT hold. For the realistic user (scientific Python already installed) it's seconds. README
       claim corrected to match reality.

**Hard-won fix (don't regress):** on Windows the MCP server must spawn the core API **detached**
(`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`, stdin/stdout to DEVNULL).
Spawned inline as a grandchild inheriting the host's JSON-RPC stdio pipes, uvicorn silently fails
to finish binding and every tool call hangs. `tests/test_mcp_integration.py` guards this.

### ✅ Stage B — USEFUL — DONE 2026-07-17 (172 tests; detail + honest caveats in §3)

- [x] `core/store.py` — workspace (`EXCELLIA_HOME` / `~/.excellia`), rulesets/recipes/profiles CRUD,
      append-only `history.jsonl` through the single `record()` writer, file fingerprints (never data)
- [x] `core/llm.py` — the only LLM door: stdlib-urllib Ollama client (core purity kept), model pick
      (`EXCELLIA_MODEL` → preferred families), retry-once, strict-JSON contract with one repair
      reprompt + typed `parse_failed` fallback; fully fake-transport tested
- [x] `core/clean.py` — 16 deterministic recipe atoms (trim/case/replace/split/concat/slice/math/
      currency/dates/structure/dedupe-with-aggregate/fill-down) behind an op registry
- [x] `core/ask.py` — plan-whitelist chat: LLM plans strict-JSON, pandas executes, answer + evidence
      table + plan returned; refusal path; adversarial escape tests; **live offline smoke passed**
- [x] `core/transform.py` — preview→confirm→apply; `_ai`-suffix non-destructive default; threaded
      `llm_map` with per-distinct-value dedup; recipes saved + replayed deterministically
- [x] `core/report.py` — highlighted xlsx (legacy priority order) + Data Health Score with breakdown
- [x] Big files — `ingest.iter_chunks` (openpyxl read-only / chunked csv), `profile_large`,
      `validate_large` (cross-chunk unique/dup tracking); opt-in 500K-row test passes in ~85s
- [x] API v2 — `/ask /clean /transform/preview /transform/apply /report`, rulesets+recipes CRUD,
      `/history`, job queue (`POST /jobs`, `GET /jobs[/{id}]`, results parked in workspace)
- [x] MCP v2 — 11 tools (+ `ask_data transform_preview transform_apply run_recipe save_ruleset
      export_report job_status`), resources `ruleset://` `recipe://`, `async_=True` job handoff;
      server still imports zero pandas
- [x] Starter ruleset packs: `kyc`, `invoice`, `payroll`, `bank-statement`

### ✅ Stage C — DOMAIN SUITES — DONE 2026-07-17 (218 tests; detail + gate in §3)

- [x] `core/fraud.py` — `train/score/evaluate/list_models`: sklearn pipeline (GradientBoosting
      default, RandomForest option), manual stratified 5-fold CV with class-imbalance sample
      weights, ModelCards saved beside `.joblib` (metrics/features/schema fingerprint — never data),
      leakage detector (numeric corr ≈1 + categorical perfect-encoding, named in the refusal),
      per-row `top_factors` via occlusion against training baselines, risk bands, drift refusal
- [x] `core/reconcile.py` grown — `match_level` L1/L2/L3 on every match, `diff_abs`/`diff_pct`
      variance, opt-in `fuzzy_keys` second pass, `run_profile` (pre-recipes + dedupe-with-aggregate
      per source → match → summary with match_rate/levels/variance totals)
- [x] `core/kyc.py` — `name_similarity`, `match_names` (pairwise or group_by cross-compare, nC2
      guard, opt-in offline-LLM verdicts degrading to `unverified` on parse failure), entity
      `dedupe` (union-find clusters over sorted-neighbour similarity, canonical row by strategy)
- [x] `core/store.py` grown — `save_model/load_model/model_cards` (joblib + meta.json)
- [x] `report.reconciliation_report` — the 5-sheet xlsx (Summary/Matched/Only-in-A/Only-in-B/
      Discrepancies with side-by-side variance)
- [x] API — `/fraud/train|score|evaluate|models`, `/reconcile/profiles` CRUD + `/reconcile/run`,
      `/kyc/match_names`, `/kyc/dedupe`; all five heavy ops also registered as job-queue ops
- [x] MCP — 8 new tools (19 total) + `profile://` resource; server still zero pandas
- [ ] OCR (`excellia[ocr]`, Tesseract-only) — deliberately deferred, stays optional-later

### ⏭ NEXT — finish Stage D's gate, then E

- [~] Stage D — FACES: **D1 web app v1 ✅** (static SPA at `/app`, 7 views, upload door) and
       **D2 add-in v1 ✅** (`=XAI.*` formulas + lean task pane over HTTPS, Windows + Mac, no Node).
       **2026-07-19: async-job wiring ✅ (Big file mode) · formula cache persistence ✅
       (OfficeRuntime.storage) · pane chat ✅ (`/values/ask` + evidence) · web-app bulk mode ✅ ·
       pane categorise/summarise ✅ · 500K-row live run through the job path ✅ (timings in §3).**
       Gate D now open ONLY on the manual step: sideload into real Excel (Windows + Mac) and
       paste the Claude Desktop config. Detail in §3.
- [ ] Stage E — SHIP: polish, video, README, post, PyPI

---

## 2. Architecture — one brain, many faces (the placement math)

```
            HUMAN DOORS                                  AI DOORS
 ┌─────────────────┐ ┌─────────────────┐      ┌──────────────┐ ┌───────────────────┐
 │  Excel add-in   │ │    Web app      │      │Claude Desktop│ │ local_agent (ours)│
 │ ┌─────────────┐ │ │  (React/vanilla)│      │ (cloud brain)│ │ (Ollama brain,    │
 │ │ =XAI() fns  │ │ │  big & bulk     │      └──────┬───────┘ │  fully offline)   │
 │ │ task pane   │ │ │  files          │             │MCP      └────────┬──────────┘
 │ └─────────────┘ │ └────────┬────────┘      ┌──────▼───────┐          │MCP
 └────────┬────────┘          │               │  MCP server  │◄─────────┘
          │ HTTPS (local      │ HTTP          │ (thin, ours) │
          │ add-in proxy)     │               └──────┬───────┘
          └───────────┬───────┘                      │ HTTP (localhost only)
                      ▼                              ▼
        ┌─────────────────────────────────────────────────────────┐
        │                CORE API — FastAPI                       │
        │  sync endpoints + background JOB QUEUE + workspace      │
        └────────────────────────────┬────────────────────────────┘
                                     ▼
        ┌─────────────────────────────────────────────────────────┐
        │              CORE ENGINE — pure Python                  │
        │ ingest · validate · anomaly · reconcile · clean · ask   │
        │ transform · fraud · kyc · recipes · report              │
        │        + llm.py (Ollama client, the ONLY LLM door)      │
        └────────────────────────────┬────────────────────────────┘
                                     ▼
                      ┌──────────────────────────┐
                      │ ~/.excellia/  workspace   │
                      │ rulesets/ recipes/        │
                      │ profiles/ models/ cache/  │
                      │ history.jsonl             │
                      └──────────────────────────┘
```

### 2.1 The five components (the ones we talked about) — and who owns what

| Component | Build it? | What it is in this repo |
|---|---|---|
| **Core Engine** | **Yes — the crown jewel** | `excellia/core/` — all logic, pure Python, imports nothing outward |
| **Core API** | **Yes — the glue** | `excellia/api/` — FastAPI; owns jobs, sessions, file handling; every endpoint calls exactly one core function |
| **MCP Server** | **Yes — thin forever** | `excellia/mcp_server/` — describes tools, forwards to API. If it grows logic, the architecture failed |
| **MCP Client** | **No (as a product)** | Claude Desktop ships its own. Our `local_agent` *embeds* the `mcp` Python client library — that's the only MCP-client code we write, and it lives inside the agent |
| **Local offline AI agent/host** | **Yes — the proof** | `excellia/local_agent/` — Ollama picks tools, MCP client calls our server, zero network |

### 2.2 The governing rules (never violate)

1. **Human clicks a button → direct HTTP to the core API. AI decides on its own → MCP.**
   The web app and Excel add-in are ordinary HTTP clients. They never speak MCP.
2. **`core/` never imports from `api/`, `mcp_server/`, `local_agent/`** (test-enforced). Dependencies point inward.
3. **Privacy:** no code path may leave the machine. The only network sockets are localhost (API, Ollama,
   add-in proxy). Cloud OCR / cloud LLMs are opt-in plugins, never defaults, and never silent.
4. **Deterministic-first:** if regex/pandas/sklearn can do it, the LLM must not. The LLM proposes,
   explains, and formats — deterministic code executes and counts.
5. **Explainability:** every Issue/Flag/score/match carries a human-readable `reason`. No black boxes.
6. **Non-destructive:** nothing overwrites user data without an explicit confirm step. Excel add-in
   writes to adjacent columns; `transform` requires preview→confirm; every apply is undoable/exportable.
7. **Row convention:** Excel row numbers everywhere (header = 1, data starts at 2).
8. **One job per MCP tool, docstrings are the interface** — write them for the model, not for humans.

### 2.3 Feature → layer placement table (the "where does it live" math)

| Feature (user's words) | Core module | API | MCP tool(s) | Face(s) |
|---|---|---|---|---|
| Profile a sheet | `ingest.py` ✅ | `POST /profile` ✅ | `profile_sheet` ✅ | all |
| Rule validation | `validate.py` ✅ | `POST /validate` ✅ | `validate` ✅ | all |
| Anomaly detection | `anomaly.py` ✅ | `POST /anomalies` ✅ | `detect_anomalies` ✅ | all |
| Reconciliation (basic) | `reconcile.py` ✅ | `POST /reconcile` ✅ | `reconcile` ✅ | all |
| **AI chat over data** | `ask.py` + `llm.py` ✅ | `POST /ask` ✅ | `ask_data` ✅ | task pane chat, web app chat, any MCP host |
| **AI transform (2 modes: bulk + formula)** | `transform.py` + `clean.py` + `llm.py` ✅ | `POST /transform/preview`, `/transform/apply`, `POST /clean` ✅ | `transform_preview`, `transform_apply` ✅ | add-in task pane (bulk), `=XAI()` (per-cell), web app |
| **Fraud analysis (train on labelled data, then score)** | `fraud.py` ✅ | `/fraud/train /fraud/score /fraud/models /fraud/evaluate` ✅ | `train_fraud_model`, `score_fraud`, `evaluate_fraud_model`, `list_fraud_models` ✅ | web app wizard, MCP ✅ |
| **Financial reconciliation (pro: profiles, cleaning, levels, reports)** | `reconcile.py` ✅ + `clean.py` + `report.py` ✅ | `/reconcile/profiles` CRUD + `/reconcile/run` ✅ | `run_reconciliation_profile`, `save_reconciliation_profile` ✅ | web app, MCP ✅ |
| **KYC analysis (name match, dedupe, ID checks, OCR later)** | `kyc.py` ✅ (+ `ocr.py` optional extra, unbuilt) | `/kyc/match_names /kyc/dedupe` ✅ | `match_names`, `dedupe_rows` ✅ | web app, add-in `=XAI.MATCH`, MCP ✅ |
| Deterministic cleaning formulas (Limestone library) | `clean.py` ✅ | `POST /clean` ✅ | (used via transform) | web app, task pane |
| Saved rulesets / recipes / profiles / models | `store.py` ✅ (profiles/models: Stage C) | CRUD endpoints ✅ (rulesets, recipes) | MCP **resources** ✅ + `save_ruleset` ✅ | all |
| Big-file & bulk processing | chunking in `ingest.py` ✅ | **job queue** in API ✅ | `async_=True` variants + `job_status` ✅ | web app primarily |
| Reports & exports (highlighted xlsx, health score) | `report.py` ✅ | `POST /report` ✅ | `export_report` ✅ | all |
| Excel add-in `=XAI(...)` formula | — (face) | consumes `/transform`, `/ask`, `/kyc`, `/validate` | — | Excel custom functions |
| Excel add-in task pane | — (face) | consumes API + jobs | — | Excel task pane |
| Web app | — (face) | consumes everything | — | browser |

**Rule of thumb encoded above:** anything that *computes* lives in `core/`. Anything that *waits, queues,
stores, or authenticates* lives in `api/`. Anything that *describes tools to a model* lives in
`mcp_server/`. Anything that *renders pixels* is a face. When unsure: if it needs pandas → core; if it
needs a socket → api; if it needs a docstring an LLM will read → mcp_server; if it needs a human eye → face.

---

## 3. Stage gates — the order of work and the definition of "done" for each

> **The iron rule you set: FIRST a working MCP server/client/agent loop, THEN the feature buildout.**
> A stage is not started until the previous stage's gate is fully checked. No skipping because a
> feature is exciting. Excitement is how monoliths happen.

### Stage A — WORKING (the skeleton breathes) — ✅ DONE 2026-07-12 (detail in §1)

Goal: a stranger (or you on a fresh machine) can `pip install`, paste one config block, restart
Claude Desktop, and watch a real validation happen. And the same server drives from offline Ollama.

- [x] A1. **Git baseline.** `git add -A && git commit` (repo has zero commits). Tag `v0.1.0-core`.
- [~] A2. **Claude Desktop integration.**
  - [x] Write `claude_desktop_config.json` snippet into README (command: `excellia-mcp`, no args, stdio)
  - [x] Start `excellia-api` (uvicorn, 127.0.0.1:8000) — document that MCP tools need it running;
        better: `excellia-mcp` auto-spawns the API as a subprocess if `/health` fails (keep the code thin —
        subprocess spawn ≠ logic) — *done; on Windows the spawn MUST be detached, see the hard-won fix in §1*
  - [ ] Live test: "profile examples/messy_vendors.xlsx and tell me what's wrong with it" in Claude Desktop
        — **manual user step remaining** (paste config, restart GUI app); the MCP chain itself is proven
        by the live stdio client in `tests/test_mcp_integration.py`
- [x] A3. **`local_agent/agent.py`** — the air-gapped proof (~100 lines max):
  - stdio MCP client (`mcp` package) connects to `excellia-mcp`
  - `tools/list` → convert tool schemas to Ollama function-calling format
  - REPL loop: user prompt → Ollama (e.g. `llama3.1`, `qwen2.5`, `gemma3`) → tool call(s) → results → answer
  - Entry point `excellia-agent` in pyproject — verified live with `llama3.2:latest`
  - [x] Demo transcript saved to `docs/local_agent_demo.md`
- [x] A4. **Same-server proof:** run A2's exact prompt through A3. Zero changes to `server.py`.
      (Raw stdio client stands in for Claude Desktop; the Claude Desktop screenshot itself waits on A2's manual step.)
- [x] A5. **Instructive errors end to end** (the model must be able to self-correct):
  - missing file → "File not found: X. Provide an absolute path or a path relative to <cwd>." ✅
  - unknown ruleset → lists available rulesets ✅ (core already does; surfaced through MCP text)
  - non-tabular / unsupported file → names supported extensions ✅
  - API down → MCP tool returns "Excellia core API is not running. Start it with `excellia-api`." not a stack trace ✅
  - bonus: null-sentinel strings (`"null"`/`"none"`/`""`) coerced to real `None` at the API boundary
  - all error strings asserted in `tests/test_api_errors.py`
- [~] A6. **60-second install** on a clean venv, timed, steps written at the top of README.
      **Honest result:** ~2.5 min from a bare venv (pandas/scipy/sklearn wheels dominate); seconds when
      the scientific stack is already present. README claim corrected to match; literal "<60s" target dropped.

**GATE A — PASSED 2026-07-12** (tagged `v0.2.0-stage-a`) with two honest caveats: live offline agent demo ✔ ·
same unchanged server driven by two brains ✔ · committed & tagged ✔ · *caveat 1:* the Claude Desktop demo is
proven via a raw stdio client, the GUI paste-and-restart remains a manual user step · *caveat 2:* fresh-machine
install is ~2.5 min from a bare venv, not <60s (seconds with scientific Python preinstalled).

### Stage B — USEFUL (an analyst would actually keep it installed) — ✅ DONE 2026-07-17

Goal: real files (100K–1M rows), saved knowledge (rulesets/recipes), the two LLM pillars (`ask`,
`transform`) with hard anti-hallucination guardrails, and readable outputs.

- [x] B1. **Workspace** — `excellia/core/store.py`; root = `EXCELLIA_HOME` env or `~/.excellia/`
  - `rulesets/*.json`, `recipes/*.json`, `profiles/*.json`, `models/` (Stage C),
    `cache/`, `history.jsonl` (audit trail of every run: timestamp, op, file hash, params, result summary)
  - [x] Audit trail is append-only and every layer writes through one function (`store.record`)
- [x] B2. **Big files** — `ingest.iter_chunks` (xlsx via openpyxl read-only mode; csv via chunked
      readers; legacy .xls falls back to full-load-then-slice) + `profile_large` + `validate_large`
      streaming with cross-chunk state; opt-in 500K-row test (`EXCELLIA_BIG=1`) passes in ~85s well
      under budget. *Honest caveats:* streaming validate runs a subset of the inferred checks
      (formats/dup-IDs/dup-rows — mixed-type and missing-value inference need global stats and stay
      on the in-memory path); the memory test measures Python heap via tracemalloc (<1 GB asserted),
      not process RSS.
- [x] B3. **Job queue in the API** (never in core): `POST /jobs {op, params} → job_id`,
      `GET /jobs/{id}`; ThreadPool executor (2 workers); results parked in the workspace `jobs/` dir;
      sync endpoints stay for small files. MCP: `job_status(job_id)` tool; `transform_apply`,
      `run_recipe`, `export_report` accept `async_=True` and return a job_id with poll instructions.
      *Caveat:* status is queued/running/done/error — no numeric progress percentage yet.
- [x] B4. **Rulesets become data, not code:** CRUD via `store.py` + API
      (`GET/POST/DELETE /rulesets[/{name}]`) + MCP `save_ruleset(name, spec)`, and MCP **resources**
      `ruleset://<name>`. Starter packs shipped: `kyc`, `invoice`, `payroll`, `bank-statement`
      (as built-in spec dicts; user packs live in the workspace and merge into the list).
- [x] B5. **`llm.py` — the only LLM door** (core):
  - Ollama HTTP client via **stdlib urllib** (core's no-`requests` purity rule kept — the §8 question
    is answered), `OLLAMA_URL` env, model picker (`EXCELLIA_MODEL` env, else preferred installed
    family), health check, timeout, retry-once
  - **Strict-JSON contract helper:** `json_call` → parse (fence/prose tolerant) + one repair-reprompt
    + typed fallback `{status:"error", reason:"parse_failed"}` (the KYC doc's lesson, generalised)
  - Unit-tested with a fake transport; zero LLM calls anywhere else in core except via this module
- [x] B6. **`ask.py` — AI chat over data that cannot lie about numbers:**
  - Pipeline: LLM sees *schema + stats + 20 sample rows only* → strict-JSON **query plan**
    (filters/group_by/aggregates/sort/limit — a safe whitelist executed by pandas, never eval of LLM
    text; adversarial-escape tests in `tests/test_ask.py`) → engine computes → LLM narrates
  - Response shape: `{answer, evidence, plan, matched_rows}` — evidence always returned
  - [x] Refusal path: model can return `{refuse: why + which tool instead}`; invalid plans and parse
        failures degrade to instructive refusals, never crashes; failed narration falls back to a
        deterministic summary so numbers stay real
  - Proven live offline: qwen2.5-coder planned "total amount per city", pandas computed, narration
    matched the evidence exactly
- [x] B7. **`clean.py` — the deterministic formula library** (Limestone's formulas + GUI's edit panel + apply_formats2, unified):
  trim/collapse · case (upper/lower/title/sentence) · replace/remove char · split column by delimiter ·
  concat columns · math ops between columns · abs · date parse+format · currency strip ·
  drop empty rows/cols · redefine header row · dedupe rows (keep/aggregate: first/last/sum/max/min/mean) ·
  fill down · L/R/mid string slice. Every op = `{op, params}` JSON — **this is the recipe atom.**
  16 ops in a registry; unknown ops/params/columns raise errors naming the step and the valid options.
- [x] B8. **`transform.py` — propose → preview → confirm → apply (never silent):**
  - Input: instruction ("split address into street/city/pin", "mark rows taggable/non-taggable by X")
  - LLM maps instruction to: (a) a sequence of `clean.py` ops when deterministically possible, else
    (b) a per-row LLM op (`llm_map` with a strict output schema), else (c) a mix
  - `preview(df, instruction)` → recipe JSON + before/after on a 20-row sample; `apply(df, recipe)`
    executes on the full data (llm_map runs threaded with per-distinct-value dedup; big runs go
    through the job queue)
  - Output goes to **new columns** (`<col>_ai` suffix) unless `replace=True` is explicitly passed
  - [x] Undo: applies always write a NEW file — the original is never touched, so undo IS the
        original (simpler than the planned inverse-patch; pre-image parking becomes unnecessary)
  - [x] **Recipes are saved and replayable** — `save_as` on apply, `run_recipe(file, recipe_name)`,
        replay determinism asserted in tests
- [x] B9. **`report.py`** — everything the GUI's export did, engine-side:
  - highlighted xlsx (colour per issue kind, legacy priority: outlier > duplicate > mixed > format >
    missing), Issues/Anomalies sheets, Summary with legend
  - **Data Health Score** (the legacy heuristic: start 100; weighted deductions — outliers 0.8/pct,
    mixed 0.5/pct, missing 0.4/pct, format 0.3/pct, dups 0.2/pct) with the breakdown shown, never a bare number
  - *Deferred niceties:* per-column issue-count sheet and before/after-recipe comparison — small,
    land with the web app's dashboard (Stage D)
- [x] B10. **MCP surface v2** (server stays thin — every tool is still a forward, zero pandas):
      `ask_data`, `transform_preview`, `transform_apply`, `run_recipe`, `save_ruleset`, `export_report`,
      `job_status` + resources `ruleset://<name>`, `recipe://<name>`. Every docstring written against §12
      (trigger words · inputs/defaults · output keys + row convention · failure next-step).

**GATE B — PASSED 2026-07-17** (tagged `v0.3.0-stage-b`): 500K-row file profiles+validates without OOM ✔
(opt-in `EXCELLIA_BIG=1`, ~85s, heap <1 GB) · `ask` returns evidence tables and refuses gracefully ✔
(unit-tested with fakes + live offline smoke against qwen2.5-coder) · a transform previews, applies
non-destructively, saves as a recipe, and replays on a second file ✔ · both brains drive the same
unchanged server ✔ (live stdio integration test lists all 11 tools and profiles the demo file;
the Claude Desktop GUI paste remains the same manual user step as Gate A) · health-score xlsx report
opens ✔ (reopened and asserted with openpyxl in tests, incl. highlight fills)

### Stage C — DOMAIN SUITES (fraud · reconciliation pro · KYC) — ✅ DONE 2026-07-17

Goal: the three money features. Each is a deep vertical on top of Stage B plumbing.

#### C1. Fraud analysis (`core/fraud.py`) — supervised, honest, explainable

The user story (yours, formalised): *"Give fraud-detected data as training input — then, for accuracy,
they upload fresh data and the system scores it."*

- [x] `train(df, label_column, model_name, positive_label=None) -> ModelCard`
  - sklearn Pipeline: coerce/impute → one-hot low-cardinality categoricals → scale numerics →
    **GradientBoosting** (default) or RandomForest (option); class imbalance via sample weights;
    stratified 5-fold CV (manual loop — no dependence on sklearn's shifting fit-param routing)
  - **ModelCard** (saved as `models/<name>.meta.json` beside the `.joblib`): rows, class balance,
    features used/dropped, CV **precision / recall / F1 / ROC-AUC**, confusion matrix at the chosen
    threshold, top-15 feature importances, feature baselines (for scoring factors), trained-at,
    schema fingerprint (hash of column names — NOT the data)
  - [x] Refuses with an instructive error when: label column missing (lists columns), single-class,
        > 10 classes ("that looks like data, not a label"), < 200 usable rows, or leakage
        (numeric corr ≈1.0, or a categorical that perfectly encodes the label — named in the error)
- [x] `score(df, model_name, threshold=None)`
  - per row: `fraud_probability` (0–1), `risk_band` (low/medium/high/critical, fixed thresholds),
    **`top_factors`** — up to 3 features pushing this row's score up, with values and contributions
    (occlusion against training baselines: one batch prediction per probed feature — cheap and local)
  - schema drift check: missing columns → refuse listing the difference; extra columns → listed as ignored
- [x] `evaluate(df, label_column, model_name) -> metrics` — the "for accuracy" step: labelled holdout →
      honest precision/recall/F1/confusion side by side with the card's CV metrics + a drift note
- [x] Unsupervised fallback stays `detect_anomalies` — said explicitly in the train refusals and the
      `train_fraud_model` docstring ("no labelled history → use detect_anomalies")
- [x] API: `POST /fraud/train` (also a job op — training can be slow), `POST /fraud/score`,
      `POST /fraud/evaluate`, `GET /fraud/models`; MCP: `train_fraud_model`, `score_fraud`,
      `evaluate_fraud_model`, `list_fraud_models`
- [x] Honesty guardrails baked in: metrics always attached; wording is "risk score", never
      "this IS fraud"; card attached to every score response; synthetic-signal test asserts a
      metrics floor and the leakage detector fires on planted leaks

#### C2. Financial reconciliation PRO (grow `core/reconcile.py` + `clean.py` + `report.py`)

Everything Limestone did, minus the GUI debt:

- [x] **Match levels** on every matched/discrepant record: `L1` exact · `L2` within tolerance ·
      `L3` fuzzy-key match (opt-in `fuzzy_keys` per profile, with `key_similarity` attached)
- [x] **Variance columns** for numeric discrepancies: `diff_abs`, `diff_pct` per differing field,
      plus per-field variance totals in the run summary
- [x] **Pre-steps** in the profile: cleaning recipe per source (`pre_recipe_a/b`) + dedupe with
      aggregation strategy (`dedupe_a/b` — e.g. sum amounts on duplicate txn IDs) before matching
- [x] **Profiles** (`profiles/*.json`): `{name, keys, tolerance, fuzzy_keys, pre_recipe_a/b,
      dedupe_a/b}` — one-click monthly runs: `run_reconciliation_profile(file_a, file_b, profile_name)`
- [x] **Reconciliation report xlsx**: sheets = Summary (counts, match rate, levels, variance totals) /
      Matched (with level) / Only-in-A / Only-in-B / Discrepancies (side-by-side a|b + variance)
- [x] **History** → `history.jsonl` (profile, file hash, bucket counts, match rate) via `store.record`
- [x] API: profiles CRUD + `POST /reconcile/run` (also a job op for big pairs); MCP:
      `run_reconciliation_profile`, `save_reconciliation_profile`, resource `profile://<name>`

#### C3. KYC analysis (`core/kyc.py`, OCR as optional extra)

- [x] **Hybrid name matching** (the KYC tool's algorithm, generalised):
  - `name_similarity(a, b) -> float` — normalise (lower, strip punctuation, collapse spaces) →
    `SequenceMatcher.ratio()*100`; golden-pair tests (transliteration, honorifics, punctuation)
  - `match_names(df, col_a, col_b | group_by, llm_verify=False, seq_threshold=50)` — bulk nC2 within
    groups (guarded: too many pairs → error telling you to add group_by) or pairwise columns; when
    `llm_verify` and similarity ≥ threshold, `llm.py` renders the strict-JSON verdict
    `{status: match|no_match, match_percent, reason}` (the "strict fraud-screening name assistant"
    prompt); parse-failure → deterministic score with `verdict: "unverified"` — never a crash
  - output per pair: both names, seq %, verdict, llm %, reason — all tested with a fake transport
- [x] **KYC dedupe** `dedupe(df, columns, threshold, strategy)` — entity resolution: union-find
      clusters over sorted-neighbour similarity, canonical row per cluster (`most_complete` /
      first / last), merge log with Excel rows; deduped copy written to a NEW file — distinct from
      row-level near-dup flags in `anomaly.py`
- [x] **ID validation** = existing `kyc` ruleset ✅ (PAN/Aadhaar/GST/IFSC formats + uniqueness) — done
- [ ] **OCR (later, optional):** `pip install excellia[ocr]` → `ocr.py` with **local Tesseract only**
      (Google Cloud Vision is cloud → excluded from default; may exist as an explicitly-named opt-in
      plugin, never silent). Regex dictionary from the KYC spec (Aadhaar `\d{4}\s?\d{4}\s?\d{4}`, PAN,
      GSTIN, DOB, gender) + optional local-LLM cleanup of noisy OCR text into the JSON schema.
      Extract → validate through the `kyc` ruleset automatically.
- [x] API: `/kyc/match_names` (also a job op for bulk), `/kyc/dedupe`; MCP: `match_names`, `dedupe_rows`

**GATE C — PASSED 2026-07-17** (tagged `v0.4.0-stage-c`): train on a labelled file, evaluate on a
holdout, score a fresh file with per-row reasons ✔ (synthetic-signal tests assert the metrics floor,
the leakage detector, drift refusal, and Excel-row factor output) · a saved reconciliation profile
runs end to end producing the 5-sheet report ✔ (asserted sheet-by-sheet with openpyxl, via core AND
the HTTP API) · bulk name matching with LLM verify produces verdicts offline ✔ (verdict table via
API/MCP with fake-transport tests; *caveat: verdicts return as JSON, not yet as an xlsx file*) ·
every output carries reasons ✔ · OCR remains deliberately unbuilt (optional `excellia[ocr]`, later)

### Stage D — FACES (web app + Excel add-in) — *current stage*

#### D1. Web app (`excellia/webapp/`) — the big-file / bulk door — ✅ v1 SHIPPED 2026-07-17

The legacy Flask GUI's replacement, but as a **pure client of the core API** (nothing computes in
the web layer — test-enforced):

- [x] Stack: **static single-page app served by the core API itself** at `/app` — vanilla JS,
      zero build toolchain, zero second server, same-origin (no CORS), pip ships it.
      **Changed 2026-07-17 from React+Vite+TS** (owner prompted "react?? flask can't do?"):
      Flask was rejected because server-rendered templates are exactly the legacy monolith
      pattern Phase 1 escaped; React's toolchain was dropped because a Node build step fights
      the "pip install and go" thesis. Graduate to React only if the UI outgrows vanilla.
- [x] Views (v1):
  - [x] **Upload & file picking** — drag-drop / click-to-pick via `POST /upload` (multipart, saved
        to workspace `uploads/`), or paste a local path; selection persists across visits
  - [x] **Quality** — profile + validate (ruleset picker fed by `GET /rulesets`) + anomalies with
        severity badges; health score with breakdown; highlighted-report export (path shown —
        the file is already on the user's disk, that's the point of local-first)
  - [x] **Transform studio** — instruction → preview before/after sample + recipe JSON → confirm
        apply (replace checkbox, save-as-recipe) → saved-recipe replay
  - [x] **Ask the data** — answer + evidence table + the query plan that actually ran (trust through glass)
  - [x] **Sidebar chat** (2026-07-19) — the same Ask thread, collapsible in the sidebar and
        reachable from every view; shared in-memory history, one `POST /ask` per message,
        rendering only (chatWatchers pub-sub keeps both windows painted)
  - [x] **Reconciliation** — file B + keys/tolerance/fuzzy-keys or saved profile, profile save,
        four bucket tabs with match-level badges, 5-sheet report path
  - [x] **Fraud** — train (label column → metrics card + top features) · score (bands, per-row top
        factors) · evaluate (holdout vs CV side by side)
  - [x] **KYC** — name matching (pairwise/cross, LLM-verify toggle) & entity dedupe with merge log
  - [x] **Bulk mode** (2026-07-19) — N files (multi-drop upload or pasted paths) × one op
        (profile / validate+ruleset / health report / saved recipe) → ONE background job per
        file via `POST /jobs`, polled into a live status matrix with per-file results and a
        roll-up line; polling stops when the user leaves the view. Zero new API surface.
  - [x] **Jobs & History** — polling job table + audit-trail browser fed by `history.jsonl`
- [x] Big-file UX: sidebar **"Big file mode"** toggle (persisted) — every heavy POST (profile/
      validate/anomalies/report/transform-apply/reconcile-run/fraud-train+score/kyc) routes
      through `POST /jobs` + 1.5s polling with a live sidebar job-status line; the `call()`
      helper resolves to the sync endpoint's exact result shape so views are path-agnostic.
      *Landed 2026-07-19. Live 500K-row run through this exact job sequence: profile 3s ·
      validate 5s (480K seeded issues) · transform (2-step recipe) 4.3s · highlighted report
      216s — the xlsx write dominates; the job queue is precisely why the page never freezes.
      (Driven via HTTP; an in-browser click-through of the same calls remains a nice-to-have.)*
- [x] Auth: **none in v1** (localhost, single analyst); uploads land in the workspace, originals
      never touched

#### D2. Excel add-in (`excellia/addin/`) — ✅ v1 SHIPPED 2026-07-17 (formula core + lean pane; chat next)

Architecture — **upgraded from the concept doc**: Office.js (the only cross-platform route — Windows,
Mac, Excel on the web, one manifest), and the Node/Express HTTPS proxy is GONE. `excellia-addin`
mints a self-signed localhost certificate (pure Python, `pip install excellia[addin]`), offers to
trust it with explicit consent, and serves the SAME FastAPI app (API + web app + add-in files) over
**https://localhost:8443** — same origin, no proxy, no toolchain. New `/values/*` endpoints are the
formula door: validate/similarity (deterministic), map/split/ask (LLM via core). Honest naming note:
Excel custom functions require a namespace, so the general formula is `=XAI.RUN(...)`, not bare `=XAI()`.

**Mode 1 — Formula mode: the `=XAI.*` family (Excel custom functions):**

- [x] `=XAI.RUN(range, prompt)` — the general per-cell AI transform (`=XAI.RUN(A2,"extract the pin code")`)
- [x] `=XAI.SPLIT(range, "street | city | pin")` — split into parts; returns a **spilled array**
      with a header row (strict-JSON contract per distinct value; parse failure → blank parts)
- [x] `=XAI.TAG(range, "criteria")` — Yes/No classification per cell
- [x] `=XAI.ASK("question", A1:D200)` — one-cell answer backed by `ask`'s evidence pipeline
      (the range's first row = headers; full evidence table lives in the web app / task pane later)
- [x] `=XAI.VALIDATE(range, "pan|gst|email|ifsc|aadhaar|phone")` — deterministic regex verdicts,
      **zero LLM** (`validate.check_format` in core)
- [x] `=XAI.MATCH(a, b)` — KYC name-similarity 0–100 between cells/equal ranges (broadcasts 1-vs-N)
- [~] Engineering rules for formula mode:
  - [x] batching: cells coalesce into ONE API request per (function, prompt) per 80ms window
  - [x] **cache** keyed by (value, prompt): in-memory for the session + LLM-derived results
        persisted to `OfficeRuntime.storage` (newest-2000 cap, debounced writes, loaded before
        any HTTP on startup) — survives file reopen. Deterministic kinds recompute (cheap).
        *Landed 2026-07-19.*
  - [x] volatile off (custom functions are non-volatile by default); errors surface as `#VALUE!`
        with the API's instructive message (Excel doesn't allow custom `#XAI!` codes)
  - [ ] cancellation + long-batch handoff to a task-pane job — deferred
- [ ] Live-Excel verification: sideloading is inherently a manual user step (like Claude Desktop);
      the mechanical layer (manifest↔metadata↔runtime consistency, TLS serving, every endpoint)
      is test- and smoke-verified

**Mode 2 — Task-pane copilot (v1 lean; the owner's call: core first, chat later):**

- [~] Range handling: uses the current selection with explicit shape checks (single column /
      two columns); `getUsedRange` intersection guard still to add
- [~] Operations shipped: **Validate formats** · **Transform selection (preview → apply)** ·
      **Name match** · **Chat** (2026-07-19: question over the selected range incl. header row →
      `/values/ask` → answer + evidence table, refusals surfaced) · **Categorise** +
      **Summarise** (2026-07-19: fixed instructions over the same `/values/map` door,
      adjacent-column writes) — all mapped to `/values/*` core endpoints.
      Deferred: Keywords · Simplify JSON
- [ ] Combined vs Per-row processing modes with live progress — deferred (single batched mode v1)
- [x] **Non-destructive always:** writes ONLY to an empty adjacent column (refuses otherwise,
      instructively); AI-written cells get the visual accent (blue + italic) + bold header
- [x] Preview→confirm for transforms (sample of distinct values shown before apply)
- [~] Connection status pill (API version shown; Ollama/model detail still to add)
- [ ] Abort button (AbortController) — deferred
- [x] Manifest + sideload instructions for **Windows (shared-folder catalog)** and **macOS (wef
      folder)** printed by `excellia-addin` and in docs/RUNNING.md; AppSource much later

**GATE D — OPEN only on the manual step (2026-07-19; automation teeth all closed):**
500K-row file through checks→transform→report without a freeze ✔ (Big file mode job path,
live-timed: 3s/5s/4.3s/216s — see D1) · `=XAI.SPLIT` spills ✔, recalc hits the cache ✔, cache
survives file reopen ✔ (`OfficeRuntime.storage`) · task pane transforms non-destructively ✔ +
chat/categorise/summarise ✔ (*live per-row progress + abort still deferred*) · bulk mode ✔ ·
faces contain ZERO logic ✔ (test-enforced for both) · **remaining: sideload into real Excel on
Windows and Mac and watch it work — inherently manual, `excellia-addin` prints the steps.**
*Bonus fix from the live run: flat-params recipe steps and wrong param names now raise
instructive TransformErrors naming the step (`transform.validate_recipe` rejects stray step
keys; `apply` wraps TypeError/CleanError with the step number) instead of leaking a raw
TypeError — regression-tested.*

### Stage E — SHIP — writing deliverables ✅ 2026-07-19; recordings + publish left

- [x] README rewrite (2026-07-19): thesis first → products table (each linking its own README) →
      install → six "pick your door" quick starts → tools table → honest privacy TABLE →
      repo layout → status. GitHub-friendly, machine-agnostic paths.
- [x] Per-component READMEs (2026-07-19, owner request): `excellia/core/README.md`,
      `api/README.md`, `mcp_server/README.md`, `local_agent/README.md`, `webapp/README.md`,
      `addin/README.md` — each: what it is, how to run, how to use, key files, the rules.
- [~] 90-second screen recording: Claude Desktop cleans `messy_vendors.xlsx` — **script DONE**
      (`docs/recording_script.md`: shot list, timed narration, exact prompts, prep checklist);
      owner records it himself.
- [~] Second recording (30s): fully offline via `local_agent` — **script DONE** (same file;
      airplane-mode cold open). Owner records.
- [x] The post: *"Why enterprise AI logic should be an MCP server, not an app"* — draft in
      `docs/architecture_post.md` (~1,100 words, ready to publish).
- [ ] PyPI publish (`pip install excellia`), version tags — **explicitly held** (owner:
      "don't commit or publish"); `CHANGELOG.md` itself is written ✔ (full history 0.1.0→now
      + Unreleased), `LICENSE` (MIT) added ✔
- [x] `SECURITY.md` (threat model: loopback-only sockets, per-mode exposure table, storage,
      prompt-injection posture, reporting) + `CONTRIBUTING.md` (setup + the 9 architecture
      rules PRs are reviewed against) — 2026-07-19

---

## 4. Full API surface after Stage D (reference)

```
# sync (small files)
GET  /health                       POST /profile        POST /validate
POST /anomalies                    POST /reconcile      POST /ask
POST /clean                        POST /transform/preview
POST /transform/apply              POST /report
POST /kyc/match_names              POST /kyc/dedupe
POST /fraud/score                  POST /fraud/evaluate

# workspace CRUD
GET/POST/PUT/DELETE /rulesets[/{name}]      /recipes[/{name}]
GET/POST/PUT/DELETE /reconcile/profiles[/{name}]
GET /fraud/models    GET /history

# async (big files / slow ops) — everything above accepts {"async": true}
POST /jobs {op, params} -> {job_id}
GET  /jobs/{id} -> {status: queued|running|done|error, progress, result_path?, error?}
GET  /jobs -> list
```

## 5. Full MCP tool list after Stage C (server still < ~300 lines, still zero logic)

| Tool | One job |
|---|---|
| `profile_sheet` ✅ | understand an unfamiliar file |
| `validate` ✅ | rule violations with row/col/reason |
| `detect_anomalies` ✅ | statistical suspects with confidence+reason |
| `reconcile` ✅ | quick two-file compare |
| `ask_data` ✅ | question → answer + evidence table (never invents numbers) |
| `transform_preview` ✅ | instruction → recipe + before/after sample (nothing changes yet) |
| `transform_apply` ✅ | apply a previewed recipe; new columns unless told otherwise |
| `run_recipe` ✅ | replay a saved cleanup on a new file |
| `save_ruleset` ✅ / `save_reconciliation_profile` ✅ | persist reusable configs |
| `run_reconciliation_profile` ✅ | one-click monthly reconciliation |
| `train_fraud_model` ✅ | labelled file → model + honest metrics card |
| `evaluate_fraud_model` ✅ | labelled holdout → real-world accuracy |
| `score_fraud` ✅ | fresh file → per-row risk + top factors |
| `list_fraud_models` ✅ | model cards |
| `match_names` ✅ | KYC hybrid name matching (offline LLM verify optional) |
| `dedupe_rows` ✅ | entity-level near-duplicate resolution |
| `export_report` ✅ | highlighted xlsx / summary / health score |
| `job_status` ✅ | poll long-running work |

Resources: `ruleset://<name>` · `recipe://<name>` · `profile://<name>` · `fraudmodel://<name>` (card JSON).

## 6. Workspace layout (`EXCELLIA_HOME`, default `~/.excellia/`)

```
~/.excellia/
  rulesets/kyc.json invoice.json payroll.json ...
  recipes/<name>.json            # ordered clean/transform ops — the replayable atoms
  profiles/<name>.json           # reconciliation profiles
  models/<name>.joblib           # fraud pipelines
  models/<name>.meta.json        # ModelCards (metrics, features, fingerprints — never data)
  cache/                         # transform pre-images (undo), =XAI() response cache
  history.jsonl                  # append-only audit trail of every run
  uploads/ jobs/                 # API working dirs (auto-cleaned, TTL)
```

## 7. What we explicitly do NOT build (scope discipline, inherited + extended)

- No cloud LLM/OCR calls by default, ever. Opt-in plugins must be loudly named (`excellia[gcv]`) and logged.
- No general agent framework, no multi-tenant platform, no auth/RBAC in v1 (localhost, one analyst).
- No MCP client as a product (hosts bring their own; ours lives only inside `local_agent`).
- No "works with any data source" — spreadsheets (xlsx/xlsm/xls/csv/tsv). That's the trust surface.
- No writing into users' original files — exports are always new files; add-in writes adjacent.
- No fat MCP server. The moment `server.py` imports pandas, stop and refactor.
- Not six shallow servers — one deep one. Fraud/KYC/reconcile are TOOLS on the same server, not new servers.

## 8. Testing strategy per stage

- **A:** agent loop integration test with a scripted fake-Ollama transport; MCP tool-schema snapshot test;
  error-message tests (every instructive error string asserted)
- **B:** 500K-row memory test (RSS budget); `ask` plan-executor property tests (plan whitelist can't be
  escaped — adversarial strings in filters); recipe round-trip (save→load→replay determinism);
  report xlsx opened+parsed by openpyxl in tests
- **C:** fraud on synthetic labelled data (known signal → metrics floor asserted; leakage detector fires
  on a planted leak); reconciliation profile end-to-end on Limestone-shaped fixtures (CMS vs Switch style);
  KYC matcher golden pairs (hindi-transliteration variants, initials, honorifics)
- **D:** API-contract tests shared by web app and add-in (schemathesis or recorded fixtures);
  add-in custom-function batching/caching unit tests (Node); Playwright smoke for the web app
- **Always:** `core` purity test ✅ (already exists — extend forbidden list with `ollama`? no: `llm.py`
  talks raw HTTP via stdlib/`urllib` or is the single allowed exception, decided in B5)

## 9. Risk register (what will bite, and the plan)

| Risk | Mitigation |
|---|---|
| Local LLMs return malformed JSON constantly | B5's strict-JSON contract with repair-reprompt + typed fallback; NEVER a raw `json.loads` outside `llm.py` |
| `ask` becomes a hallucination machine | plan-whitelist executor; evidence table mandatory; numbers only from pandas |
| Big xlsx eats RAM | read-only/streaming openpyxl, chunked csv, job queue, RSS test in CI |
| Fraud model overfits tiny data / leaks labels | min-rows refusal, CV-only metrics, leakage detector, honest wording rules |
| Excel custom functions re-fire on every recalc → LLM cost/time explosion | (value,prompt) cache + batching + non-volatile registration |
| Office HTTPS wall blocks local API | the proven proxy pattern (dev-certs + express middleware), documented |
| Scope creep (this very file is huge) | stage gates are sequential and blocking; §7 list; MCP server line-count as a canary |
| Windows-first paths (legacy habit) | `pathlib` everywhere, CI on ubuntu+windows |

## 10. Milestone → announcement mapping (marketing is part of shipping)

- Gate A → repo public + "install in 60s" README
- Gate B → the 90-second Claude Desktop video
- Gate C → the offline-agent video + the architecture post
- Gate D → web app screenshots thread + add-in sideload guide
- Gate E → PyPI + the "one deep server" post

## 11. Decisions already made (do not relitigate without a reason)

1. FastMCP over raw MCP SDK; stdio transport (no ports for the AI door)
2. Excel row numbers in every user-facing row reference
3. LLM assists, deterministic code decides; regex beats model where regex is perfect
4. ~~The add-in proxy forwards to the core API~~ **Revised 2026-07-17:** there is NO proxy at all —
   `excellia-addin` serves the same FastAPI app over HTTPS (self-signed localhost cert, consent-gated
   trust) so the pane, the formulas, and the API share one origin. The 2026-07-12 half of the
   decision stands: nothing in Excel ever talks straight to Ollama
5. ~~React for the web app~~ **Revised 2026-07-17 (owner call):** the web app is a static SPA
   served by the core API at `/app` — no Flask (legacy pattern), no Node toolchain (fights
   pip-install-and-go). Vanilla JS everywhere; graduate to React only if the UI outgrows it
6. GradientBoosting default for fraud (RandomForest option); ModelCards mandatory
7. Tesseract-only OCR by default; cloud OCR = loud opt-in extra
8. Job queue lives in the API layer; core stays synchronous and pure
9. `~/.excellia` workspace; append-only `history.jsonl` audit trail
10. One deep MCP server, never six shallow ones

## 12. Docstring checklist for every MCP tool (the craft that decides adoption)

Every tool docstring must answer, in ≤ 4 sentences: **when to reach for it** (trigger words an agent
recognises) · **what it needs** (and what happens with defaults) · **what comes back** (keys, units,
row-number convention) · **what to do on failure** (the next tool or the fix). Error strings are part
of the interface: name the problem, name the fix, name the alternative tool.

---

*End of checkpoint. A, B, C done and gated; Stage D's automation is COMPLETE, and Stage E's
WRITING is complete (2026-07-19): README + six component READMEs + SECURITY + CONTRIBUTING +
CHANGELOG + LICENSE + both recording scripts + the architecture post, plus the web-app sidebar
chat. What remains is exactly the human-in-the-loop list: (1) sideload the add-in into real
Excel on Windows and Mac (`excellia-addin` prints the steps), (2) paste the Claude Desktop
config and watch it work, (3) record the two videos from `docs/recording_script.md`,
(4) commit (owner-held) and (5) PyPI publish (owner-held). Update checkboxes as you land
work — this file is the memory.*
