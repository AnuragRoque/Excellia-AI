/* Excellia =XAI.* custom functions.
   Engineering rules (from the spec):
   - BATCH: all cells in a calc pass coalesce into ONE API request per
     (endpoint, instruction) — never one HTTP call per cell.
   - CACHE: results keyed by (value, instruction) survive recalcs — an
     unchanged cell never re-runs the LLM.
   - Errors surface as #VALUE! with the API's instructive message.
   Same origin as the API (https://localhost:8443) — plain fetch. */
"use strict";

const CACHE = new Map(); // `${kind}|${instruction}|${value}` -> result
const QUEUES = new Map(); // `${kind}|${instruction}` -> {items: [...], timer}
const BATCH_MS = 80;

function fnError(message) {
  return new CustomFunctions.Error(
    CustomFunctions.ErrorCode.invalidValue, String(message).slice(0, 250));
}

async function post(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw fnError(data.detail || `API error (HTTP ${resp.status})`);
  return data;
}

/* Coalesce per-cell lookups into one POST per (kind, instruction). */
function batched(kind, path, instruction, buildBody) {
  return (value) => {
    const key = `${kind}|${instruction}|${value}`;
    if (CACHE.has(key)) return Promise.resolve(CACHE.get(key));
    const qkey = `${kind}|${instruction}`;
    let q = QUEUES.get(qkey);
    if (!q) {
      q = { items: [] };
      QUEUES.set(qkey, q);
      q.timer = setTimeout(async () => {
        QUEUES.delete(qkey);
        const values = [...new Set(q.items.map((i) => i.value))];
        try {
          const data = await post(path, buildBody(values));
          values.forEach((v, i) => CACHE.set(`${kind}|${instruction}|${v}`, data.results[i]));
          q.items.forEach((i) => i.resolve(CACHE.get(`${kind}|${instruction}|${i.value}`)));
        } catch (e) {
          q.items.forEach((i) => i.reject(e));
        }
      }, BATCH_MS);
    }
    return new Promise((resolve, reject) => q.items.push({ value, resolve, reject }));
  };
}

const flat = (matrix) => matrix.flat();
const cell = (v) => (v === null || v === undefined ? "" : String(v));

async function mapMatrix(matrix, lookup) {
  const out = [];
  for (const row of matrix) out.push(await Promise.all(row.map((v) => lookup(cell(v)))));
  return out;
}

/* ---- the functions ---- */

async function RUN(values, instruction) {
  const lookup = batched("map", "/values/map", instruction,
    (vals) => ({ values: vals, instruction }));
  return mapMatrix(values, lookup);
}

async function TAG(values, criteria) {
  const instruction = `Answer strictly "Yes" or "No" (nothing else): ${criteria}`;
  const lookup = batched("map", "/values/map", instruction,
    (vals) => ({ values: vals, instruction }));
  return mapMatrix(values, lookup);
}

async function VALIDATE(values, format) {
  const fmt = String(format || "").trim().toLowerCase();
  const lookup = batched("validate", "/values/validate", fmt,
    (vals) => ({ values: vals, format: fmt }));
  const out = await mapMatrix(values, lookup);
  return out.map((row) => row.map((ok) => (ok ? "valid" : "INVALID")));
}

async function MATCH(a, b) {
  const av = flat(a).map(cell), bv = flat(b).map(cell);
  if (av.length !== bv.length && bv.length !== 1 && av.length !== 1)
    throw fnError(`Ranges differ in size (${av.length} vs ${bv.length}); use equal ranges or one cell vs a range.`);
  const n = Math.max(av.length, bv.length);
  const pa = Array.from({ length: n }, (_, i) => av[av.length === 1 ? 0 : i]);
  const pb = Array.from({ length: n }, (_, i) => bv[bv.length === 1 ? 0 : i]);
  const data = await post("/values/similarity", { a: pa, b: pb });
  const shape = av.length >= bv.length ? a : b; // mirror the bigger input's shape
  let k = 0;
  return shape.map((row) => row.map(() => data.results[k++]));
}

async function SPLIT(values, parts) {
  const names = String(parts || "").split("|").map((s) => s.trim()).filter(Boolean);
  if (!names.length) throw fnError('Give part names separated by |, e.g. "street | city | pin"');
  const vals = flat(values).map(cell);
  const data = await post("/values/split", { values: vals, parts: names });
  return [names, ...data.results]; // header row + one row per input cell
}

async function ASK(question, data) {
  if (!data || data.length < 2)
    throw fnError("Select a range that includes the header row plus data rows.");
  const columns = data[0].map(cell);
  const rows = data.slice(1);
  const r = await post("/values/ask", { columns, rows, question });
  return r.answer || "(no answer)";
}

CustomFunctions.associate("RUN", RUN);
CustomFunctions.associate("TAG", TAG);
CustomFunctions.associate("SPLIT", SPLIT);
CustomFunctions.associate("ASK", ASK);
CustomFunctions.associate("VALIDATE", VALIDATE);
CustomFunctions.associate("MATCH", MATCH);
