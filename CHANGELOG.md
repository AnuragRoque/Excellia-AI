# Changelog

All notable changes to Excellia. Format loosely follows [Keep a Changelog](https://keepachangelog.com);
versions are git tags.

## [Unreleased]

### Added
- Web app **sidebar chat** — the Ask conversation, reachable from every view (same single
  `POST /ask` per message; one shared thread with the Ask view).
- GitHub-ready documentation: rewritten top-level README, per-component READMEs
  (`core`, `api`, `mcp_server`, `local_agent`, `webapp`, `addin`), `SECURITY.md` threat model,
  `CONTRIBUTING.md`, `LICENSE` (MIT), this changelog, the two demo recording scripts
  (`docs/recording_script.md`), and the architecture post draft (`docs/architecture_post.md`).

### Pending before 1.0
- Manual verifications: add-in sideload into real Excel (Windows + Mac), Claude Desktop
  paste-and-restart demo. Screen recordings. PyPI publish.

## [0.6.0-stage-d2] — 2026-07-19 (Gate D automation closed)

### Added
- **Big file mode** in the web app: every heavy POST routes through `POST /jobs` + polling with
  a live status line; verified live with a 500K-row run (profile 3s · validate 5s · transform
  4.3s · report 216s).
- **Bulk mode** view: N files × one operation → one background job per file, live status matrix.
- Excel formula cache **persistence** (`OfficeRuntime.storage`) — LLM results survive workbook
  reopen; newest-2000 cap, debounced writes.
- Task pane **chat** (`/values/ask` with evidence), **categorise** and **summarise**
  (`/values/map`, adjacent-column writes).
- Web-app restyle to the reference palette; Ask view rebuilt as a chat thread.
- `README_RUNNER.md` — per-server runner's guide.

### Fixed
- `transform.py` instructive errors: flat recipe steps / bad param names now name the offending
  step instead of leaking a raw TypeError.

## [0.6.0-addin] — 2026-07-17 (Stage D2: Excel add-in v1)

- `=XAI.*` custom-function family (RUN / SPLIT / TAG / ASK / VALIDATE / MATCH) with batching
  and (value, prompt) caching; spilled arrays; non-volatile.
- Lean task pane: validate formats, transform (preview → apply), name match — writes only to
  empty adjacent columns.
- `excellia-addin`: self-signed localhost HTTPS (consent-gated trust), one Office.js manifest
  for Windows + Mac, printed sideload steps. No Node, no proxy — same FastAPI app on :8443.
- New `/values/*` API endpoints (the formula door).

## [0.5.0-webapp] — 2026-07-17 (Stage D1: web app v1)

- Static SPA served by the core API at `/app` — vanilla JS, zero build step, zero logic
  (test-enforced). Views: Quality, Ask, Transform, Reconcile, Fraud, KYC, Jobs & History.
- `POST /upload` multipart door; uploads land in the workspace.

## [0.4.0-stage-c] — 2026-07-17 (Stage C: domain suites)

- `core/fraud.py`: train/score/evaluate with ModelCards, stratified CV, class-imbalance
  weights, leakage detection, per-row top factors, risk bands, drift refusal.
- Reconciliation pro: L1/L2/L3 match levels, variance columns, fuzzy-key pass, saved profiles
  with pre-recipes and dedupe, 5-sheet xlsx report.
- `core/kyc.py`: hybrid name matching (optional offline-LLM verdicts), entity dedupe
  (union-find clusters, canonical rows, merge log).
- 8 new MCP tools (19 total) + `profile://` resource; fraud/reconcile/KYC API endpoints + job ops.

## [0.3.0-stage-b] — 2026-07-17 (Stage B: useful)

- Workspace (`~/.excellia/`) with rulesets/recipes CRUD and append-only `history.jsonl`.
- `core/llm.py` — the single LLM door (stdlib Ollama client, strict-JSON contract).
- `core/ask.py` — plan-whitelist chat with mandatory evidence tables.
- `core/clean.py` (16 deterministic recipe ops) + `core/transform.py`
  (preview → confirm → apply, `_ai` columns, saved replayable recipes).
- `core/report.py` — highlighted xlsx + Data Health Score with breakdown.
- Big-file streaming (`iter_chunks`, `profile_large`, `validate_large`); job queue in the API;
  MCP v2 (11 tools + resources). Starter rulesets: kyc, invoice, payroll, bank-statement.

## [0.2.0-stage-a] — 2026-07-12 (Stage A: the loop breathes)

- Offline agent (`excellia-agent`): Ollama + MCP stdio client, REPL + one-shot.
- Same-server proof: Claude-Desktop-style host and offline agent drive identical `server.py`.
- Instructive errors end to end; null-sentinel coercion at the API boundary.
- Windows fix: MCP server spawns the core API detached (inline children hang tool calls).

## [0.1.0-core] — 2026-07-12 (Phase 1)

- Core engine extracted from the legacy Flask monolith: ingest/profile, validate, anomaly,
  reconcile — pure Python, purity test-enforced.
- Core API (`/health /profile /validate /anomalies /reconcile /rulesets`), thin MCP server
  (4 tools), packaging with entry points, demo data, 72 tests.
