# Contributing to Excellia

Thanks for looking under the hood. Excellia is opinionated — most review comments are one of the
architecture rules below, so reading this first saves everyone a round-trip.

## Setup

```bash
git clone <this repo> && cd excellia_codebase
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e .[dev]
pytest                                          # must pass before and after your change
```

Opt-in slow tests: `EXCELLIA_RUN_MCP_IT=1 pytest` (live MCP stdio round-trip),
`EXCELLIA_BIG=1 pytest` (500K-row memory budget, ~90s).

## The architecture rules (PRs are reviewed against these)

1. **Placement:** computes → `core/` · waits/queues/stores → `api/` · describes a tool to a
   model → `mcp_server/` · renders pixels → a face (`webapp/`, `addin/`). When unsure: if it
   needs pandas it's core; if it needs a socket it's api.
2. **Core purity:** `core/` imports nothing from the outer layers. Test-enforced
   (`tests/test_imports.py`) — don't fight the test, move the code.
3. **Thin MCP server:** one tool = one docstring + one HTTP forward. If `server.py` needs
   pandas, stop and refactor. Docstrings follow the checklist in `EXCELLIA_FEATURES.md` §12
   (trigger words · inputs/defaults · output keys + Excel-row convention · failure next-step).
4. **Faces own zero logic.** Every button is one HTTP call (test-enforced for both faces).
5. **Deterministic-first:** if regex/pandas/sklearn can do it, the LLM must not. All LLM calls
   go through `core/llm.py` — never a raw `json.loads` of model output anywhere else.
6. **Non-destructive:** never overwrite user data. Applies write new files; the add-in writes
   to empty adjacent columns; transforms preview before apply.
7. **Excel row numbers** in every user-facing row reference (header = 1, data starts at 2).
8. **Instructive errors:** name the problem, the fix, and the alternative tool. Error strings
   are part of the interface and are asserted in tests — update the tests with the strings.
9. **Privacy:** no code path may leave the machine. No new network calls, no telemetry.
   Anything cloud must be a loudly-named opt-in extra, and discussed in an issue first.

Decisions already made (don't relitigate without new evidence): `EXCELLIA_FEATURES.md` §11.
Deliberate non-features (don't PR them): §7.

## Practical notes

- Tests accompany every behaviour change; the suite is fast, offline, and needs no Ollama —
  LLM paths are tested with fake transports (see `tests/test_llm.py` for the pattern).
- `pathlib` everywhere; the code runs on Windows, Linux, and macOS.
- Keep PRs one-topic. Update `CHANGELOG.md` under *Unreleased*.
- Big features: open an issue first — the roadmap in `EXCELLIA_FEATURES.md` is staged
  deliberately, and a great feature at the wrong layer will be asked to move.
