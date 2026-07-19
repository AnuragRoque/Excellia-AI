# Security & threat model

Excellia's core promise is **locality**: your spreadsheets, the computation on them, and (in
offline mode) even the AI reasoning never leave your machine. This document says exactly what
that means, what each deployment mode exposes, and where the edges are.

## Network surface

The only sockets Excellia opens are **loopback**:

| Socket | Who | Purpose |
|---|---|---|
| `127.0.0.1:8000` (HTTP) | `excellia-api` | Core API + web app |
| `localhost:8443` (HTTPS, self-signed) | `excellia-addin` | Same app, TLS for Office panes |
| `127.0.0.1:11434` (HTTP, outbound) | `core/llm.py` → Ollama | The only LLM door |
| stdio (no socket) | `excellia-mcp` | MCP transport to the host |

No code path calls out to the internet. There is no telemetry, no update check, no cloud LLM,
no cloud OCR. Anything cloud would be a loudly-named opt-in extra, never a default (see
`EXCELLIA_FEATURES.md` §7) — none exist today.

**Known exception (not our code):** Office.js, the Microsoft library the Excel add-in must use,
is loaded from Microsoft's CDN by Excel on first use and then cached. The add-in's own logic and
all data stay local.

## What each AI host sees

| Mode | Leaves the machine |
|---|---|
| Claude Desktop / Claude Code / any cloud MCP host | Your **prompt**, the file **path**, and **tool results** — counts, flagged rows, reasons, summaries. Never the file, never raw rows beyond what a tool explicitly returns (e.g. an evidence table you asked for). |
| `excellia-agent` + Ollama | **Nothing.** Model, data, and computation are all local. |
| Web app / add-in / raw API | Nothing — no AI host involved; LLM features go to local Ollama. |

Tool results can themselves be sensitive (an evidence table *contains data rows*). If that
matters for your data, use the offline agent — it exists precisely for this.

## What's stored, and where

Everything lands under `~/.excellia/` (`EXCELLIA_HOME` to relocate): saved rulesets, recipes,
reconciliation profiles, fraud models, uploads from the web app, job results, and the
append-only `history.jsonl` audit trail. Notes:

- **Fraud ModelCards store metrics, feature names, and a schema fingerprint (a hash of column
  *names*) — never your data.** The `.joblib` pipeline, like any fitted sklearn model, encodes
  learned parameters derived from training data; treat saved models with the same sensitivity
  as the data they were trained on.
- `history.jsonl` records operations, parameters, and file *fingerprints* — not file contents.
- Original files are never modified; every apply/export writes a new file.

## Trust boundaries & deliberate limitations

- **No auth, localhost only (v1).** The API binds to `127.0.0.1` and assumes a single analyst
  on a trusted machine. Do **not** rebind it to `0.0.0.0` or port-forward it — there is no
  authentication layer to protect you if you do.
- **Local processes can talk to it.** Anything running on your machine can call
  `127.0.0.1:8000`. That is the standard posture of local dev tools (Ollama itself works the
  same way), but it's worth knowing.
- **The add-in's certificate** is a self-signed cert for `localhost`, minted locally and
  trusted only with your explicit consent. It is not a CA and cannot sign anything else.
- **Prompt-injection surface:** cell values and file contents are untrusted input that reaches
  a model in `ask`/`transform`/LLM-verify paths. Mitigation is architectural: the model's
  output is never executed — it's parsed against a strict JSON schema and run through a
  whitelisted plan executor / recipe registry. A hostile spreadsheet can waste a model's time;
  it cannot make Excellia run arbitrary code or fabricate numbers (all arithmetic is pandas).
- **`df.eval` expression rules:** custom validation rulesets may contain pandas expressions
  authored by *you*. Rulesets are config on your own machine — treat third-party ruleset files
  like you'd treat any script someone sends you.

## Reporting a vulnerability

Open a GitHub issue for anything that doesn't reveal an exploitable detail, or email
**anuragsingh2445@gmail.com** for anything sensitive. Please include reproduction steps.
You'll get a response as fast as a one-maintainer project honestly can — usually within a few
days.
