# Running Excellia — every way that works today

> Status: Stage D (`v0.6.0-addin`). What exists: the core engine (incl. fraud scoring,
> reconciliation pro, KYC), the core API (job queue + workspace CRUD + upload + `/values/*`),
> the **web app at http://127.0.0.1:8000/app/**, the **Excel add-in** (`=XAI.*` formulas +
> task pane over HTTPS), the thin MCP server (19 tools + resources), and the offline Ollama
> agent. Paths below are Windows-style because that's the dev machine; everything also runs on
> Linux/macOS (swap `.venv\Scripts\` for `.venv/bin/` and drop `.exe`).

The tools, whichever door you enter through:

| Tool | What it does |
|---|---|
| `profile_sheet` | Row/column counts, inferred types, null rates, stats, auto-detected formats (GST/PAN/Aadhaar/email/phone/IFSC) |
| `validate` | Deterministic rule checks — rulesets: `default`, `kyc`, `invoice`, `payroll`, `bank-statement` + your saved ones |
| `detect_anomalies` | Isolation Forest + column outliers + rare categories + near-duplicates, each with a reason |
| `reconcile` | Match two files by key columns; tolerances for amounts, date windows, fuzzy names |
| `ask_data` * | Question → query plan → pandas computes → answer WITH evidence table (never invents numbers) |
| `transform_preview` * | Instruction → recipe + before/after sample; changes nothing |
| `transform_apply` | Apply a recipe → NEW file, `_ai`-suffix columns by default; `save_as` persists the recipe |
| `run_recipe` | Replay a saved recipe on a new file |
| `save_ruleset` | Save a custom validation ruleset |
| `export_report` | Highlighted xlsx + Data Health Score with breakdown |
| `job_status` | Poll big-file jobs started with `async_=true` |
| `train_fraud_model` | Labelled file → model + honest CV-metrics ModelCard; refuses on leakage/too-few-rows |
| `score_fraud` | Fresh file → per-row probability, risk band, top factors |
| `evaluate_fraud_model` | Labelled holdout → real-world accuracy vs training metrics |
| `list_fraud_models` | All saved ModelCards |
| `save_reconciliation_profile` / `run_reconciliation_profile` | Saved profile → pre-clean, dedupe, match (L1/L2/L3), 5-sheet xlsx report |
| `match_names` * (only with llm_verify) | KYC name matching: deterministic similarity + optional offline-LLM verdicts |
| `dedupe_rows` | Entity dedupe: clusters, canonical rows, merge log, new file |

Tools marked * need a local Ollama running; the rest are pure deterministic code.
Row numbers everywhere are Excel rows: header = 1, first data row = 2.
Demo file with seeded errors: `examples/messy_vendors.xlsx`.
Saved rulesets/recipes and the audit trail live in `~/.excellia/` (`EXCELLIA_HOME` to move it).

---

## 0. One-time setup

```powershell
cd "C:\Users\anura\Documents\04 PROJECT MAIN\11 Excellia Core\excellia_codebase"
python -m venv .venv                # skip if .venv already exists
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Verify the install — all three entry points should resolve:

```powershell
Get-Command excellia-mcp, excellia-api, excellia-agent
pytest    # 172 passed, 2 skipped (opt-in slow tests)
```

> Honest timing: from a bare venv this takes ~2.5 min (pandas/scipy/scikit-learn wheels).
> With scientific Python already present it's seconds.

You never need to start the API by hand for the MCP routes — `excellia-mcp` spawns it
automatically (detached, on Windows) when the first tool call finds it down.

---

## Way 1 — Claude Desktop (cloud brain, local data)

1. Open Claude Desktop → **Settings → Developer → Edit Config** (opens `claude_desktop_config.json`).
2. Add the server. The exe lives inside the project venv, so use the **absolute path**:

```json
{
  "mcpServers": {
    "excellia": {
      "command": "C:\\Users\\anura\\Documents\\04 PROJECT MAIN\\11 Excellia Core\\excellia_codebase\\.venv\\Scripts\\excellia-mcp.exe"
    }
  }
}
```

3. **Fully restart** Claude Desktop — quit from the system tray; closing the window is not a restart.
4. Ask (absolute paths work best):

> Profile "C:\Users\anura\Documents\04 PROJECT MAIN\11 Excellia Core\excellia_codebase\examples\messy_vendors.xlsx" and tell me what's wrong with it.

Privacy note: file contents and all computation stay on your machine. What Anthropic sees:
your prompt, the file *path*, and the tool *results* (counts, flagged rows, reasons). If the
findings themselves are sensitive, use Way 3.

## Way 2 — Claude Code (this CLI)

Register the same server once:

```powershell
claude mcp add excellia "C:\Users\anura\Documents\04 PROJECT MAIN\11 Excellia Core\excellia_codebase\.venv\Scripts\excellia-mcp.exe"
```

From the next session on, Claude Code can call the four tools directly
(`claude mcp list` to confirm, `claude mcp remove excellia` to undo).

## Way 3 — Fully offline: Ollama agent (zero bytes leave the machine)

Needs [Ollama](https://ollama.com) running with a **tool-capable** model:

```powershell
ollama pull qwen2.5:7b     # the recommended, verified-class model
```

Then, with the venv activated:

```powershell
excellia-agent                                       # interactive REPL
excellia-agent check examples\messy_vendors.xlsx     # one-shot check
```

- The agent auto-picks an installed model; pin one explicitly with
  `$env:EXCELLIA_AGENT_MODEL = "qwen2.5:7b"` before launching.
- Non-default Ollama location: set `OLLAMA` host via the agent's env (default `http://127.0.0.1:11434`).
- If the picked model can't call tools, the agent says so and names the fix — it won't fail silently.

Same unchanged `server.py` as Ways 1–2. That's the thesis.

## Way 4 — The web app (point and click)

The API serves a full web UI from the same process — no second server, no build step:

```powershell
excellia-api        # then open http://127.0.0.1:8000/app/
```

Drag-drop a spreadsheet (or paste a local path) in the sidebar, then use the views:
**Quality** (profile/validate/anomalies + health-score report) · **Ask the data** (answer +
evidence + query plan) · **Transform** (preview → confirm → recipes) · **Reconcile** (profiles,
match-level tabs, 5-sheet report) · **Fraud** (train/score/evaluate) · **KYC** (name match,
dedupe) · **Jobs & History**. The web layer owns zero logic — every button is one HTTP call to
the endpoints below.

## Way 5 — Core API directly (no AI at all)

For scripts, curl, or wiring up your own client:

```powershell
excellia-api        # uvicorn on http://127.0.0.1:8000 — keeps logs in the foreground
```

Interactive docs at http://127.0.0.1:8000/docs — the full surface lives there. Highlights:
sync analysis (`/profile /validate /anomalies /reconcile /ask /clean /transform/preview
/transform/apply /report`), domain suites (`/fraud/train|score|evaluate|models`,
`/reconcile/profiles` CRUD + `/reconcile/run`, `/kyc/match_names /kyc/dedupe`), workspace CRUD
(`/rulesets /recipes /history`), and the job queue (`POST /jobs {op, params}` → poll
`GET /jobs/{id}`) for big files. Core examples:

```powershell
# health
curl http://127.0.0.1:8000/health

# available rulesets
curl http://127.0.0.1:8000/rulesets

# profile a sheet                          body: {file, sheet?}
curl -X POST http://127.0.0.1:8000/profile -H "Content-Type: application/json" `
     -d '{"file": "C:/.../examples/messy_vendors.xlsx"}'

# validate                                 body: {file, ruleset?, sheet?}
curl -X POST http://127.0.0.1:8000/validate -H "Content-Type: application/json" `
     -d '{"file": "C:/.../examples/messy_vendors.xlsx", "ruleset": "kyc"}'

# anomalies                                body: {file, contamination?, sheet?}   (0 < contamination < 0.5)
curl -X POST http://127.0.0.1:8000/anomalies -H "Content-Type: application/json" `
     -d '{"file": "C:/.../examples/messy_vendors.xlsx", "contamination": 0.05}'

# reconcile two files                      body: {a, b, keys, tolerance?}
curl -X POST http://127.0.0.1:8000/reconcile -H "Content-Type: application/json" `
     -d '{"a": "C:/.../file_a.xlsx", "b": "C:/.../file_b.xlsx", "keys": ["invoice_id"]}'
```

Forward slashes in JSON paths save you double-backslash escaping. Optional string params
tolerate `"null"`/`"none"`/`""` and treat them as absent (a courtesy to sloppy local LLMs
that also helps humans).

## Way 6 — The Excel add-in (Windows AND Mac)

The `=XAI.*` formula family plus a task pane, one Office.js manifest for both platforms.
Needs the HTTPS server (Office panes refuse plain HTTP):

```powershell
pip install excellia[addin]     # one-time: adds the certificate library
excellia-addin                  # mints a localhost cert, asks before trusting it,
                                # prints sideload steps, serves https://localhost:8443
```

Sideload (one time — `excellia-addin` prints these too):
- **Windows**: copy `excellia/addin/static/manifest.xml` to a shared folder, add that folder
  under Excel → Options → Trust Center → Trusted Add-in Catalogs, restart Excel,
  Insert → My Add-ins → Shared Folder → Excellia.
- **macOS**: copy `manifest.xml` to `~/Library/Containers/com.microsoft.Excel/Data/Documents/wef/`,
  restart Excel, Insert → My Add-ins → Excellia.

Then in any cell:

```
=XAI.VALIDATE(C2:C99, "pan")        deterministic format check — zero AI
=XAI.MATCH(A2, B2)                  KYC name similarity 0–100
=XAI.RUN(A2:A99, "extract pin")     per-cell AI transform (needs Ollama)
=XAI.TAG(B2:B99, "corporate?")      Yes/No classification (needs Ollama)
=XAI.SPLIT(A2, "street|city|pin")   spills parts across columns (needs Ollama)
=XAI.ASK("total per city?", A1:D99) answer computed from the range, never invented
```

Formulas batch into one API call per calc pass and cache per (value, prompt) — recalcs don't
re-run the LLM. The task pane (Excellia button, Home tab) does validate/transform/name-match on
the selection, writing only to an empty adjacent column. Air-gap caveat: Office.js itself loads
from Microsoft's CDN on first use and is then cached by Office.

## Way 7 — Any other MCP host

Any MCP-capable host (Cursor, Windsurf, VS Code MCP, a raw stdio client, …) can use the
server: configure a **stdio** server whose command is the absolute path to
`.venv\Scripts\excellia-mcp.exe`, no args, no ports. The opt-in live integration test shows
a minimal raw client:

```powershell
$env:EXCELLIA_RUN_MCP_IT = "1"; pytest tests/test_mcp_integration.py -v
```

---

## Running the tests

```powershell
pytest                                    # 239 tests, fast, no network, no Ollama needed
$env:EXCELLIA_RUN_MCP_IT = "1"; pytest    # + the live MCP stdio round-trip
$env:EXCELLIA_BIG = "1"; pytest           # + the 500K-row memory-budget test (~90s)
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tool returns "Excellia core API is not running. Start it with `excellia-api`." | The auto-spawn failed — run `excellia-api` in a terminal and retry (its logs will say why). |
| Claude Desktop doesn't show the tools | Full quit from the system tray and relaunch; check the config path is the absolute `.exe` path with escaped backslashes. |
| Agent: "Model 'X' cannot call tools" | `ollama pull qwen2.5:7b` or set `EXCELLIA_AGENT_MODEL` to a tool-capable model. |
| "File not found: X" | Use an absolute path — MCP hosts don't share your shell's working directory. |
| Every MCP tool call hangs (Windows) | Don't run the API as an inline child of the MCP server — the packaged `excellia-mcp` already spawns it detached; use the entry points, not ad-hoc scripts. |

## What you can't do yet (so you don't go looking)

No chat inside the Excel task pane yet (use the web app's Ask view), no bulk multi-file mode
in the web app, formula cache doesn't survive closing the workbook, and no OCR (deliberately
deferred optional extra). Everything else — validation, anomalies, ask, transform, reports,
fraud, reconciliation profiles, KYC, the web UI, and the `=XAI.*` formulas — is live.
Status in [`EXCELLIA_FEATURES.md`](../EXCELLIA_FEATURES.md) §1.
