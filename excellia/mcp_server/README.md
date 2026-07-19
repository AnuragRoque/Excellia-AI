# MCP server — `excellia/mcp_server/`

The AI door. A thin stdio MCP server exposing **19 tools** and `ruleset:// recipe:// profile://`
resources so that any MCP-capable host — Claude Desktop, Claude Code, Cursor, Windsurf, VS Code,
or the bundled offline agent — can drive the engine.

**It contains zero logic.** No pandas, no computation — every tool forwards one HTTP call to the
core API (and auto-spawns the API, detached, if it isn't running). If this file ever imports
pandas, the architecture has failed.

## Hook it up

You never run it directly — an MCP host launches it over stdio. Point the host at the
`excellia-mcp` entry point (use the **absolute path** into your venv), no args, no ports.

**Claude Desktop** — `claude_desktop_config.json` (Settings → Developer → Edit Config), then a
full restart (quit from the system tray):

```json
{
  "mcpServers": {
    "excellia": { "command": "C:\\path\\to\\excellia_codebase\\.venv\\Scripts\\excellia-mcp.exe" }
  }
}
```

**Claude Code:**

```bash
claude mcp add excellia "C:\path\to\excellia_codebase\.venv\Scripts\excellia-mcp.exe"
```

**Any other host:** same idea — stdio transport, absolute command path.

**Offline:** `excellia-agent` (see [../local_agent/README.md](../local_agent/README.md)) drives
this exact server with a local Ollama model — same tools, zero changes.

Then ask, in the host: *"Profile C:\data\vendors.xlsx and tell me what's wrong with it."*
(absolute paths — MCP hosts don't share your shell's working directory).

## The tools

Analysis: `profile_sheet` · `validate` · `detect_anomalies` · `reconcile` · `ask_data` —
transform: `transform_preview` · `transform_apply` · `run_recipe` — fraud:
`train_fraud_model` · `score_fraud` · `evaluate_fraud_model` · `list_fraud_models` —
reconciliation pro: `save_reconciliation_profile` · `run_reconciliation_profile` — KYC:
`match_names` · `dedupe_rows` — plumbing: `save_ruleset` · `export_report` · `job_status`
(heavy tools accept `async_=true` and return a job id).

Full one-line-per-tool table: the top of [docs/RUNNING.md](../../docs/RUNNING.md).

## Design rules

- **Thin forever.** One tool = one API call. The server stays well under ~300 lines.
- **Docstrings are the interface** — written for the model, not for humans: trigger words,
  inputs and defaults, output keys (Excel row convention), and what to do on failure.
- **Instructive errors**, never stack traces: "Excellia core API is not running. Start it with
  `excellia-api`."
- Windows hard-won fix (do not regress): the auto-spawned API must be **detached**
  (`DETACHED_PROCESS`, DEVNULL stdio) — an inline child inherits the host's JSON-RPC pipes and
  hangs every tool call. Guarded by `tests/test_mcp_integration.py`.

Live round-trip test (opt-in): `EXCELLIA_RUN_MCP_IT=1 pytest tests/test_mcp_integration.py -v`
