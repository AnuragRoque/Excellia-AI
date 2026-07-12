"""Core API. Thin: every endpoint calls exactly one core function.

Job queues, auth, and sessions belong here (the API layer), never in
``core``. None of that is in v1.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from excellia.api.schemas import (
    AnomaliesRequest,
    ProfileRequest,
    ReconcileRequest,
    ValidateRequest,
)
from excellia.core import anomaly, ingest, reconcile, validate

app = FastAPI(
    title="Excellia Core API",
    description="Spreadsheet validation engine. Fully on-prem; nothing leaves the machine.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/profile")
def profile_endpoint(req: ProfileRequest) -> dict:
    try:
        return ingest.profile(req.file, sheet=req.sheet).to_dict()
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {req.file}")


@app.post("/validate")
def validate_endpoint(req: ValidateRequest) -> dict:
    try:
        df = ingest.load(req.file, sheet=req.sheet)
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {req.file}")
    issues = validate.validate(df, ruleset=req.ruleset)
    return {
        "issues": [i.to_dict() for i in issues],
        "summary": {"total": len(issues)},
    }


@app.post("/anomalies")
def anomalies_endpoint(req: AnomaliesRequest) -> dict:
    try:
        df = ingest.load(req.file, sheet=req.sheet)
    except FileNotFoundError:
        raise HTTPException(404, f"File not found: {req.file}")
    flags = anomaly.detect_anomalies(df, sensitivity=req.contamination)
    return {"flags": [f.to_dict() for f in flags]}


@app.post("/reconcile")
def reconcile_endpoint(req: ReconcileRequest) -> dict:
    try:
        df_a = ingest.load(req.a)
        df_b = ingest.load(req.b)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    result = reconcile.reconcile(df_a, df_b, keys=req.keys, tolerance=req.tolerance)
    return result.to_dict()


@app.get("/rulesets")
def rulesets_endpoint() -> dict:
    return {"rulesets": validate.list_rulesets()}


def serve() -> None:
    """Entry point for `excellia-api`."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    serve()
