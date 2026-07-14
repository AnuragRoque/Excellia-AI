# Excellia

Point it at Claude for convenience, or at your own Ollama for a fully air-gapped deployment — your data never leaves either way; the only difference is where the reasoning happens.

Excellia is a spreadsheet validation engine exposed as an MCP server. Any AI agent — cloud or fully offline — can profile, validate, anomaly-check, and reconcile Excel/CSV files without a single row leaving your machine.

## Install

```bash
pip install excellia        # from source today: pip install -e .
```

One command. If you already work in Python data tooling (pandas + scikit-learn present), it
resolves in seconds; a bare virtualenv has to download the scientific stack first, which takes
a couple of minutes. Then setup is trivial: paste one config block, restart your host — no ports,
no services to manage. The MCP server starts the core API itself when a tool is first called
(or run `excellia-api` in a terminal to keep it warm and watch its logs).

### Brain 1 — Claude Desktop (convenient)

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "excellia": {
      "command": "excellia-mcp"
    }
  }
}
```

Try: *"Profile examples/messy_vendors.xlsx and tell me what's wrong with it."* (use an absolute path).

### Brain 2 — fully offline (regulated / air-gapped)

Needs [Ollama](https://ollama.com) with a tool-capable model (e.g. `ollama pull qwen2.5:7b`):

```bash
excellia-agent                                # interactive REPL
excellia-agent check C:\data\vendors.xlsx     # one-shot
```

Same MCP server, zero code changes between the two brains. That is the point.

## Four tools

| Tool | What it does |
|---|---|
| `profile_sheet` | Row/column counts, inferred types, null rates, stats, auto-detected formats |
| `validate` | Deterministic rule checks: required fields, GST/PAN/Aadhaar/email/phone/IFSC formats, ranges, duplicates, mixed types |
| `detect_anomalies` | Isolation Forest + column outliers + rare categories + near-duplicates + pattern breaks — every flag has a confidence and a reason |
| `reconcile` | Match two spreadsheets by key columns; tolerances for amounts, date windows, fuzzy names; four buckets incl. field-level discrepancies |

Row numbers everywhere are Excel rows: header is row 1, data starts at row 2.

## Architecture

```
AI host (Claude Desktop or excellia-agent + Ollama)
        │ MCP (stdio)
  MCP server        ← thin adapter, zero logic
        │ HTTP (localhost)
  Core API (FastAPI)
        │
  Core engine (pure Python + pandas + scikit-learn)
```

The MCP server contains zero validation logic. Everything lives once, in the core. The full product
roadmap (fraud scoring, KYC matching, reconciliation profiles, web app, Excel add-in with `=XAI()`
formulas) lives in [EXCELLIA_FEATURES.md](EXCELLIA_FEATURES.md).

## Privacy — the honest version

Using Claude Desktop: the .xlsx file, every row, all pandas/ML processing stay local. What goes to Anthropic: your prompt, the file *path*, and whatever the tools *return* (violation counts, flagged rows, reasons). Findings can themselves be sensitive — for regulated production, use `excellia-agent` with Ollama instead: same server, different brain, zero bytes leave the machine.

## Development

```bash
pip install -e .[dev]
pytest          # 70 tests
```

## Status

Stage A (working MCP loop) — see [EXCELLIA_FEATURES.md](EXCELLIA_FEATURES.md) for the live status board and [EXCELLIA_MCP_PLAN.md](EXCELLIA_MCP_PLAN.md) for the original thesis.
