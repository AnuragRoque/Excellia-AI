/* Excellia task pane — a pure client of the local core API (same origin).
   Non-destructive rule: results only ever go to an EMPTY adjacent column;
   the user's cells are never overwritten. */
"use strict";

const $ = (s) => document.querySelector(s);

async function post(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `API error (HTTP ${resp.status})`);
  return data;
}

function say(sel, msg, isError = false) {
  const el = $(sel);
  el.textContent = msg;
  el.className = isError ? "out err" : "out";
}

async function withButton(btn, fn) {
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = "working…";
  try { await fn(); }
  finally { btn.disabled = false; btn.textContent = old; }
}

/* Selected range -> {values (2D), rowCount, columnCount, rowIndex, columnIndex, sheet} */
async function readSelection(ctx) {
  const range = ctx.workbook.getSelectedRange();
  range.load(["values", "rowCount", "columnCount", "rowIndex", "columnIndex"]);
  const sheet = ctx.workbook.worksheets.getActiveWorksheet();
  await ctx.sync();
  return { range, sheet, values: range.values, rowCount: range.rowCount,
           columnCount: range.columnCount, rowIndex: range.rowIndex,
           columnIndex: range.columnIndex };
}

/* Write a single column right of the selection — only if it's empty. */
async function writeAdjacent(ctx, sel, column, header) {
  const target = sel.sheet.getRangeByIndexes(
    sel.rowIndex, sel.columnIndex + sel.columnCount, sel.rowCount, 1);
  target.load("values");
  await ctx.sync();
  const occupied = target.values.some((r) => r[0] !== "" && r[0] !== null);
  if (occupied) {
    throw new Error("The column right of the selection has data — Excellia never "
      + "overwrites. Move the selection or clear that column.");
  }
  target.values = column.map((v) => [v]);
  target.format.font.italic = true;
  target.format.font.color = "#2563eb";  // the AI-written accent from the spec
  if (header && sel.rowIndex > 0) {
    const head = sel.sheet.getRangeByIndexes(
      sel.rowIndex - 1, sel.columnIndex + sel.columnCount, 1, 1);
    head.load("values");
    await ctx.sync();
    if (head.values[0][0] === "" || head.values[0][0] === null) {
      head.values = [[header]];
      head.format.font.bold = true;
    }
  }
  await ctx.sync();
}

const cells = (sel) => sel.values.flat().map((v) => (v === null ? "" : String(v)));

/* ---- actions ---- */

$("#v-run").onclick = (e) => withButton(e.target, async () => {
  try {
    await Excel.run(async (ctx) => {
      const sel = await readSelection(ctx);
      if (sel.columnCount !== 1) throw new Error("Select a single column of values.");
      const fmt = $("#v-fmt").value;
      const data = await post("/values/validate", { values: cells(sel), format: fmt });
      await writeAdjacent(ctx, sel,
        data.results.map((ok) => (ok ? "valid" : "INVALID")), `${fmt}_check`);
      const bad = data.results.filter((ok) => !ok).length;
      say("#v-out", `${sel.rowCount} checked — ${bad} invalid.`);
    });
  } catch (err) { say("#v-out", err.message, true); }
});

let previewedInstruction = null;

$("#t-preview").onclick = (e) => withButton(e.target, async () => {
  try {
    await Excel.run(async (ctx) => {
      const sel = await readSelection(ctx);
      if (sel.columnCount !== 1) throw new Error("Select a single column of values.");
      const instruction = $("#t-i").value.trim();
      if (!instruction) throw new Error("Write an instruction first.");
      const sample = [...new Set(cells(sel).filter((v) => v.trim()))].slice(0, 8);
      if (!sample.length) throw new Error("The selection is empty.");
      const data = await post("/values/map", { values: sample, instruction });
      say("#t-out", sample.map((v, i) => `${v}  →  ${data.results[i]}`).join("\n")
        + "\n\nLooks right? Apply writes the full column.");
      previewedInstruction = instruction;
      $("#t-apply").disabled = false;
    });
  } catch (err) { say("#t-out", err.message, true); }
});

$("#t-apply").onclick = (e) => withButton(e.target, async () => {
  try {
    await Excel.run(async (ctx) => {
      const sel = await readSelection(ctx);
      if (sel.columnCount !== 1) throw new Error("Select a single column of values.");
      const instruction = previewedInstruction || $("#t-i").value.trim();
      const data = await post("/values/map", { values: cells(sel), instruction });
      await writeAdjacent(ctx, sel, data.results, "ai_result");
      say("#t-out", `${sel.rowCount} cells transformed into the adjacent column.`);
    });
  } catch (err) { say("#t-out", err.message, true); }
});

$("#m-run").onclick = (e) => withButton(e.target, async () => {
  try {
    await Excel.run(async (ctx) => {
      const sel = await readSelection(ctx);
      if (sel.columnCount !== 2) throw new Error("Select exactly two columns (name A | name B).");
      const a = sel.values.map((r) => (r[0] === null ? "" : String(r[0])));
      const b = sel.values.map((r) => (r[1] === null ? "" : String(r[1])));
      const data = await post("/values/similarity", { a, b });
      await writeAdjacent(ctx, sel, data.results, "similarity");
      say("#m-out", `${sel.rowCount} pairs scored (0–100).`);
    });
  } catch (err) { say("#m-out", err.message, true); }
});

/* ---- boot ---- */

Office.onReady(() => {
  fetch("/health").then((r) => r.json()).then((h) => {
    const p = $("#pill");
    p.textContent = `core API ${h.version} — local`;
    p.className = "pill ok";
  }).catch(() => {
    const p = $("#pill");
    p.textContent = "core API unreachable — run `excellia-addin`";
    p.className = "pill bad";
  });
});
