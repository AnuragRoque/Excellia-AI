# Core API — `excellia/api/`

The single HTTP door to the engine. FastAPI on `http://127.0.0.1:8000`. Every other face — web
app, Excel add-in, MCP server — is a client of this. It owns everything that *waits, queues,
stores, or uploads*; it computes nothing (every endpoint calls exactly one core function).

## Run

```bash
excellia-api          # uvicorn on http://127.0.0.1:8000, logs in the foreground
```

- Interactive docs (the full surface): http://127.0.0.1:8000/docs
- The web app is served by this same process at http://127.0.0.1:8000/app/
- You usually don't start it by hand for AI use — `excellia-mcp` auto-spawns it.

## Surface

```
# sync analysis (small files)
GET  /health                       POST /profile        POST /validate
POST /anomalies                    POST /reconcile      POST /ask
POST /clean                        POST /transform/preview
POST /transform/apply              POST /report
POST /kyc/match_names              POST /kyc/dedupe
POST /fraud/train                  POST /fraud/score    POST /fraud/evaluate

# workspace CRUD
GET/POST/DELETE /rulesets[/{name}]      /recipes[/{name}]
GET/POST/DELETE /reconcile/profiles[/{name}]     POST /reconcile/run
GET /fraud/models    GET /history    POST /upload (multipart)

# async (big files / slow ops)
POST /jobs {op, params} -> {job_id}
GET  /jobs/{id} -> {status: queued|running|done|error, result?, error?}
GET  /jobs -> list

# the add-in's formula door (single values / small ranges)
POST /values/validate  /values/similarity  /values/map  /values/split  /values/ask
```

Quick smoke:

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/profile -H "Content-Type: application/json" \
     -d '{"file": "C:/path/to/examples/messy_vendors.xlsx"}'
```

Forward slashes in JSON paths save you double-backslash escaping on Windows. Optional string
params tolerate `"null"`/`"none"`/`""` and treat them as absent (a courtesy to sloppy local
LLMs that also helps humans).

## Key files

- `main.py` — the app: routes, upload door, static mounts for `/app` and the add-in, `serve()`
  entry point
- `jobs.py` — the background job queue (ThreadPool, results parked in the workspace `jobs/` dir)
- `schemas.py` — request/response models

## Rules

- **Zero logic.** If an endpoint needs pandas, the code belongs in `core/` — move it.
- **Localhost only.** No auth in v1 because the socket never leaves the machine; do not bind
  to `0.0.0.0` (see [SECURITY.md](../../SECURITY.md)).
- Errors are instructive: name the problem, the fix, and the alternative — they are part of the
  interface (asserted in `tests/test_api_errors.py`).
