/* Excellia web app — a PURE client of the core API on the same origin.
   Governing rule: nothing computes here; every button is one HTTP call. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const S = { file: localStorage.getItem("excellia.file") || "" };

/* ---------- plumbing ---------- */

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, info = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = info ? "info" : "";
  t.hidden = false;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.hidden = true; }, info ? 4000 : 12000);
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(path, opts);
  let data;
  try { data = await resp.json(); }
  catch { throw new Error(`API returned a non-JSON response (HTTP ${resp.status})`); }
  if (!resp.ok) {
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : JSON.stringify(d ?? data));
  }
  return data;
}

async function run(btn, fn) {           // busy-state wrapper for buttons
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = "working…";
  try { await fn(); }
  catch (e) { toast(e.message); }
  finally { btn.disabled = false; btn.textContent = old; }
}

function needFile() {
  if (!S.file) { toast("Pick a file first — drop one on the left or paste a path."); return null; }
  return S.file;
}

/* ---------- render helpers ---------- */

function table(records, cap = 500) {
  if (!records || !records.length) return `<p class="sub">— empty —</p>`;
  const cols = Object.keys(records[0]);
  const rows = records.slice(0, cap).map((r) =>
    `<tr>${cols.map((c) => `<td>${fmtCell(c, r[c])}</td>`).join("")}</tr>`).join("");
  const note = records.length > cap ? `<p class="sub">showing ${cap} of ${records.length}</p>` : "";
  return `<div class="tablewrap"><table><thead><tr>${
    cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>${note}`;
}

function fmtCell(col, v) {
  if (v === null || v === undefined) return `<span class="sub">·</span>`;
  if (["severity", "risk_band", "match_level", "verdict"].includes(col))
    return `<span class="badge ${esc(v)}">${esc(v)}</span>`;
  if (typeof v === "object") return `<code>${esc(JSON.stringify(v))}</code>`;
  return esc(v);
}

function kv(obj) {
  return `<div class="kv">${Object.entries(obj).map(([k, v]) =>
    `<b>${esc(k)}</b><span>${typeof v === "object" && v !== null
      ? esc(JSON.stringify(v)) : esc(v)}</span>`).join("")}</div>`;
}

const json = (o) => `<pre class="json">${esc(JSON.stringify(o, null, 2))}</pre>`;

/* ---------- views ---------- */

const VIEWS = {
  quality: { label: "Quality", render: qualityView },
  ask: { label: "Ask the data", render: askView },
  transform: { label: "Transform", render: transformView },
  reconcile: { label: "Reconcile", render: reconcileView },
  fraud: { label: "Fraud", render: fraudView },
  kyc: { label: "KYC", render: kycView },
  jobs: { label: "Jobs & History", render: jobsView },
};

function qualityView(v) {
  v.innerHTML = `
    <h2>Data quality</h2>
    <p class="sub">Profile, validate, and anomaly-check the selected file. Deterministic — no LLM involved.</p>
    <section class="card">
      <div class="row">
        <div><label class="f">Ruleset</label><select id="q-ruleset"></select></div>
        <div><label class="f">Anomaly sensitivity (0–0.5)</label>
          <input type="number" id="q-sens" value="0.05" step="0.01" min="0.01" max="0.49"></div>
      </div>
      <button id="q-run">Run checks</button>
      <button id="q-report" class="ghost">Export highlighted report</button>
      <div class="out" id="q-out"></div>
    </section>`;
  api("GET", "/rulesets").then((r) => {
    $("#q-ruleset").innerHTML = r.rulesets.map((n) =>
      `<option${n === "default" ? " selected" : ""}>${esc(n)}</option>`).join("");
  }).catch(() => {});
  $("#q-run").onclick = (e) => run(e.target, async () => {
    const file = needFile(); if (!file) return;
    const ruleset = $("#q-ruleset").value, sens = parseFloat($("#q-sens").value) || 0.05;
    const [prof, val, anom] = [
      await api("POST", "/profile", { file }),
      await api("POST", "/validate", { file, ruleset }),
      await api("POST", "/anomalies", { file, contamination: sens }),
    ];
    $("#q-out").innerHTML = `
      ${kv({ rows: prof.row_count, columns: prof.column_count,
             issues: val.summary.total, errors: val.summary.errors,
             warnings: val.summary.warnings, anomaly_flags: anom.summary.total })}
      <h3 style="margin-top:14px">Columns</h3>
      ${table(prof.columns.map(({ top_values, ...c }) => c))}
      <h3 style="margin-top:14px">Issues</h3>${table(val.issues)}
      <h3 style="margin-top:14px">Anomalies</h3>${table(anom.flags)}`;
  });
  $("#q-report").onclick = (e) => run(e.target, async () => {
    const file = needFile(); if (!file) return;
    const r = await api("POST", "/report", { file, ruleset: $("#q-ruleset").value });
    const cls = r.health.score >= 80 ? "good" : r.health.score >= 50 ? "mid" : "poor";
    $("#q-out").innerHTML = `
      <div class="score ${cls}">${r.health.score}<span style="font-size:16px">/100</span></div>
      <p class="sub">${esc(r.health.note)}</p>
      ${table(r.health.breakdown)}
      <p class="pathline">report written to: ${esc(r.path)}</p>`;
  });
}

function askView(v) {
  v.innerHTML = `
    <h2>Ask the data</h2>
    <p class="sub">The local LLM plans a query, pandas computes it, and every number comes from the
      evidence table below the answer. Needs Ollama running.</p>
    <section class="card">
      <label class="f">Question</label>
      <textarea id="a-q" placeholder="total amount per city, highest first"></textarea>
      <button id="a-run">Ask</button>
      <div class="out" id="a-out"></div>
    </section>`;
  $("#a-run").onclick = (e) => run(e.target, async () => {
    const file = needFile(); if (!file) return;
    const r = await api("POST", "/ask", { file, question: $("#a-q").value });
    $("#a-out").innerHTML = `
      <section class="card"><h3>${r.refused ? "Could not answer" : "Answer"}</h3>
        <p>${esc(r.answer)}</p></section>
      <h3>Evidence (${r.matched_rows ?? 0} rows)</h3>${table(r.evidence)}
      <h3 style="margin-top:12px">Query plan (what actually ran)</h3>${json(r.plan)}`;
  });
}

function transformView(v) {
  v.innerHTML = `
    <h2>Transform studio</h2>
    <p class="sub">Instruction → recipe → preview on a sample → confirm. Nothing touches your file;
      results go to a new file with _ai columns unless you tick replace.</p>
    <section class="card">
      <label class="f">Instruction</label>
      <textarea id="t-i" placeholder="split address into street, city and pin"></textarea>
      <button id="t-preview">Preview</button>
      <div class="out" id="t-out"></div>
    </section>
    <section class="card">
      <h3>Saved recipes</h3>
      <div class="row">
        <div><select id="t-recipes"></select></div>
        <div><button id="t-runrecipe" class="ghost" style="margin-top:0">Run on current file</button></div>
      </div>
      <div class="out" id="t-rout"></div>
    </section>`;
  const loadRecipes = () => api("GET", "/recipes").then((r) => {
    $("#t-recipes").innerHTML = r.recipes.length
      ? r.recipes.map((n) => `<option>${esc(n)}</option>`).join("")
      : `<option value="">(none saved yet)</option>`;
  }).catch(() => {});
  loadRecipes();

  $("#t-preview").onclick = (e) => run(e.target, async () => {
    const file = needFile(); if (!file) return;
    const r = await api("POST", "/transform/preview", { file, instruction: $("#t-i").value });
    window._recipe = r.recipe;
    $("#t-out").innerHTML = `
      <p class="sub">${esc(r.note || "")} — review the sample, then apply.</p>
      <h3>Before (sample)</h3>${table(r.before, 20)}
      <h3 style="margin-top:12px">After (sample)</h3>${table(r.after, 20)}
      <h3 style="margin-top:12px">Recipe</h3>${json(r.recipe)}
      <div class="row"><div><label class="f">Save recipe as (optional)</label>
        <input type="text" id="t-save" placeholder="monthly-clean"></div></div>
      <label class="inline-check"><input type="checkbox" id="t-replace"> replace columns in place
        (instead of _ai copies)</label>
      <button id="t-apply">Apply to full file</button>`;
    $("#t-apply").onclick = (e2) => run(e2.target, async () => {
      const body = { file, recipe: window._recipe, replace: $("#t-replace").checked };
      if ($("#t-save").value.trim()) body.save_as = $("#t-save").value.trim();
      const a = await api("POST", "/transform/apply", body);
      $("#t-out").insertAdjacentHTML("beforeend",
        `<p class="pathline">written to: ${esc(a.out_path)}</p>
         <h3 style="margin-top:10px">Result sample</h3>${table(a.sample, 10)}`);
      loadRecipes();
    });
  });

  $("#t-runrecipe").onclick = (e) => run(e.target, async () => {
    const file = needFile(); if (!file) return;
    const name = $("#t-recipes").value;
    if (!name) { toast("No saved recipes yet — preview a transform and save it."); return; }
    const a = await api("POST", "/transform/apply", { file, recipe_name: name });
    $("#t-rout").innerHTML = `<p class="pathline">written to: ${esc(a.out_path)}</p>
      ${table(a.sample, 10)}`;
  });
}

function reconcileView(v) {
  v.innerHTML = `
    <h2>Reconciliation</h2>
    <p class="sub">File A is the selected file. Match levels: L1 exact · L2 within tolerance ·
      L3 fuzzy key. A 5-sheet xlsx report lands next to file A.</p>
    <section class="card">
      <label class="f">File B (path on this machine)</label>
      <input type="text" id="r-b" placeholder="C:\\data\\bank_statement.xlsx">
      <div class="row">
        <div><label class="f">Key columns (comma-separated)</label>
          <input type="text" id="r-keys" placeholder="txn_id"></div>
        <div><label class="f">Numeric tolerance</label>
          <input type="number" id="r-tol" value="0" step="0.01"></div>
        <div><label class="f">Fuzzy keys 0–1 (blank = off)</label>
          <input type="number" id="r-fuzzy" step="0.05" min="0" max="1"></div>
      </div>
      <div class="row">
        <div><label class="f">Saved profile (overrides the fields above)</label>
          <select id="r-profiles"><option value="">(none — use fields above)</option></select></div>
        <div><label class="f">Save these settings as profile (optional)</label>
          <input type="text" id="r-savename" placeholder="monthly-cms-switch"></div>
      </div>
      <button id="r-run">Run reconciliation</button>
      <div class="out" id="r-out"></div>
    </section>`;
  api("GET", "/reconcile/profiles").then((r) => {
    $("#r-profiles").insertAdjacentHTML("beforeend",
      r.profiles.map((n) => `<option>${esc(n)}</option>`).join(""));
  }).catch(() => {});

  $("#r-run").onclick = (e) => run(e.target, async () => {
    const a = needFile(); if (!a) return;
    const b = $("#r-b").value.trim();
    if (!b) { toast("Enter the path of file B."); return; }
    const body = { a, b };
    const saved = $("#r-profiles").value;
    if (saved) body.profile_name = saved;
    else {
      const profile = { keys: $("#r-keys").value.split(",").map((s) => s.trim()).filter(Boolean) };
      const tol = parseFloat($("#r-tol").value);
      if (tol) profile.tolerance = { numeric: tol };
      const fz = parseFloat($("#r-fuzzy").value);
      if (fz) profile.fuzzy_keys = fz;
      const saveName = $("#r-savename").value.trim();
      if (saveName) {
        await api("POST", `/reconcile/profiles/${encodeURIComponent(saveName)}`, { spec: profile });
        toast(`Profile '${saveName}' saved.`, true);
      }
      body.profile = profile;
    }
    const r = await api("POST", "/reconcile/run", body);
    const res = r.result;
    const tabs = { matched: res.matched, discrepancies: res.discrepancies,
                   only_in_a: res.only_in_a, only_in_b: res.only_in_b };
    $("#r-out").innerHTML = `
      ${kv(r.summary)}
      ${r.report_path ? `<p class="pathline">report: ${esc(r.report_path)}</p>` : ""}
      <div class="tabs">${Object.keys(tabs).map((k, i) =>
        `<button data-tab="${k}"${i ? "" : ' class="active"'}>${k} (${tabs[k].length})</button>`).join("")}</div>
      <div id="r-tab"></div>`;
    const show = (k) => {
      $("#r-tab").innerHTML = table(tabs[k].map(flattenDiff));
      document.querySelectorAll("[data-tab]").forEach((b) =>
        b.classList.toggle("active", b.dataset.tab === k));
    };
    document.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => show(b.dataset.tab)));
    show("matched");
  });
}

function flattenDiff(rec) {
  if (!rec.differences) return rec;
  const { a, b, differences, ...rest } = rec;
  return { ...rest, differences: Object.entries(differences).map(([col, d]) =>
    `${col}: ${d.a} → ${d.b}${d.diff_abs != null ? ` (Δ${d.diff_abs})` : ""}`).join("; ") };
}

function fraudView(v) {
  v.innerHTML = `
    <h2>Fraud</h2>
    <p class="sub">Train on labelled history, check honesty on a holdout, then score fresh files.
      Scores are risk estimates with reasons — never verdicts.</p>
    <section class="card"><h3>1 · Train (current file = labelled history)</h3>
      <div class="row">
        <div><label class="f">Label column</label><input type="text" id="f-label" placeholder="is_fraud"></div>
        <div><label class="f">Model name</label><input type="text" id="f-name" placeholder="vendor-fraud-v1"></div>
        <div><label class="f">Algorithm</label><select id="f-algo">
          <option value="gradient_boosting">gradient boosting</option>
          <option value="random_forest">random forest</option></select></div>
      </div>
      <button id="f-train">Train</button><div class="out" id="f-tout"></div>
    </section>
    <section class="card"><h3>2 · Score / evaluate (current file = fresh or holdout)</h3>
      <div class="row">
        <div><label class="f">Model</label><select id="f-models"></select></div>
        <div><label class="f">Label column (evaluate only)</label>
          <input type="text" id="f-evallabel" placeholder="is_fraud"></div>
      </div>
      <button id="f-score">Score</button>
      <button id="f-eval" class="ghost">Evaluate on holdout</button>
      <div class="out" id="f-sout"></div>
    </section>`;
  const loadModels = () => api("GET", "/fraud/models").then((r) => {
    $("#f-models").innerHTML = r.models.length
      ? r.models.map((c) => `<option>${esc(c.name)}</option>`).join("")
      : `<option value="">(no models trained yet)</option>`;
  }).catch(() => {});
  loadModels();

  $("#f-train").onclick = (e) => run(e.target, async () => {
    const file = needFile(); if (!file) return;
    const r = await api("POST", "/fraud/train", {
      file, label_column: $("#f-label").value.trim(),
      model_name: $("#f-name").value.trim() || "model",
      algorithm: $("#f-algo").value });
    const c = r.model_card;
    $("#f-tout").innerHTML = `
      ${kv({ ...c.cv_metrics, rows: c.rows, positive_label: c.positive_label })}
      <h3 style="margin-top:10px">Top features</h3>${table(c.top_features)}
      <p class="sub">${esc(r.note)}</p>${json(c)}`;
    loadModels();
  });
  $("#f-score").onclick = (e) => run(e.target, async () => {
    const file = needFile(); if (!file) return;
    const model = $("#f-models").value;
    if (!model) { toast("Train a model first."); return; }
    const r = await api("POST", "/fraud/score", { file, model_name: model });
    $("#f-sout").innerHTML = `
      ${kv({ ...r.summary.bands, flagged: r.summary.flagged, rows: r.summary.rows })}
      <p class="sub">${esc(r.summary.note)}</p>
      ${table(r.scores.map((s) => ({ row: s.row, probability: s.fraud_probability,
        risk_band: s.risk_band, top_factors: s.top_factors.map((f) =>
          `${f.feature}=${f.value} (+${f.contribution})`).join("; ") })))}`;
  });
  $("#f-eval").onclick = (e) => run(e.target, async () => {
    const file = needFile(); if (!file) return;
    const r = await api("POST", "/fraud/evaluate", {
      file, model_name: $("#f-models").value,
      label_column: $("#f-evallabel").value.trim() });
    $("#f-sout").innerHTML = `
      <h3>Holdout (real world)</h3>${kv(r.holdout_metrics)}
      <h3 style="margin-top:10px">At training (cross-validation)</h3>${kv(r.cv_metrics_at_training)}
      <p class="sub">${esc(r.note)}</p>`;
  });
}

function kycView(v) {
  v.innerHTML = `
    <h2>KYC</h2>
    <section class="card"><h3>Name matching</h3>
      <p class="sub">Pairwise: fill both columns. Cross-compare: fill only column A (+ optional group).</p>
      <div class="row">
        <div><label class="f">Column A</label><input type="text" id="k-a" placeholder="declared_name"></div>
        <div><label class="f">Column B (pairwise)</label><input type="text" id="k-b"></div>
        <div><label class="f">Group by (cross mode)</label><input type="text" id="k-g"></div>
        <div><label class="f">Threshold %</label><input type="number" id="k-t" value="50" min="0" max="100"></div>
      </div>
      <label class="inline-check"><input type="checkbox" id="k-llm"> verify candidates with the local
        LLM (offline verdicts with reasons)</label>
      <button id="k-match">Match names</button>
      <div class="out" id="k-mout"></div>
    </section>
    <section class="card"><h3>Entity dedupe</h3>
      <div class="row">
        <div><label class="f">Columns (comma-separated)</label>
          <input type="text" id="k-cols" placeholder="name, city"></div>
        <div><label class="f">Similarity %</label><input type="number" id="k-dt" value="85" min="0" max="100"></div>
        <div><label class="f">Keep</label><select id="k-strat">
          <option value="most_complete">most complete row</option>
          <option value="first">first</option><option value="last">last</option></select></div>
      </div>
      <button id="k-dedupe">Dedupe</button>
      <div class="out" id="k-dout"></div>
    </section>`;
  $("#k-match").onclick = (e) => run(e.target, async () => {
    const file = needFile(); if (!file) return;
    const r = await api("POST", "/kyc/match_names", {
      file, col_a: $("#k-a").value.trim() || null, col_b: $("#k-b").value.trim() || null,
      group_by: $("#k-g").value.trim() || null, llm_verify: $("#k-llm").checked,
      seq_threshold: parseFloat($("#k-t").value) || 50 });
    $("#k-mout").innerHTML = `${kv(r.summary)}${table(r.pairs)}`;
  });
  $("#k-dedupe").onclick = (e) => run(e.target, async () => {
    const file = needFile(); if (!file) return;
    const r = await api("POST", "/kyc/dedupe", {
      file, columns: $("#k-cols").value.split(",").map((s) => s.trim()).filter(Boolean),
      threshold: parseFloat($("#k-dt").value) || 85, strategy: $("#k-strat").value });
    $("#k-dout").innerHTML = `
      ${kv({ rows_before: r.rows_before, rows_after: r.rows_after,
             clusters_merged: r.clusters_merged })}
      <p class="pathline">deduped copy: ${esc(r.out_path)}</p>
      <h3 style="margin-top:10px">Merges</h3>
      ${table(r.merges.map((m) => ({ canonical_row: m.canonical_row,
        merged_rows: m.merged_rows.join(", "),
        values: Object.values(m.values).join(" | ") })))}`;
  });
}

function jobsView(v) {
  v.innerHTML = `
    <h2>Jobs & history</h2>
    <section class="card"><h3>Background jobs</h3><div id="j-jobs" class="out"></div></section>
    <section class="card"><h3>Audit trail (history.jsonl)</h3><div id="j-hist" class="out"></div></section>`;
  const refresh = async () => {
    if (!document.contains(v)) { clearInterval(timer); return; }
    try {
      const [jobs, hist] = [await api("GET", "/jobs"), await api("GET", "/history?limit=40")];
      $("#j-jobs").innerHTML = table(jobs.jobs.map(({ params, trace, ...j }) => j)) ;
      $("#j-hist").innerHTML = table(hist.history.map((h) => ({
        ts: h.ts, op: h.op, file: h.file ?? "", summary: h.summary ?? "" })));
    } catch (e) { /* API briefly down — keep polling */ }
  };
  const timer = setInterval(refresh, 2500);
  refresh();
}

/* ---------- file picking ---------- */

function setFile(path, label) {
  S.file = path;
  localStorage.setItem("excellia.file", path);
  $("#currentfile").textContent = label || path || "";
  $("#filepath").value = path.startsWith("/") || path.includes(":") ? path : "";
}

async function uploadFile(f) {
  $("#droplabel").textContent = "uploading…";
  try {
    const fd = new FormData();
    fd.append("file", f);
    const resp = await fetch("/upload", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "upload failed");
    setFile(data.path, `${data.name} (uploaded)`);
    toast(`Loaded ${data.name}`, true);
  } catch (e) { toast(e.message); }
  finally { $("#droplabel").innerHTML = "Drop a spreadsheet here<br>or click to pick one"; }
}

/* ---------- boot ---------- */

function route() {
  const name = location.hash.replace("#", "") || "quality";
  const view = VIEWS[name] ? name : "quality";
  document.querySelectorAll("nav a").forEach((a) =>
    a.classList.toggle("active", a.dataset.view === view));
  const main = $("#view");
  main.innerHTML = "";
  VIEWS[view].render(main);
}

function boot() {
  $("#nav").innerHTML = Object.entries(VIEWS).map(([k, v]) =>
    `<a href="#${k}" data-view="${k}">${v.label}</a>`).join("");
  window.addEventListener("hashchange", route);

  const drop = $("#drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault(); drop.classList.remove("over");
    if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
  });
  $("#fileinput").addEventListener("change", (e) => {
    if (e.target.files[0]) uploadFile(e.target.files[0]);
  });
  $("#filepath").addEventListener("change", (e) => {
    if (e.target.value.trim()) setFile(e.target.value.trim());
  });
  if (S.file) setFile(S.file);

  api("GET", "/health")
    .then((h) => { const s = $("#status"); s.textContent = `core API ${h.version}`; s.className = "status ok"; })
    .catch(() => { const s = $("#status"); s.textContent = "core API unreachable"; s.className = "status bad"; });

  route();
}

boot();
