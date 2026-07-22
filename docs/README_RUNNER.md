# Excellia — Runner's Guide (every server, how to start it, how to use it)

> One brain, many doors. This file tells you how to **run and use each server/face** that exists
> today. Deeper walkthroughs live in [docs/RUNNING.md](docs/RUNNING.md); project status lives in
> [EXCELLIA_FEATURES.md](EXCELLIA_FEATURES.md) §1.

## 0. One-time setup (all servers share this)

```powershell
cd "C:\Users\anura\Documents\04 PROJECT MAIN\11 Excellia Core\excellia_codebase"
python -m venv .venv                # skip if .venv exists
.venv\Scripts\Activate.ps1
pip install -e .[dev]

Get-Command excellia-api, excellia-mcp, excellia-agent   # all three must resolve
pytest                                                    # full suite, no network needed
```

Workspace (saved rulesets/recipes/profiles/models, audit trail): `~/.excellia/` — move it with
the `EXCELLIA_HOME` env var. Demo file with seeded errors: `examples/messy_vendors.xlsx`.
Row convention everywhere: Excel rows — header = 1, first data row = 2.

---

## 1. `excellia-api` — the Core API server (FastAPI)

**What it is:** the single HTTP door to the engine. Every other face (web app, add-in, MCP) is a
client of this. Owns the job queue, uploads, and workspace CRUD. Zero logic lives here — every
endpoint calls exactly one core function.

**Start:**

```powershell
excellia-api        # uvicorn on http://127.0.0.1:8000, logs in the foreground
```

**Use:**

- Interactive docs (full surface): http://127.0.0.1:8000/docs
- Sync analysis: `POST /profile /validate /anomalies /reconcile /ask /clean /transform/preview
  /transform/apply /report`
- Domain suites: `/fraud/train|score|evaluate|models` · `/reconcile/profiles` CRUD +
  `/reconcile/run` · `/kyc/match_names` `/kyc/dedupe`
- Workspace: `GET/POST/DELETE /rulesets[/{name}]` `/recipes[/{name}]` · `GET /history`
- Big files / slow ops: `POST /jobs {op, params}` → `GET /jobs/{id}` (queued|running|done|error)
- Quick smoke:

```powershell
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/profile -H "Content-Type: application/json" `
     -d '{"file": "C:/.../examples/messy_vendors.xlsx"}'
```

Forward slashes in JSON paths avoid double-backslash escaping. Optional params tolerate
`"null"`/`"none"`/`""` as absent.

---

## 2. Web app — served BY `excellia-api` at `/app` (no second server)

**What it is:** the point-and-click face for big/bulk files. Static SPA, vanilla JS, zero build
step, zero logic (test-enforced) — every button is one HTTP call to the API above.

**Start:** nothing extra — it ships inside the API process:

```powershell
excellia-api        # then open http://127.0.0.1:8000/app/
```

**Use:** drag-drop a spreadsheet (or paste a local path) in the sidebar, then:
**Quality** (profile / validate / anomalies / health-score report) · **Ask** (a chat thread —
each answer carries its evidence rows + the query plan that ran) · **Transform** (preview →
confirm → saved recipes) · **Reconcile** (profiles, L1/L2/L3 match tabs, 5-sheet report) ·
**Fraud** (train / score / evaluate) · **KYC** (name match, dedupe) · **Bulk** (one operation
× many files — each file becomes a background job, live status matrix with per-file results) ·
**Jobs & History** (job polling + audit trail). For 100K+ row files flip the sidebar
**Big file mode** toggle — heavy operations then run as background jobs and are polled, so
the page never hangs on one long request.

---

## 3. `excellia-mcp` — the MCP server (the AI door)

**What it is:** a thin stdio MCP server exposing 19 tools + `ruleset:// recipe:// profile://`
resources. Zero pandas, zero logic — it forwards to the Core API and **auto-spawns it**
(detached on Windows) if it's not running. You never start `excellia-api` by hand for this door.

**Start:** you don't run it directly — an MCP host launches it. Point any host at the absolute
exe path, stdio transport, no args, no ports:

```
C:\...\excellia_codebase\.venv\Scripts\excellia-mcp.exe
```

**Use it from:**

- **Claude Desktop** — Settings → Developer → Edit Config, add:

```json
{
  "mcpServers": {
    "excellia": {
      "command": "C:\\Users\\anura\\Documents\\04 PROJECT MAIN\\11 Excellia Core\\excellia_codebase\\.venv\\Scripts\\excellia-mcp.exe"
    }
  }
}
```

  then **fully quit** (system tray) and relaunch. Ask: *"Profile <absolute path to
  messy_vendors.xlsx> and tell me what's wrong with it."*

- **Claude Code** — `claude mcp add excellia "C:\...\.venv\Scripts\excellia-mcp.exe"`
- **Any other MCP host** (Cursor, Windsurf, VS Code MCP…) — same stdio config.
- **Live smoke test:** `$env:EXCELLIA_RUN_MCP_IT = "1"; pytest tests/test_mcp_integration.py -v`

Tool list + one-line jobs: see the table at the top of [docs/RUNNING.md](docs/RUNNING.md).
Tools marked * there (`ask_data`, `transform_preview`, LLM-verify matching) need Ollama;
everything else is deterministic.

---

## 4. `excellia-agent` — the offline Ollama agent (zero bytes leave the machine)

**What it is:** our own MCP host — an air-gapped agent that lets a local Ollama model drive the
same unchanged MCP server. The privacy proof.

**Prereq:** [Ollama](https://ollama.com) running with a tool-capable model:

```powershell
ollama pull qwen2.5:7b
```

**Start & use** (venv activated):

```powershell
excellia-agent                                       # interactive REPL
excellia-agent check examples\messy_vendors.xlsx     # one-shot file check
```

- Pin a model: `$env:EXCELLIA_AGENT_MODEL = "qwen2.5:7b"` before launching.
- Non-default Ollama URL: `OLLAMA_URL` env (default `http://127.0.0.1:11434`).
- A non-tool-capable model gets an instructive error naming the fix, not a silent failure.

---

## 5. `excellia-addin` — the HTTPS server for the Excel add-in

**What it is:** the same FastAPI app served over **https://localhost:8443** (Office panes refuse
plain HTTP). Mints a self-signed localhost cert and asks consent before trusting it. Serves the
`=XAI.*` custom functions, the task pane, and all API routes — one origin, no proxy, no Node.

**Start:**

```powershell
pip install excellia[addin]     # one-time: cert library
excellia-addin                  # mints/trusts cert, prints sideload steps, serves :8443
```

**Sideload (one time — the command prints these too):**

- **Windows:** copy `excellia/addin/static/manifest.xml` to a shared folder → Excel → Options →
  Trust Center → Trusted Add-in Catalogs → add that folder → restart Excel → Insert →
  My Add-ins → Shared Folder → Excellia.
- **macOS:** copy `manifest.xml` to
  `~/Library/Containers/com.microsoft.Excel/Data/Documents/wef/` → restart Excel → Insert →
  My Add-ins → Excellia.

**Use — formulas** (batch per calc pass, cached per value+prompt):

```
=XAI.VALIDATE(C2:C99, "pan")        deterministic format check — zero AI
=XAI.MATCH(A2, B2)                  KYC name similarity 0–100
=XAI.RUN(A2:A99, "extract pin")     per-cell AI transform (needs Ollama)
=XAI.TAG(B2:B99, "corporate?")      Yes/No classification (needs Ollama)
=XAI.SPLIT(A2, "street|city|pin")   spills parts across columns (needs Ollama)
=XAI.ASK("total per city?", A1:D99) answer computed from the range, never invented
```

Formula results from the LLM are cached per (value, prompt) and **survive closing the
workbook** (`OfficeRuntime.storage`) — reopening never re-runs the LLM on unchanged cells.

**Use — task pane** (Excellia button, Home tab): validate / transform (preview→apply) /
name-match / categorise / summarise / **chat** (select a range including the header row, ask a
question — answer + evidence table) on the current selection; writes only to an empty adjacent
column, never over data.

---

## 6. Tests

```powershell
pytest                                    # fast, no network, no Ollama
$env:EXCELLIA_RUN_MCP_IT = "1"; pytest    # + live MCP stdio round-trip
$env:EXCELLIA_BIG = "1"; pytest           # + 500K-row memory-budget test (~90s)
```

## 7. Troubleshooting (the short list)

| Symptom | Fix |
|---|---|
| "Excellia core API is not running…" | Auto-spawn failed — run `excellia-api` in a terminal, read its logs, retry. |
| Claude Desktop shows no tools | Full quit from system tray; config must use the absolute `.exe` path, backslashes escaped. |
| Agent: "Model 'X' cannot call tools" | `ollama pull qwen2.5:7b` or set `EXCELLIA_AGENT_MODEL`. |
| "File not found: X" | Use absolute paths — MCP hosts don't share your shell's cwd. |
| MCP tool calls hang on Windows | Use the packaged entry points — `excellia-mcp` spawns the API detached; inline children hang. |
