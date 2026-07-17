"""Core API. Thin: every endpoint calls exactly one core function.

Job queue, workspace CRUD, and file handling belong here (the API
layer), never in ``core``. Endpoint bodies are factored into ``_do_*``
functions so the job queue runs the exact same code path async.

Error contract: errors are instructive — they name the problem, the
fix, and the alternative. AI callers read these strings and retry
intelligently, so treat them as part of the interface.
"""

from __future__ import annotations

import os

import pandas as pd
from fastapi import FastAPI, HTTPException

from excellia.api import jobs
from excellia.api.schemas import (
    AnomaliesRequest,
    AskRequest,
    CleanRequest,
    FraudEvaluateRequest,
    FraudScoreRequest,
    FraudTrainRequest,
    JobRequest,
    KycDedupeRequest,
    KycMatchRequest,
    ProfileRequest,
    ReconcileRequest,
    ReconcileRunRequest,
    ReportRequest,
    SpecBody,
    TransformApplyRequest,
    TransformPreviewRequest,
    ValidateRequest,
)
from excellia.core import (
    anomaly,
    ask,
    clean,
    fraud,
    ingest,
    kyc,
    reconcile,
    report,
    store,
    transform,
    validate,
)
from excellia.core.llm import LLMError
from excellia.core.transform import TransformError

_VERSION = "0.4.0"

# Files above this on-disk size take the streaming (chunked) core paths
# instead of the in-memory ones. ~15MB of xlsx/csv is roughly where full
# loads start to hurt; callers with bigger files should also prefer /jobs.
BIG_FILE_BYTES = 15 * 1024 * 1024

app = FastAPI(
    title="Excellia Core API",
    description="Spreadsheet intelligence engine. Fully on-prem; nothing leaves the machine.",
    version=_VERSION,
)

_ROW_NOTE = "row numbers are Excel rows: header is row 1, first data row is 2"


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


def _check_exists(file: str) -> None:
    if not os.path.exists(file):
        raise HTTPException(
            404,
            f"File not found: {file}. Provide an absolute path, or a path "
            f"relative to the API's working directory ({os.getcwd()}).",
        )


def _out_path(file: str, out_path: str | None, suffix: str) -> str:
    """A safe output path: never the input file itself."""
    if out_path is None:
        stem, ext = os.path.splitext(file)
        out_path = f"{stem}_{suffix}{ext if ext.lower() in ('.xlsx', '.csv') else '.xlsx'}"
    if os.path.abspath(out_path) == os.path.abspath(file):
        raise HTTPException(400, "Refusing to overwrite the input file; pick another out_path")
    return out_path


def _write_df(df: pd.DataFrame, path: str) -> str:
    if path.lower().endswith(".csv"):
        df.to_csv(path, index=False)
    else:
        df.to_excel(path, index=False)
    return os.path.abspath(path)


def _sample(df: pd.DataFrame, n: int = 10) -> list[dict]:
    return df.head(n).astype(object).where(df.head(n).notna(), None).to_dict(orient="records")


def _llm_503(e: LLMError) -> HTTPException:
    return HTTPException(503, str(e))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": _VERSION}


# --- the four pillars (Stage A surface, unchanged behaviour) ----------

def _is_big(file: str) -> bool:
    try:
        return os.path.getsize(file) > BIG_FILE_BYTES
    except OSError:
        return False


def _do_profile(req: ProfileRequest) -> dict:
    _check_exists(req.file)
    try:
        fn = ingest.profile_large if _is_big(req.file) else ingest.profile
        prof = fn(req.file, sheet=req.sheet)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, f"Could not read {req.file}: {e}")
    store.record("profile", file=req.file,
                 summary={"rows": prof.row_count, "columns": prof.column_count})
    return prof.to_dict()


@app.post("/profile")
def profile_endpoint(req: ProfileRequest) -> dict:
    return _do_profile(req)


def _do_validate(req: ValidateRequest) -> dict:
    try:
        if _is_big(req.file):
            _check_exists(req.file)
            issues = validate.validate_large(req.file, ruleset=req.ruleset, sheet=req.sheet)
        else:
            df = _load(req.file, sheet=req.sheet)
            issues = validate.validate(df, ruleset=req.ruleset)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:  # unknown ruleset — message lists the available ones
        raise HTTPException(400, str(e))
    errors = sum(1 for i in issues if i.severity == "error")
    store.record("validate", file=req.file, params={"ruleset": req.ruleset},
                 summary={"issues": len(issues), "errors": errors})
    return {
        "issues": [i.to_dict() for i in issues],
        "summary": {
            "total": len(issues),
            "errors": errors,
            "warnings": len(issues) - errors,
            "note": _ROW_NOTE,
        },
    }


@app.post("/validate")
def validate_endpoint(req: ValidateRequest) -> dict:
    return _do_validate(req)


def _do_anomalies(req: AnomaliesRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        flags = anomaly.detect_anomalies(df, sensitivity=req.contamination)
    except ValueError as e:
        raise HTTPException(400, str(e))
    store.record("anomalies", file=req.file, summary={"flags": len(flags)})
    return {
        "flags": [f.to_dict() for f in flags],
        "summary": {"total": len(flags), "note": _ROW_NOTE},
    }


@app.post("/anomalies")
def anomalies_endpoint(req: AnomaliesRequest) -> dict:
    return _do_anomalies(req)


def _do_reconcile(req: ReconcileRequest) -> dict:
    df_a = _load(req.a)
    df_b = _load(req.b)
    try:
        result = reconcile.reconcile(df_a, df_b, keys=req.keys, tolerance=req.tolerance)
    except ValueError as e:  # missing key column — message lists both files' columns
        raise HTTPException(400, str(e))
    store.record("reconcile", file=req.a, params={"keys": req.keys},
                 summary=result.summary())
    return result.to_dict()


@app.post("/reconcile")
def reconcile_endpoint(req: ReconcileRequest) -> dict:
    return _do_reconcile(req)


# --- Stage B: ask / clean / transform / report ------------------------

@app.post("/ask")
def ask_endpoint(req: AskRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        result = ask.ask(df, req.question)
    except LLMError as e:
        raise _llm_503(e)
    store.record("ask", file=req.file, params={"question": req.question[:200]},
                 summary={"refused": result["refused"]})
    return result


def _do_clean(req: CleanRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        cleaned = clean.apply_ops(df, req.steps)
    except clean.CleanError as e:
        raise HTTPException(400, str(e))
    out = _write_df(cleaned, _out_path(req.file, req.out_path, "cleaned"))
    store.record("clean", file=req.file, params={"steps": [s.get("op") for s in req.steps]},
                 summary={"out": os.path.basename(out), "rows": len(cleaned)})
    return {
        "out_path": out, "rows": len(cleaned), "columns": list(cleaned.columns),
        "sample": _sample(cleaned),
        "note": "The input file was not modified; the cleaned copy is at out_path.",
    }


@app.post("/clean")
def clean_endpoint(req: CleanRequest) -> dict:
    return _do_clean(req)


@app.post("/transform/preview")
def transform_preview_endpoint(req: TransformPreviewRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        result = transform.preview(df, req.instruction)
    except LLMError as e:
        raise _llm_503(e)
    except TransformError as e:
        raise HTTPException(400, str(e))
    store.record("transform_preview", file=req.file,
                 params={"instruction": req.instruction[:200]})
    return result


def _resolve_recipe(req: TransformApplyRequest, df: pd.DataFrame) -> dict:
    given = [x for x in (req.recipe, req.recipe_name, req.instruction) if x]
    if len(given) != 1:
        raise HTTPException(
            400, "Pass exactly one of: recipe (from transform_preview), "
                 "recipe_name (saved), or instruction (preview+apply in one step).")
    if req.recipe:
        return req.recipe
    if req.recipe_name:
        try:
            return store.load("recipes", req.recipe_name)
        except store.StoreError as e:
            raise HTTPException(404, str(e))
    try:
        return transform.preview(df, req.instruction)["recipe"]  # type: ignore[arg-type]
    except LLMError as e:
        raise _llm_503(e)
    except TransformError as e:
        raise HTTPException(400, str(e))


def _do_transform_apply(req: TransformApplyRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    recipe = _resolve_recipe(req, df)
    try:
        result = transform.apply(df, recipe, replace=req.replace)
    except LLMError as e:
        raise _llm_503(e)
    except (TransformError, clean.CleanError) as e:
        raise HTTPException(400, str(e))
    out = _write_df(result, _out_path(req.file, req.out_path, "transformed"))
    saved = None
    if req.save_as:
        try:
            saved = store.save("recipes", req.save_as, recipe)
        except store.StoreError as e:
            raise HTTPException(400, str(e))
    store.record("transform_apply", file=req.file,
                 params={"steps": [s.get("op") for s in recipe.get("steps", [])],
                         "replace": req.replace},
                 summary={"out": os.path.basename(out), "rows": len(result),
                          "saved_recipe": req.save_as})
    return {
        "out_path": out, "rows": len(result), "columns": list(result.columns),
        "sample": _sample(result), "recipe": recipe, "saved_recipe": saved,
        "note": "The input file was not modified — undo is simply the original file. "
                "New columns carry the _ai suffix unless replace=true was passed.",
    }


@app.post("/transform/apply")
def transform_apply_endpoint(req: TransformApplyRequest) -> dict:
    return _do_transform_apply(req)


def _do_report(req: ReportRequest) -> dict:
    _check_exists(req.file)
    try:
        result = report.export_report(
            req.file, out_path=req.out_path, ruleset=req.ruleset,
            sensitivity=req.sensitivity, sheet=req.sheet)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    store.record("report", file=req.file,
                 summary={"score": result["health"]["score"],
                          "out": os.path.basename(result["path"])})
    return result


@app.post("/report")
def report_endpoint(req: ReportRequest) -> dict:
    return _do_report(req)


# --- Stage C: fraud ---------------------------------------------------

def _do_fraud_train(req: FraudTrainRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        card = fraud.train(df, label_column=req.label_column, model_name=req.model_name,
                           positive_label=req.positive_label, algorithm=req.algorithm)
    except fraud.FraudError as e:
        raise HTTPException(400, str(e))
    except store.StoreError as e:
        raise HTTPException(400, str(e))
    return {"model_card": card,
            "note": "Metrics are 5-fold cross-validation. Evaluate on a labelled "
                    "holdout with /fraud/evaluate before trusting them."}


@app.post("/fraud/train")
def fraud_train_endpoint(req: FraudTrainRequest) -> dict:
    return _do_fraud_train(req)


def _do_fraud_score(req: FraudScoreRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        return fraud.score(df, model_name=req.model_name, threshold=req.threshold)
    except (fraud.FraudError, store.StoreError) as e:
        raise HTTPException(400, str(e))


@app.post("/fraud/score")
def fraud_score_endpoint(req: FraudScoreRequest) -> dict:
    return _do_fraud_score(req)


@app.post("/fraud/evaluate")
def fraud_evaluate_endpoint(req: FraudEvaluateRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        return fraud.evaluate(df, label_column=req.label_column, model_name=req.model_name)
    except (fraud.FraudError, store.StoreError) as e:
        raise HTTPException(400, str(e))


@app.get("/fraud/models")
def fraud_models_endpoint() -> dict:
    return {"models": fraud.list_models()}


# --- Stage C: reconciliation profiles ---------------------------------

@app.get("/reconcile/profiles")
def reconcile_profiles_endpoint() -> dict:
    return {"profiles": store.list_names("profiles")}


@app.get("/reconcile/profiles/{name}")
def reconcile_profile_get(name: str) -> dict:
    try:
        return {"name": name, "spec": store.load("profiles", name)}
    except store.StoreError as e:
        raise HTTPException(404, str(e))


@app.post("/reconcile/profiles/{name}")
def reconcile_profile_save(name: str, body: SpecBody) -> dict:
    if not body.spec.get("keys"):
        raise HTTPException(
            400, 'A reconciliation profile needs at least {"keys": [...]}. Optional: '
                 "tolerance, fuzzy_keys, pre_recipe_a/b, dedupe_a/b, name.")
    try:
        path = store.save("profiles", name, {**body.spec, "name": name})
    except store.StoreError as e:
        raise HTTPException(400, str(e))
    store.record("save_reconciliation_profile", params={"name": name})
    return {"saved": name, "path": path}


@app.delete("/reconcile/profiles/{name}")
def reconcile_profile_delete(name: str) -> dict:
    if not store.delete("profiles", name):
        raise HTTPException(404, f"No saved reconciliation profile '{name}'.")
    return {"deleted": name}


def _do_reconcile_run(req: ReconcileRunRequest) -> dict:
    given = [x for x in (req.profile, req.profile_name) if x]
    if len(given) != 1:
        raise HTTPException(
            400, "Pass exactly one of: profile (a literal spec) or profile_name "
                 "(saved via POST /reconcile/profiles/<name>).")
    if req.profile_name:
        try:
            profile = store.load("profiles", req.profile_name)
        except store.StoreError as e:
            raise HTTPException(404, str(e))
    else:
        profile = req.profile
    df_a = _load(req.a)
    df_b = _load(req.b)
    try:
        run = reconcile.run_profile(df_a, df_b, profile)
    except (ValueError, clean.CleanError) as e:
        raise HTTPException(400, str(e))
    out = {"summary": run["summary"], "result": run["result"].to_dict()}
    if req.report:
        path = _out_path(req.a, req.out_path, "reconciliation")
        if not path.lower().endswith(".xlsx"):
            path = os.path.splitext(path)[0] + ".xlsx"
        out["report_path"] = report.reconciliation_report(
            run["result"], run["summary"], path)
    store.record("reconcile_run", file=req.a,
                 params={"profile": profile.get("name") or "(inline)"},
                 summary=run["summary"])
    return out


@app.post("/reconcile/run")
def reconcile_run_endpoint(req: ReconcileRunRequest) -> dict:
    return _do_reconcile_run(req)


# --- Stage C: KYC -----------------------------------------------------

def _do_kyc_match(req: KycMatchRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        result = kyc.match_names(
            df, col_a=req.col_a, col_b=req.col_b, group_by=req.group_by,
            llm_verify=req.llm_verify, seq_threshold=req.seq_threshold)
    except kyc.KycError as e:
        raise HTTPException(400, str(e))
    except LLMError as e:
        raise _llm_503(e)
    store.record("kyc_match_names", file=req.file,
                 summary={"candidates": result["summary"]["candidates"]})
    return result


@app.post("/kyc/match_names")
def kyc_match_endpoint(req: KycMatchRequest) -> dict:
    return _do_kyc_match(req)


def _do_kyc_dedupe(req: KycDedupeRequest) -> dict:
    df = _load(req.file, sheet=req.sheet)
    try:
        result = kyc.dedupe(df, columns=req.columns, threshold=req.threshold,
                            strategy=req.strategy)
    except kyc.KycError as e:
        raise HTTPException(400, str(e))
    deduped = result.pop("deduped")
    out = _write_df(deduped, _out_path(req.file, req.out_path, "deduped"))
    store.record("kyc_dedupe", file=req.file,
                 summary={"before": result["rows_before"], "after": result["rows_after"]})
    return {**result, "out_path": out, "sample": _sample(deduped)}


@app.post("/kyc/dedupe")
def kyc_dedupe_endpoint(req: KycDedupeRequest) -> dict:
    return _do_kyc_dedupe(req)


# --- workspace CRUD: rulesets, recipes, history -----------------------

@app.get("/rulesets")
def rulesets_endpoint() -> dict:
    return {"rulesets": validate.list_rulesets(),
            "builtin": sorted(validate.RULESETS)}


@app.get("/rulesets/{name}")
def ruleset_get(name: str) -> dict:
    try:
        return {"name": name, "spec": validate.resolve_ruleset(name)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/rulesets/{name}")
def ruleset_save(name: str, body: SpecBody) -> dict:
    if name in validate.RULESETS:
        raise HTTPException(
            400, f"'{name}' is a built-in ruleset and cannot be overwritten. "
                 "Save under a different name.")
    allowed = {"required", "formats", "ranges", "unique", "references",
               "expressions", "auto"}
    unknown = set(body.spec) - allowed
    if unknown:
        raise HTTPException(
            400, f"Unknown ruleset keys {sorted(unknown)}. Allowed: {sorted(allowed)}")
    try:
        path = store.save("rulesets", name, body.spec)
    except store.StoreError as e:
        raise HTTPException(400, str(e))
    store.record("save_ruleset", params={"name": name})
    return {"saved": name, "path": path}


@app.delete("/rulesets/{name}")
def ruleset_delete(name: str) -> dict:
    if name in validate.RULESETS:
        raise HTTPException(400, f"'{name}' is built-in and cannot be deleted.")
    if not store.delete("rulesets", name):
        raise HTTPException(404, f"No saved ruleset '{name}'.")
    return {"deleted": name}


@app.get("/recipes")
def recipes_endpoint() -> dict:
    return {"recipes": store.list_names("recipes")}


@app.get("/recipes/{name}")
def recipe_get(name: str) -> dict:
    try:
        return {"name": name, "spec": store.load("recipes", name)}
    except store.StoreError as e:
        raise HTTPException(404, str(e))


@app.post("/recipes/{name}")
def recipe_save(name: str, body: SpecBody) -> dict:
    try:
        transform.validate_recipe(body.spec)
        path = store.save("recipes", name, body.spec)
    except (TransformError, store.StoreError) as e:
        raise HTTPException(400, str(e))
    store.record("save_recipe", params={"name": name})
    return {"saved": name, "path": path}


@app.delete("/recipes/{name}")
def recipe_delete(name: str) -> dict:
    if not store.delete("recipes", name):
        raise HTTPException(404, f"No saved recipe '{name}'.")
    return {"deleted": name}


@app.get("/history")
def history_endpoint(limit: int = 50) -> dict:
    return {"history": store.history(limit=limit)}


# --- job queue --------------------------------------------------------

_JOB_OPS = {
    "profile": (ProfileRequest, _do_profile),
    "validate": (ValidateRequest, _do_validate),
    "anomalies": (AnomaliesRequest, _do_anomalies),
    "reconcile": (ReconcileRequest, _do_reconcile),
    "clean": (CleanRequest, _do_clean),
    "transform_apply": (TransformApplyRequest, _do_transform_apply),
    "report": (ReportRequest, _do_report),
    "fraud_train": (FraudTrainRequest, _do_fraud_train),
    "fraud_score": (FraudScoreRequest, _do_fraud_score),
    "reconcile_run": (ReconcileRunRequest, _do_reconcile_run),
    "kyc_match_names": (KycMatchRequest, _do_kyc_match),
    "kyc_dedupe": (KycDedupeRequest, _do_kyc_dedupe),
}


@app.post("/jobs")
def job_submit(req: JobRequest) -> dict:
    if req.op not in _JOB_OPS:
        raise HTTPException(
            400, f"Unknown job op '{req.op}'. Available: {', '.join(sorted(_JOB_OPS))}")
    model, fn = _JOB_OPS[req.op]
    try:
        parsed = model(**req.params)
    except Exception as e:
        raise HTTPException(400, f"Bad params for op '{req.op}': {e}")
    return jobs.submit(req.op, lambda: fn(parsed),
                       params_summary={"file": req.params.get("file")})


@app.get("/jobs")
def job_list() -> dict:
    return {"jobs": jobs.list_jobs()}


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    return jobs.status(job_id)


def serve() -> None:
    """Entry point for `excellia-api`."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("EXCELLIA_PORT", "8000")))


if __name__ == "__main__":
    serve()
