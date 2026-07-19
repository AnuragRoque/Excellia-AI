# Excel add-in — `excellia/addin/`

Excellia inside Excel: the **`=XAI.*` custom-formula family** plus a **task-pane copilot**. One
Office.js manifest works on Windows and Mac. No Node, no proxy — `excellia-addin` serves the
same FastAPI app (API + add-in files) over **https://localhost:8443** with a self-signed
localhost certificate (Office panes refuse plain HTTP), so everything shares one origin.

## Run

```bash
pip install -e .[addin]     # one-time: adds the certificate library
excellia-addin              # mints the cert, asks consent before trusting it,
                            # prints the sideload steps, serves https://localhost:8443
```

## Sideload (one time — `excellia-addin` prints these too)

- **Windows:** copy `excellia/addin/static/manifest.xml` to a shared folder → Excel → Options →
  Trust Center → Trusted Add-in Catalogs → add that folder → restart Excel → Insert →
  My Add-ins → Shared Folder → Excellia.
- **macOS:** copy `manifest.xml` to
  `~/Library/Containers/com.microsoft.Excel/Data/Documents/wef/` → restart Excel → Insert →
  My Add-ins → Excellia.

## Mode 1 — formulas

```
=XAI.VALIDATE(C2:C99, "pan")        deterministic format check (pan|gst|email|ifsc|aadhaar|phone) — zero AI
=XAI.MATCH(A2, B2)                  KYC name similarity 0–100 (broadcasts 1-vs-N)
=XAI.RUN(A2:A99, "extract pin")     per-cell AI transform (needs Ollama)
=XAI.TAG(B2:B99, "corporate?")      Yes/No classification (needs Ollama)
=XAI.SPLIT(A2, "street|city|pin")   splits into parts — spills across columns (needs Ollama)
=XAI.ASK("total per city?", A1:D99) one-cell answer computed from the range, never invented
```

Engineering that keeps this usable:

- **Batching:** cells coalesce into ONE API request per (function, prompt) per calc pass.
- **Caching:** results are cached per (value, prompt); LLM-derived results persist to
  `OfficeRuntime.storage` and **survive closing and reopening the workbook** — a recalc never
  re-runs the LLM on unchanged cells. Deterministic kinds recompute (cheap).
- Errors surface as `#VALUE!` with the API's instructive message attached.

## Mode 2 — task pane (Excellia button, Home tab)

Operations on the current selection: **Validate formats** · **Transform** (preview → apply) ·
**Name match** · **Categorise** · **Summarise** · **Chat** (select a range including the header
row, ask a question — answer + evidence table).

Non-destructive always: the pane writes **only to an empty adjacent column** (and refuses,
instructively, if there isn't one). AI-written cells get a visual accent so you always know
what the model touched.

## Files

- `serve.py` — the HTTPS server + certificate minting + printed sideload steps (`excellia-addin`)
- `static/manifest.xml` — the one Office.js manifest (Windows + Mac)
- `static/functions.js` / `functions.json` — the `=XAI.*` implementations and metadata
- `static/taskpane.html` / `taskpane.js` — the pane

## Rules & caveats

- The add-in is a face: **zero logic** (test-enforced) — formulas and pane call the API's
  `/values/*` endpoints; all computation is in `core/`.
- Nothing in Excel ever talks straight to Ollama — the API is the only door.
- Air-gap caveat: Office.js itself loads from Microsoft's CDN on first use (then cached by
  Office). That is Office's requirement, not ours.
