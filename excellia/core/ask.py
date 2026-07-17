"""AI chat over data that cannot lie about numbers.

Pipeline: the LLM sees only the schema, light stats, and 20 sample
rows. It returns a QUERY PLAN as strict JSON — a safe whitelist of
filter/group/aggregate/sort/limit that pandas executes. The LLM never
sees or writes code, and every number in the final answer comes from
the computed evidence table, which is always returned alongside the
prose so it can be checked.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from excellia.core.llm import Ollama

MAX_EVIDENCE_ROWS = 200
_SAMPLE_ROWS = 20

_FILTER_OPS = {"eq", "ne", "gt", "ge", "lt", "le", "contains", "startswith",
               "in", "isnull", "notnull"}
_AGG_FNS = {"count", "sum", "mean", "min", "max", "nunique"}


class PlanError(ValueError):
    """A plan step fell outside the whitelist. Message says what and why."""


_SYSTEM = """You are a query planner for spreadsheet data. You NEVER answer from \
memory and NEVER compute numbers yourself — you emit a JSON query plan that \
deterministic code executes.

Reply with ONLY a JSON object, one of:
1. {"plan": {...}} where the plan may have these keys (all optional):
   "filters": [{"column": str, "op": one of eq|ne|gt|ge|lt|le|contains|startswith|in|isnull|notnull, "value": any}]
   "group_by": [column, ...]
   "aggregates": [{"column": str, "fn": one of count|sum|mean|min|max|nunique, "as": str?}]
   "sort": [{"by": str, "desc": bool?}]   # after aggregation, "by" is a result column
   "limit": int (default 50)
2. {"refuse": "one sentence saying why this cannot be answered from this data, \
and which Excellia tool could (validate for rule violations, detect_anomalies for \
outliers, reconcile for comparing two files)"}

Use ONLY column names from the schema. Do not invent columns."""


def _schema_context(df: pd.DataFrame) -> str:
    lines = [f"Rows: {len(df)}", "Columns:"]
    for col in df.columns:
        lines.append(f"  - {col} (dtype {df[col].dtype}, {df[col].nunique()} distinct)")
    sample = df.head(_SAMPLE_ROWS).to_csv(index=False)
    if len(sample) > 4000:
        sample = sample[:4000] + "\n...truncated..."
    lines.append(f"First {min(_SAMPLE_ROWS, len(df))} rows (CSV):\n{sample}")
    return "\n".join(lines)


def _check_column(df: pd.DataFrame, name: Any) -> str:
    if not isinstance(name, str) or name not in df.columns:
        raise PlanError(
            f"Plan references unknown column '{name}'. Actual columns: {list(df.columns)}"
        )
    return name


def execute_plan(df: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    """Run a whitelisted query plan with pandas. Raises PlanError on
    anything outside the whitelist — never evaluates LLM text as code."""
    if not isinstance(plan, dict):
        raise PlanError("Plan must be a JSON object")
    unknown = set(plan) - {"filters", "group_by", "aggregates", "sort", "limit"}
    if unknown:
        raise PlanError(f"Unknown plan keys {sorted(unknown)}")

    out = df
    for f in plan.get("filters") or []:
        col = _check_column(df, (f or {}).get("column"))
        op = (f or {}).get("op")
        if op not in _FILTER_OPS:
            raise PlanError(f"Filter op '{op}' not allowed. Allowed: {sorted(_FILTER_OPS)}")
        value = f.get("value")
        series = out[col]
        if op in ("gt", "ge", "lt", "le"):
            series = pd.to_numeric(series, errors="coerce")
            value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
            mask = {"gt": series > value, "ge": series >= value,
                    "lt": series < value, "le": series <= value}[op]
        elif op == "eq":
            mask = series.astype(str).str.strip().str.lower() == str(value).strip().lower()
        elif op == "ne":
            mask = series.astype(str).str.strip().str.lower() != str(value).strip().lower()
        elif op == "contains":
            mask = series.astype(str).str.contains(str(value), case=False, regex=False, na=False)
        elif op == "startswith":
            mask = series.astype(str).str.lower().str.startswith(str(value).lower(), na=False)
        elif op == "in":
            wanted = {str(v).strip().lower() for v in (value if isinstance(value, list) else [value])}
            mask = series.astype(str).str.strip().str.lower().isin(wanted)
        elif op == "isnull":
            mask = series.isna() | series.astype(str).str.strip().eq("")
        else:  # notnull
            mask = ~(series.isna() | series.astype(str).str.strip().eq(""))
        out = out[mask.fillna(False)]

    group_by = [_check_column(df, c) for c in plan.get("group_by") or []]
    aggregates = plan.get("aggregates") or []
    if aggregates:
        named: dict[str, tuple[str, str]] = {}
        for a in aggregates:
            fn = (a or {}).get("fn")
            if fn not in _AGG_FNS:
                raise PlanError(f"Aggregate fn '{fn}' not allowed. Allowed: {sorted(_AGG_FNS)}")
            col = _check_column(df, a.get("column"))
            label = a.get("as") or f"{fn}_{col}"
            source = out[col] if fn in ("count", "nunique") else pd.to_numeric(out[col], errors="coerce")
            named[str(label)] = (col, fn)
            if fn not in ("count", "nunique"):
                out = out.assign(**{f"__num_{col}": source})
        if group_by:
            agg_spec = {
                label: pd.NamedAgg(
                    column=col if fn in ("count", "nunique") else f"__num_{col}", aggfunc=fn
                )
                for label, (col, fn) in named.items()
            }
            out = out.groupby(group_by, dropna=False).agg(**agg_spec).reset_index()
        else:
            row = {}
            for label, (col, fn) in named.items():
                series = out[col] if fn in ("count", "nunique") else out[f"__num_{col}"]
                row[label] = getattr(series, fn)()
            out = pd.DataFrame([row])
    elif group_by:
        out = out.groupby(group_by, dropna=False).size().reset_index(name="count")

    for s in plan.get("sort") or []:
        by = (s or {}).get("by")
        if not isinstance(by, str) or by not in out.columns:
            raise PlanError(f"Sort column '{by}' not in the result. Result columns: {list(out.columns)}")
        out = out.sort_values(by, ascending=not s.get("desc", False))

    limit = plan.get("limit", 50)
    if not isinstance(limit, int) or not (1 <= limit <= 1000):
        limit = 50
    out = out.drop(columns=[c for c in out.columns if str(c).startswith("__num_")],
                   errors="ignore")
    return out.head(limit)


def ask(df: pd.DataFrame, question: str, llm: Ollama | None = None) -> dict[str, Any]:
    """Answer a question about a DataFrame with evidence.

    Returns {answer, evidence, plan, matched_rows}. On refusal or
    failure, `answer` explains what to do instead — never invents."""
    llm = llm or Ollama()
    reply = llm.json_call(
        f"Data:\n{_schema_context(df)}\n\nQuestion: {question}", system=_SYSTEM
    )

    if reply.get("reason") == "parse_failed":
        return {
            "answer": "The local model could not produce a valid query plan for this "
                      "question. Rephrase it in terms of the columns shown by "
                      "profile_sheet, or use validate/detect_anomalies for quality checks.",
            "evidence": [], "plan": None, "refused": True,
        }
    if "refuse" in reply:
        return {"answer": str(reply["refuse"]), "evidence": [], "plan": None, "refused": True}

    plan = reply.get("plan")
    try:
        evidence = execute_plan(df, plan or {})
    except PlanError as e:
        return {
            "answer": f"The model proposed an invalid query plan ({e}). "
                      "Try rephrasing the question with exact column names.",
            "evidence": [], "plan": plan, "refused": True,
        }

    records = evidence.head(MAX_EVIDENCE_ROWS).to_dict(orient="records")
    table_csv = evidence.head(50).to_csv(index=False)
    narration = llm.json_call(
        "A deterministic engine computed this result table for the question "
        f"'{question}':\n\n{table_csv}\n\nReply with ONLY JSON: "
        '{"answer": "1-3 sentences describing the result, using ONLY numbers that '
        'appear in the table"}',
        system="You narrate computed results. Never introduce numbers that are not "
               "in the table you are given.",
    )
    answer = narration.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        answer = (f"Computed {len(evidence)} result row(s); see the evidence table. "
                  "(The local model failed to narrate them, but the numbers are real.)")
    return {"answer": answer, "evidence": records, "plan": plan,
            "matched_rows": len(evidence), "refused": False}
