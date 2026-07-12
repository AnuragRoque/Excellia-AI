# Excellia

Point it at Claude for convenience, or at your own Ollama for a fully air-gapped deployment — your data never leaves either way; the only difference is where the reasoning happens.

Excellia is a spreadsheet validation engine exposed as an MCP server. Any AI agent — cloud or fully offline — can profile, validate, anomaly-check, and reconcile Excel/CSV files without a single row leaving your machine.

## Four tools

| Tool | What it does |
|---|---|
| `profile_sheet` | Row/column counts, inferred types, null rates, stats |
| `validate` | Deterministic rule checks: required fields, GST/PAN/email/IFSC formats, ranges, duplicates |
| `detect_anomalies` | Isolation Forest + statistical outliers, with confidence scores and reasons |
| `reconcile` | Match two spreadsheets by key columns; tolerances for dates, amounts, fuzzy names |

## Architecture

```
AI host (Claude Desktop or local Ollama agent)
        │ MCP (stdio)
  MCP server        ← thin adapter, no logic
        │ HTTP
  Core API (FastAPI)
        │
  Core engine (pure Python + pandas)
```

The MCP server contains zero validation logic. Everything lives once, in the core.

## Install

```
pip install excellia
```

Start the core API:

```
excellia-api
```

Add to Claude Desktop config:

```json
{
  "mcpServers": {
    "excellia": {
      "command": "excellia-mcp"
    }
  }
}
```

## Privacy — the honest version

Using Claude Desktop: the .xlsx file, every row, all pandas/ML processing stay local. What goes to Anthropic: your prompt, the file *path*, and whatever the tools *return* (violation counts, flagged rows, reasons). Findings can themselves be sensitive — for regulated production, use the bundled offline agent (`local_agent/`) with Ollama instead. Same server, different brain, zero code changes.

## Status

Under active development — Phase 1 (core extraction) in progress. See [EXCELLIA_MCP_PLAN.md](EXCELLIA_MCP_PLAN.md).
