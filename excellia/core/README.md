# Core engine — `excellia/core/`

The crown jewel. **All** the logic lives here, once, as pure Python — no HTTP, no GUI, no MCP
imports (enforced by `tests/test_imports.py`). Every other component in this repo is a client of
this package.

## Use it as a library

```python
import pandas as pd
from excellia.core import ingest, validate, anomaly, reconcile, report

df = ingest.load("examples/messy_vendors.xlsx")
profile = ingest.profile(df)                     # types, null rates, stats, formats
issues  = validate.run(df, ruleset="default")    # Issue objects with row/col/reason
flags   = anomaly.detect(df)                     # Flag objects with confidence/reason
```

No server needed — the API/MCP/web/add-in layers are conveniences on top of these functions.

## The modules

| Module | One job |
|---|---|
| `ingest.py` | Robust load (encodings, delimiter sniffing, fake-parse rejection), the profiler (type inference, null rates, stats, GST/PAN/Aadhaar/email/phone/IFSC format detection), and chunked streaming for big files (`iter_chunks`, `profile_large`, `validate_large`) |
| `validate.py` | Declarative ruleset engine + auto-inferred checks (format violations, duplicate IDs/rows, missing values, mixed types); `check_format` for single values |
| `anomaly.py` | Isolation Forest with per-feature explanations, IQR outliers, rare categories, near-duplicates, pattern breaks |
| `reconcile.py` | Two-file matching: four buckets, numeric/date/fuzzy tolerances, L1/L2/L3 match levels, variance columns, saved profiles with pre-clean and dedupe steps |
| `clean.py` | 16 deterministic cleaning ops (trim/case/replace/split/concat/dates/currency/dedupe/…) — the recipe atoms; every op is `{op, params}` JSON |
| `ask.py` | Chat that cannot lie: LLM plans strict-JSON → a whitelisted pandas executor computes → answer + evidence table + the plan |
| `transform.py` | Instruction → recipe → preview on a sample → apply to a NEW file (`_ai` columns unless `replace=True`); recipes save and replay deterministically |
| `fraud.py` | Supervised fraud scoring: train/score/evaluate with ModelCards, cross-validated metrics, leakage detection, per-row top factors, drift refusal |
| `kyc.py` | Hybrid name matching (deterministic similarity + optional offline-LLM verdicts) and entity dedupe with merge logs |
| `report.py` | Highlighted xlsx reports, Data Health Score with breakdown, the 5-sheet reconciliation report |
| `store.py` | The workspace (`~/.excellia/`, `EXCELLIA_HOME` to move it): rulesets/recipes/profiles/models CRUD + the append-only `history.jsonl` audit trail |
| `llm.py` | **The only LLM door.** Stdlib-urllib Ollama client, strict-JSON contract with one repair reprompt and a typed fallback. No other module talks to a model |
| `models.py` / `rules/` | `Issue`/`Flag`/`Profile`/… dataclasses and the compiled format regexes |

## The rules (never violate)

1. **Purity:** `core/` never imports from `api/`, `mcp_server/`, `local_agent/`, or any face.
   Dependencies point inward. Test-enforced.
2. **Deterministic-first:** if regex/pandas/sklearn can do it, the LLM must not. The LLM
   proposes and explains; deterministic code executes and counts.
3. **One LLM door:** every model call goes through `llm.py`. Never a raw `json.loads` of model
   output outside it.
4. **Row convention:** every reported row number is an Excel row — header = 1, data starts at 2.
5. **Non-destructive:** nothing overwrites user data; applies write NEW files.
6. **Explainability:** every Issue/Flag/score/match carries a human-readable `reason`.

Tested by the bulk of the repo's suite (`pytest` from the repo root).
