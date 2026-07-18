const state = {
  candidates: [], selected: new Set(), active: null,
  filters: { severity: "", source: "" },
  adds: [], removals: new Set(), pack: [], packLoaded: false,
  releaseFilter: "",
};
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const openLink = (u) => (u && /^https?:\/\//i.test(u))
  ? `<a class="open" href="${esc(u)}" target="_blank" rel="noopener" aria-label="Open page">↗</a>` : "";

// ---- tabs ----
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
  const name = t.dataset.tab;
  document.querySelectorAll(".tab-panel").forEach((p) => { p.hidden = p.id !== "tab-" + name; });
  if (name === "remove" && !state.packLoaded) loadPack();
}));

// ---- updates tab (existing behaviour) ----
async function load(refresh = false) {
  showLoading();
  try {
    const res = await fetch("/api/updates" + (refresh ? "?refresh=1" : ""));
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    state.candidates = data.candidates || [];
    state.selected = new Set(state.candidates.filter((c) => c.status === "ok").map((c) => c.mod_id));
    hideLoading(); renderUpdates(); renderQueue(); updateBatch();
  } catch (e) { loadingError("Couldn't load updates: " + e.message); }
}
function visible() {
  return state.candidates.filter((c) =>
    (!state.filters.severity || c.severity === state.filters.severity) &&
    (!state.filters.source || c.platform === state.filters.source));
}
function renderUpdates() {
  const list = $("#mod-list"); list.innerHTML = "";
  for (const c of visible()) {
    const row = document.createElement("div");
    row.className = "row " + (c.status !== "ok" ? c.status : "") + (state.active === c.mod_id ? " active" : "");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = state.selected.has(c.mod_id); cb.disabled = c.status !== "ok";
    cb.addEventListener("click", (e) => { e.stopPropagation(); toggleUpdate(c.mod_id); });
    const main = document.createElement("div"); main.className = "main";
    main.innerHTML = `<div class="name">${esc(c.name)}</div><div class="ver">${esc(c.current_version)} → <b>${esc(c.latest_version)}</b></div>`;
    row.append(cb, main);
    if (c.platform === "curseforge") { const t = document.createElement("span"); t.className = "tag"; t.textContent = "CF"; row.append(t); }
    const b = document.createElement("span"); b.className = "badge " + c.severity; b.textContent = c.severity; row.append(b);
    row.addEventListener("click", () => { state.active = c.mod_id; renderUpdates(); });
    list.append(row);
  }
  $("#update-count").textContent = `${state.candidates.length} updates`;
  $("#selected-count").textContent = `${state.selected.size} selected`;
  renderReader();
}
function renderReader() {
  const c = state.candidates.find((x) => x.mod_id === state.active); const r = $("#reader");
  if (!c) { r.innerHTML = '<p class="muted">Select a mod to read its changelog.</p>'; return; }
  const link = c.platform === "modrinth" ? "Open on Modrinth ↗" : "Open on CurseForge ↗";
  let h = `<h2>${esc(c.name)} <span class="ver">${esc(c.current_version)} → <b>${esc(c.latest_version)}</b></span></h2>`;
  if (c.project_url && /^https?:\/\//i.test(c.project_url)) h += `<a class="open" href="${esc(c.project_url)}" target="_blank" rel="noopener">${link}</a>`;
  if (c.note) h += `<div class="dep">${esc(c.note)}</div>`;
  for (const e of c.changelogs) { h += `<div class="cl-ver">${esc(e.version)}<span class="cl-date">${esc(e.date)}</span></div><div class="cl-body">${e.body_html || '<span class="muted">No changelog provided.</span>'}</div>`; }
  for (const d of c.added_dependencies) {
    const label = esc(d.name || d.slug || d.id);
    const tail = d.addable
      ? ` <span class="muted">(${esc(d.version)})</span> — added to the Add queue`
      : " — not in your pack; add it manually";
    h += `<div class="dep">⚠ New required dependency: <b>${label}</b>${tail}</div>`;
  }
  r.innerHTML = h;
}
function toggleUpdate(id) {
  state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id);
  renderUpdates(); renderQueue(); updateBatch();
}
$("#filter-severity").addEventListener("change", (e) => { state.filters.severity = e.target.value; renderUpdates(); });
$("#filter-source").addEventListener("change", (e) => { state.filters.source = e.target.value; renderUpdates(); });
$("#select-all").addEventListener("click", () => {
  const vis = visible().filter((c) => c.status === "ok");
  const all = vis.every((c) => state.selected.has(c.mod_id));
  vis.forEach((c) => all ? state.selected.delete(c.mod_id) : state.selected.add(c.mod_id));
  renderUpdates(); renderQueue(); updateBatch();
});

// ---- add tab ----
async function runSearch() {
  const q = $("#add-query").value.trim(); if (!q) return;
  const platform = $("#add-platform").value;
  $("#add-results").innerHTML = '<p class="muted" style="padding:.5rem">Searching…</p>';
  try {
    const looksLink = /https?:\/\//i.test(q) || /^\d+$/.test(q);
    const url = looksLink ? "/api/resolve?ref=" + encodeURIComponent(q)
                          : `/api/search?q=${encodeURIComponent(q)}&platform=${platform}`;
    const res = await fetch(url); if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const hits = looksLink ? (data.hit ? [data.hit] : []) : data.hits;
    renderResults(hits);
  } catch (e) { $("#add-results").innerHTML = `<p class="muted" style="padding:.5rem">Search failed: ${esc(e.message)}</p>`; }
}
function renderResults(hits) {
  const box = $("#add-results"); box.innerHTML = "";
  if (!hits.length) { box.innerHTML = '<p class="muted" style="padding:.5rem">No results. Try a link or id.</p>'; return; }
  for (const hit of hits.slice(0, 12)) {
    const row = document.createElement("div"); row.className = "add-row";
    const inPack = state.pack.some((m) => m.name.toLowerCase() === hit.name.toLowerCase());
    row.innerHTML = `<div class="main"><div class="name">${esc(hit.name)}</div><div class="sum">${esc(hit.summary)}</div></div>
      <span class="tag">${hit.platform === "curseforge" ? "CF" : "MR"}</span>${openLink(hit.page_url)}
      <select class="ver-sel"><option>loading…</option></select>
      <button class="add-btn" disabled>${inPack ? "In pack" : "Add"}</button>`;
    box.append(row);
    const sel = row.querySelector(".ver-sel");
    const btn = row.querySelector(".add-btn");
    // fetch each row's versions in parallel — don't block rendering the next row
    fetchVersions(hit).then((versions) => {
      populateVersions(sel, versions);
      if (!versions.length) { sel.innerHTML = "<option>no compatible versions</option>"; return; }
      btn.disabled = inPack;
      btn.addEventListener("click", () => {
        const opt = versions.find((v) => v.ref === sel.value);
        if (opt) queueAdd(hit, opt, versions.side);
      });
    }).catch(() => { sel.innerHTML = "<option>versions unavailable</option>"; });
  }
}
async function fetchVersions(hit) {
  const res = await fetch(`/api/project-versions?platform=${hit.platform}&id=${encodeURIComponent(hit.id)}`);
  if (!res.ok) return Object.assign([], { side: "BOTH" });
  const data = await res.json();
  const arr = data.versions || []; arr.side = data.side || "BOTH"; return arr;
}
function populateVersions(sel, versions) {
  const rf = state.releaseFilter;
  const shown = versions.filter((v) => !rf || v.type === rf);
  sel.innerHTML = (shown.length ? shown : versions)
    .map((v) => `<option value="${esc(v.ref)}">${esc(v.name)} (${esc(v.type)})</option>`).join("");
}
function queueAdd(hit, opt, side) {
  if (state.adds.some((a) => a.module_id === hit.slug)) return;
  state.adds.push({ platform: hit.platform, module_id: hit.slug, name: hit.name,
    version: opt.name, url: opt.url, side: side || "BOTH", required: true, page_url: hit.page_url });
  renderQueue(); updateBatch();
}
// Derived: new deps of currently-selected updates, deduped by slug, one entry
// per dep with the names of every selected mod that introduced it. Skips deps
// that aren't addable or are already queued manually. (Deps already in the pack
// are excluded upstream — the scan only reports a required dependency whose
// Modrinth project id isn't already installed — so no pack check is needed.)
function computeAutoDeps() {
  const bySlug = new Map();
  for (const c of state.candidates) {
    if (!state.selected.has(c.mod_id)) continue;
    for (const d of (c.added_dependencies || [])) {
      if (!d.addable || !d.slug) continue;
      if (state.adds.some((a) => a.module_id === d.slug)) continue;
      const e = bySlug.get(d.slug) || { dep: d, requiredBy: [] };
      if (!e.requiredBy.includes(c.name)) e.requiredBy.push(c.name);
      bySlug.set(d.slug, e);
    }
  }
  return [...bySlug.values()];
}
function renderQueue() {
  const box = $("#add-queue"); box.innerHTML = "";
  const auto = computeAutoDeps();
  for (const { dep, requiredBy } of auto) {
    const row = document.createElement("div"); row.className = "add-row auto-dep";
    const chips = requiredBy.map((n) => `<span class="dep-chip">dep of ${esc(n)}</span>`).join("");
    row.innerHTML = `<span class="tag">MR</span>
      <div class="main"><div class="name">${esc(dep.name || dep.slug)}</div>
        <div class="dep-chips">${chips}</div></div>
      <span class="ver">${esc(dep.version)}</span>${openLink(dep.url)}`;
    box.append(row);
  }
  for (const a of state.adds) {
    const row = document.createElement("div"); row.className = "add-row";
    row.innerHTML = `<span class="tag">${a.platform === "curseforge" ? "CF" : "MR"}</span>
      <div class="main"><div class="name">${esc(a.name)}</div></div>
      <span class="ver">${esc(a.version)}</span>${openLink(a.page_url)}
      <button class="rm-btn">✕</button>`;
    row.querySelector(".rm-btn").addEventListener("click", () => {
      state.adds = state.adds.filter((x) => x !== a); renderQueue(); updateBatch();
    });
    box.append(row);
  }
  $("#add-queue-count").textContent = auto.length + state.adds.length;
}
$("#add-search-btn").addEventListener("click", runSearch);
$("#add-query").addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(); });
$("#add-release").addEventListener("change", (e) => { state.releaseFilter = e.target.value; runSearch(); });

// ---- remove tab ----
async function loadPack() {
  try {
    const res = await fetch("/api/pack"); if (!res.ok) throw new Error("HTTP " + res.status);
    state.pack = (await res.json()).mods || []; state.packLoaded = true; renderRemove();
  } catch (e) { $("#remove-list").innerHTML = `<p class="muted" style="padding:.5rem">Couldn't load pack: ${esc(e.message)}</p>`; }
}
function renderRemove() {
  const q = ($("#remove-filter").value || "").toLowerCase();
  const plat = $("#remove-platform").value;
  const list = $("#remove-list"); list.innerHTML = "";
  for (const m of state.pack) {
    if (q && !m.name.toLowerCase().includes(q)) continue;
    if (plat && m.platform !== plat) continue;
    const row = document.createElement("div"); row.className = "row";
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = state.removals.has(m.mod_id);
    cb.addEventListener("click", () => { cb.checked ? state.removals.add(m.mod_id) : state.removals.delete(m.mod_id); updateBatch(); });
    const main = document.createElement("div"); main.className = "main";
    main.innerHTML = `<div class="name">${esc(m.name)}</div><div class="ver">${esc(m.version)}</div>`;
    row.append(cb, main);
    if (m.platform === "curseforge") { const t = document.createElement("span"); t.className = "tag"; t.textContent = "CF"; row.append(t); }
    list.append(row);
  }
}
$("#remove-filter").addEventListener("input", renderRemove);
$("#remove-platform").addEventListener("change", renderRemove);

// ---- batch + review + generate ----
function batchCounts() {
  return { u: state.selected.size, a: state.adds.length + computeAutoDeps().length,
           r: state.removals.size };
}
function updateBatch() {
  const b = batchCounts();
  $("#batch-summary").textContent = `${b.u} updates · ${b.a} adds · ${b.r} removals`;
}
function openReview() {
  const body = $("#review-body");
  const upd = [...state.selected].map((id) => state.candidates.find((c) => c.mod_id === id)).filter(Boolean);
  const rem = [...state.removals].map((id) => state.pack.find((m) => m.mod_id === id) || { mod_id: id, name: id });
  const sec = (title, items, render) => items.length
    ? `<div class="review-sec">${title} (${items.length})</div>` + items.map(render).join("") : "";
  const autoAdds = computeAutoDeps().map(({ dep, requiredBy }) =>
    ({ name: dep.name || dep.slug, version: dep.version, auto: true, requiredBy }));
  const addsForReview = [...state.adds, ...autoAdds];
  body.innerHTML =
    sec("Updates", upd, (c) => `<div class="review-item">${esc(c.name)} <span class="muted">${esc(c.current_version)} → ${esc(c.latest_version)}</span><button data-t="u" data-id="${esc(c.mod_id)}">remove</button></div>`) +
    sec("Adds", addsForReview, (a) => a.auto
      ? `<div class="review-item">+ ${esc(a.name)} <span class="muted">${esc(a.version)}</span> <span class="dep-chip">dep of ${esc(a.requiredBy.join(", "))}</span></div>`
      : `<div class="review-item">+ ${esc(a.name)} <span class="muted">${esc(a.version)}</span><button data-t="a" data-id="${esc(a.module_id)}">remove</button></div>`) +
    sec("Removals", rem, (m) => `<div class="review-item">− ${esc(m.name)}<button data-t="r" data-id="${esc(m.mod_id)}">keep</button></div>`) ||
    '<p class="muted">Nothing queued yet.</p>';
  body.querySelectorAll("button").forEach((btn) => btn.addEventListener("click", () => {
    const { t, id } = btn.dataset;
    if (t === "u") state.selected.delete(id);
    else if (t === "a") state.adds = state.adds.filter((x) => x.module_id !== id);
    else state.removals.delete(id);
    renderUpdates(); renderQueue(); if (state.packLoaded) renderRemove(); updateBatch(); openReview();
  }));
  $("#review").hidden = false;
}
$("#review-btn").addEventListener("click", openReview);
$("#review-close").addEventListener("click", () => { $("#review").hidden = true; });
async function generate() {
  const autoAdds = computeAutoDeps().map(({ dep }) => ({
    platform: "modrinth", module_id: dep.slug, name: dep.name, version: dep.version,
    url: dep.download_url, side: dep.side, required: true }));
  const payload = { updates: [...state.selected],
    adds: [...state.adds.map(({ page_url, ...a }) => a), ...autoAdds],
    removals: [...state.removals] };
  if (!payload.updates.length && !payload.adds.length && !payload.removals.length) { setStatus("Nothing queued.", true); return; }
  $("#review").hidden = true;
  setStatus(`Downloading and hashing ${payload.updates.length + payload.adds.length} jar(s)…`);
  try {
    const res = await fetch("/api/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (data.failures && data.failures.length) setStatus(`Wrote nothing — failures: ${data.failures.map((f) => f.id).join(", ")}`, true);
    else if (!data.written_file) setStatus(data.note || "Nothing to generate.", true);
    else setStatus(`Wrote ${data.written_file}, bumped preview revision to ${data.new_revision}. Review the git diff, then commit & push.`);
  } catch (e) { setStatus("Generate failed: " + e.message, true); }
}
$("#generate").addEventListener("click", generate);
$("#review-generate").addEventListener("click", generate);

// ---- shared helpers ----
function setStatus(msg, isError = false) { const el = $("#status"); el.textContent = msg; el.className = "status" + (isError ? " error" : ""); el.hidden = false; }
function showLoading() { const el = $("#loading"); el.hidden = false; el.classList.remove("error"); $("#loading-text").textContent = "Scanning for updates…"; $("#loading-retry").hidden = true; }
function hideLoading() { $("#loading").hidden = true; }
function loadingError(msg) { const el = $("#loading"); el.hidden = false; el.classList.add("error"); $("#loading-text").textContent = msg; $("#loading-retry").hidden = false; }
$("#loading-retry").addEventListener("click", () => load(true));
load();
loadPack();  // eager: so the "already in pack" check works on the Add tab from a cold start
