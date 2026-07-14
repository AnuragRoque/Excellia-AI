"""Core API. Thin: every endpoint calls exactly one core function.

Job queues, auth, and sessions belong here (the API layer), never in
``core``. None of that is in v1.

Error contract: errors are instructive — they name the problem, the
fix, and the alternative. AI callers read these strings and retry
intelligently, so treat them as part of the interface.
"""

from __future__ import annotations

import os

import pandas as pd
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


def _load(file: str, sheet: str | None = None) -> pd.DataFrame:
    """Load a spreadsheet, translating core errors into instructive HTTP ones."""
    try:
        return ingest.load(file, sheet=sheet)
    except FileNotFoundError:
        raise HTTPException(
            404,
            f"File not found: {file}. Provide an absolute path, or a path "
            f"relative to the API's working directory ({os.getcwd()}).",
        )
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:  # e.g. sheet name not in workbook
        raise HTTPException(400, f"Could not read {file}: {e}")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/profile")
def profile_endpoint(req: ProfileRequest) -> dict:
    _load(req.file, sheet=req.sheet)  # surface load errors instructively
    return ingest.profile(req.file, sheet=req.sheet).to_dict()


@app.post("/validate")
def validate_endpoint(req: ValidateRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        issues = validate.validate(df, ruleset=req.ruleset)
    except ValueError as e:  # unknown ruleset — message lists the available ones
        raise HTTPException(400, str(e))
    errors = sum(1 for i in issues if i.severity == "error")
    return {
        "issues": [i.to_dict() for i in issues],
        "summary": {
            "total": len(issues),
            "errors": errors,
            "warnings": len(issues) - errors,
            "note": "row numbers are Excel rows: header is row 1, first data row is 2",
        },
    }


@app.post("/anomalies")
def anomalies_endpoint(req: AnomaliesRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        flags = anomaly.detect_anomalies(df, sensitivity=req.contamination)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "flags": [f.to_dict() for f in flags],
        "summary": {
            "total": len(flags),
            "note": "row numbers are Excel rows: header is row 1, first data row is 2",
        },
    }


@app.post("/reconcile")
def reconcile_endpoint(req: ReconcileRequest) -> dict:
    df_a = _load(req.a)
    df_b = _load(req.b)
    try:
        result = reconcile.reconcile(df_a, df_b, keys=req.keys, tolerance=req.tolerance)
    except ValueError as e:  # missing key column — message lists both files' columns
        raise HTTPException(400, str(e))
    return result.to_dict()


@app.get("/rulesets")
def rulesets_endpoint() -> dict:
    return {"rulesets": validate.list_rulesets()}


def serve() -> None:
    """Entry point for `excellia-api`."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("EXCELLIA_PORT", "8000")))


if __name__ == "__main__":
    serve()
