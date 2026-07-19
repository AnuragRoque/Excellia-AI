# Web app — `excellia/webapp/`

The point-and-click face for big and bulk files. A **static single-page app served by the core
API itself** at `http://127.0.0.1:8000/app/` — vanilla JS, no build step, no Node, no second
server. It owns **zero logic** (test-enforced): every button is exactly one HTTP call to the
core API.

## Run

Nothing extra — it ships inside the API process:

```bash
excellia-api        # then open http://127.0.0.1:8000/app/
```

## Use

Drag-drop a spreadsheet (or paste a local path) in the sidebar, then:

| View | What it does |
|---|---|
| **Quality** | Profile + validate (ruleset picker) + anomalies; health score with breakdown; highlighted-report export |
| **Ask the data** | A chat thread — every answer carries its evidence rows and the query plan that actually ran |
| **Transform** | Instruction → recipe → before/after preview → confirm apply (replace opt-in, save-as-recipe) → replay saved recipes |
| **Reconcile** | File B + keys/tolerances or a saved profile; four bucket tabs with L1/L2/L3 badges; 5-sheet report |
| **Fraud** | Train (metrics card + top features) · score (risk bands, per-row factors) · evaluate (holdout vs CV) |
| **KYC** | Name matching (pairwise/cross, optional offline-LLM verify) and entity dedupe with merge log |
| **Bulk** | One operation × many files — each file becomes ONE background job; live status matrix with per-file results |
| **Jobs & History** | Job polling + the append-only audit trail |

Two always-available sidebar features:

- **💬 Chat** — the same conversation as the Ask view, reachable from every view. Same engine,
  same evidence, one `POST /ask` per message.
- **Big file mode** — heavy operations route through `POST /jobs` and are polled, so the page
  never hangs on one long request. Use for 100K+ row files (a 500K-row run is live-verified:
  profile 3s · validate 5s · transform 4.3s · report ~4min, page responsive throughout).

Uploads land in the workspace `uploads/` dir; your original files are never touched.

## Files

- `index.html` — the shell (sidebar, file picker, chat, view container)
- `app.js` — all views; a `call()` helper transparently routes POSTs through the job queue when
  Big file mode is on and resolves to the sync endpoint's exact result shape
- `styles.css` — near-black panels, pink→periwinkle gradient for AI actions, serif numerals

## The rule

**Nothing computes here.** No pandas, no maths beyond rendering, no decisions. If a feature
needs computation, it goes in `core/` and gets an API endpoint first
(`tests/test_webapp.py::test_webapp_owns_zero_logic` enforces this). Vanilla JS is a deliberate
choice — graduate to React only if the UI outgrows it (decision log:
[EXCELLIA_FEATURES.md](../../EXCELLIA_FEATURES.md) §11).
