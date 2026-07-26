const state = {
  candidates: [], selected: new Set(), active: null,
  filters: { severity: "", source: "", text: "" },
  adds: [], removals: new Set(), pack: [], packLoaded: false,
  releaseFilter: "", dismissed: new Set(), manualCollapsed: false,
};
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const openLink = (u) => (u && /^https?:\/\//i.test(u))
  ? `<a class="open" href="${esc(u)}" target="_blank" rel="noopener" aria-label="Open page">↗</a>` : "";
function renderWarnings(list, container) {
  if (!container) return;
  container.innerHTML = "";
  const shown = (list || []).filter((n) => !state.dismissed.has(n.code));
  container.hidden = shown.length === 0;
  for (const n of shown) {
    const row = document.createElement("div");
    row.className = "notice " + (n.level === "info" ? "info" : "warn");
    const span = document.createElement("span");
    span.textContent = (n.level === "info" ? "ⓘ " : "⚠ ") + n.message;
    const x = document.createElement("button");
    x.type = "button"; x.className = "notice-x"; x.textContent = "✕"; x.setAttribute("aria-label", "Dismiss");
    x.addEventListener("click", () => { state.dismissed.add(n.code); renderWarnings(list, container); });
    row.append(span, x);
    container.append(row);
  }
}

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
    if (refresh) state.dismissed.clear();
    state.candidates = data.candidates || [];
    state.selected = new Set(state.candidates.filter((c) => c.status === "ok").map((c) => c.mod_id));
    hideLoading(); renderUpdates(); renderQueue(); updateBatch();
    renderWarnings(data.warnings || [], $("#scan-warnings"));
  } catch (e) { loadingError("Couldn't load updates: " + e.message); }
}
function matchesFilters(c) {
  return (!state.filters.severity || c.severity === state.filters.severity) &&
         (!state.filters.source || c.platform === state.filters.source) &&
         (!state.filters.text || c.name.toLowerCase().includes(state.filters.text));
}
function visible() { return state.candidates.filter((c) => c.status !== "manual" && matchesFilters(c)); }
function manualVisible() { return state.candidates.filter((c) => c.status === "manual" && matchesFilters(c)); }
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
  $("#update-count").textContent = `${state.candidates.filter((c) => c.status === "ok").length} updates`;
  $("#selected-count").textContent = `${state.selected.size} selected`;
  renderManual();
  renderReader();
}
function renderManual() {
  const band = $("#manual-updates");
  band.innerHTML = "";
  const rows = manualVisible();
  band.hidden = rows.length === 0;
  if (!rows.length) return;
  const head = document.createElement("div");
  head.className = "manual-head" + (state.manualCollapsed ? " collapsed" : "");
  head.innerHTML = `<span class="manual-title">⚠ Needs manual update (${rows.length})</span><span class="caret">▾</span>`;
  head.addEventListener("click", () => { state.manualCollapsed = !state.manualCollapsed; renderManual(); });
  band.append(head);
  if (state.manualCollapsed) return;
  const body = document.createElement("div"); body.className = "manual-body";
  for (const c of rows) {
    const row = document.createElement("div");
    row.className = "manual-row" + (state.active === c.mod_id ? " active" : "");
    const main = document.createElement("div"); main.className = "main";
    main.innerHTML = `<div class="name">${esc(c.name)}</div><div class="ver">${esc(c.current_version)} → <b>${esc(c.latest_version)}</b></div>`;
    const reason = document.createElement("div"); reason.className = "reason muted";
    reason.textContent = c.note || "";
    const link = document.createElement("span");
    link.innerHTML = openLink(c.project_url);
    row.append(main, reason, link);
    row.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;               // let the "open page" link work
      state.active = c.mod_id; renderUpdates();
    });
    body.append(row);
  }
  band.append(body);
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
$("#updates-filter").addEventListener("input", (e) => { state.filters.text = e.target.value.toLowerCase(); renderUpdates(); });
$("#select-all").addEventListener("click", () => {
  const vis = visible().filter((c) => c.status === "ok");
  const all = vis.every((c) => state.selected.has(c.mod_id));
  vis.forEach((c) => all ? state.selected.delete(c.mod_id) : state.selected.add(c.mod_id));
  renderUpdates(); renderQueue(); updateBatch();
});

// Keyboard nav for the Updates list: ↑/↓ (+ k/j) move the active row through the
// filtered visible() order, Enter opens its page, Space toggles its selection.
// Gated so it never fires on other tabs or while typing in an input/select.
document.addEventListener("keydown", (e) => {
  if ($("#tab-updates").hidden || !$("#review").hidden || !$("#result").hidden) return;
  const el = document.activeElement;
  if (el && /^(INPUT|SELECT|TEXTAREA|BUTTON|A)$/.test(el.tagName)) return;
  const rows = visible();
  if (!rows.length) return;
  const idx = rows.findIndex((c) => c.mod_id === state.active);   // -1 if active is filtered out / unset
  if (["ArrowDown", "ArrowUp", "j", "k"].includes(e.key)) {
    e.preventDefault();
    const down = e.key === "ArrowDown" || e.key === "j";
    const next = idx < 0 ? 0 : Math.min(Math.max(idx + (down ? 1 : -1), 0), rows.length - 1);
    state.active = rows[next].mod_id;
    renderUpdates();
    const activeRow = $("#mod-list").children[next];              // render order === visible() order
    if (activeRow) activeRow.scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") {
    const c = rows[idx];
    if (c && c.project_url && /^https?:\/\//i.test(c.project_url)) {
      e.preventDefault();
      window.open(c.project_url, "_blank", "noopener");
    }
  } else if (e.key === " " || e.key === "Spacebar") {
    const c = rows[idx];
    if (c && c.status === "ok") { e.preventDefault(); toggleUpdate(c.mod_id); }
  }
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
    renderWarnings(looksLink ? [] : (data.warnings || []), $("#add-warnings"));
    renderResults(hits);
  } catch (e) { $("#add-results").innerHTML = `<p class="muted" style="padding:.5rem">Search failed: ${esc(e.message)}</p>`; }
}
function renderResults(hits) {
  const box = $("#add-results"); box.innerHTML = "";
  if (!hits.length) { box.innerHTML = '<p class="muted" style="padding:.5rem">No results. Try a link or id.</p>'; return; }
  for (const hit of hits.slice(0, 12)) {
    const wrap = document.createElement("div"); wrap.className = "add-result";
    const row = document.createElement("div"); row.className = "add-row";
    const inPack = state.pack.some((m) => m.name.toLowerCase() === hit.name.toLowerCase());
    row.innerHTML = `<button class="disc" type="button" aria-expanded="false" aria-label="Toggle details">▸</button>
      <div class="main"><div class="name">${esc(hit.name)}</div><div class="sum">${esc(hit.summary)}</div></div>
      <span class="tag">${hit.platform === "curseforge" ? "CF" : "MR"}</span>${openLink(hit.page_url)}
      <select class="ver-sel"><option>loading…</option></select>
      <button class="add-btn" disabled>${inPack ? "In pack" : "Add"}</button>`;
    const preview = document.createElement("div"); preview.className = "add-preview"; preview.hidden = true;
    wrap.append(row, preview);
    box.append(wrap);
    const sel = row.querySelector(".ver-sel");
    const btn = row.querySelector(".add-btn");
    const toggle = () => togglePreview(wrap, hit, sel);
    row.querySelector(".disc").addEventListener("click", toggle);
    row.querySelector(".name").addEventListener("click", toggle);
    sel.addEventListener("change", () => { if (!preview.hidden) loadPreview(preview, hit, sel); });
    // fetch each row's versions in parallel — don't block rendering the next row
    fetchVersions(hit).then((versions) => {
      populateVersions(sel, versions);
      if (!versions.length) { sel.innerHTML = "<option>no compatible versions</option>"; return; }
      btn.disabled = inPack;
      btn.addEventListener("click", () => {
        const opt = versions.find((v) => v.ref === sel.value);
        if (opt) queueAdd(hit, opt, versions.side);
      });
      if (!preview.hidden) loadPreview(preview, hit, sel);   // refresh if expanded before versions arrived
    }).catch(() => { sel.innerHTML = "<option>versions unavailable</option>"; });
  }
}

function togglePreview(wrap, hit, sel) {
  const preview = wrap.querySelector(".add-preview");
  const disc = wrap.querySelector(".disc");
  const open = preview.hidden;                 // currently hidden -> we're opening it
  preview.hidden = !open;
  disc.textContent = open ? "▾" : "▸";
  disc.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) loadPreview(preview, hit, sel);
}

async function loadPreview(preview, hit, sel) {
  const req = (preview._req = (preview._req || 0) + 1);
  const descHtml = `<div class="cl-ver">Description</div><div class="cl-body">${esc(hit.summary) || '<span class="muted">No description.</span>'}</div>`;
  const optEl = sel.options[sel.selectedIndex];
  const label = optEl ? optEl.textContent : "";
  const placeholder = /^(loading…|no compatible versions|versions unavailable)$/.test(label);
  if (!sel.value || placeholder) {
    preview.innerHTML = descHtml + `<div class="cl-ver">Changelog</div><div class="cl-body muted">Select a version.</div>`;
    return;
  }
  preview.innerHTML = descHtml + `<div class="cl-ver">Changelog</div><div class="cl-body muted">Loading changelog…</div>`;
  try {
    const cl = await fetchChangelog(hit.platform, hit.id, sel.value);
    if (preview._req !== req) return;   // a newer load superseded this one
    const ver = cl.version || label;
    const date = cl.date ? `<span class="cl-date">${esc(cl.date)}</span>` : "";
    const bodyHtml = cl.body_html || '<span class="muted">No changelog provided.</span>';
    preview.innerHTML = descHtml + `<div class="cl-ver">${esc(ver)}${date}</div><div class="cl-body">${bodyHtml}</div>`;
  } catch (e) {
    if (preview._req !== req) return;   // a newer load superseded this one
    preview.innerHTML = descHtml + `<div class="cl-ver">Changelog</div><div class="cl-body muted">Changelog unavailable.</div>`;
  }
}

async function fetchChangelog(platform, id, ref) {
  const res = await fetch(`/api/project-changelog?platform=${encodeURIComponent(platform)}&id=${encodeURIComponent(id)}&ref=${encodeURIComponent(ref)}`);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
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
  openResultModal();
  try {
    const res = await fetch("/api/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok || !res.body) throw new Error("HTTP " + res.status);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "", result = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
        if (!line) continue;
        const evt = JSON.parse(line);
        if (evt.type === "progress") renderProgress(evt);
        else if (evt.type === "result") result = evt;
      }
    }
    if (!result) throw new Error("No result from server");
    renderResult(result);
  } catch (e) { resultError("Generate failed: " + e.message); }
}

// ---- result modal: state + rendering ----
function openResultModal() {
  $("#result").hidden = false;
  $("#result-title").textContent = "Generating…";
  $("#result-error").hidden = true;
  $("#result-progress").hidden = false;
  $("#result-progress-text").textContent = "Starting…";
  $("#result-body").hidden = true; $("#result-body").innerHTML = "";
  $("#result-foot").hidden = true;
  $("#result-close").hidden = true;
  $("#commit-btn").disabled = false; $("#discard-btn").disabled = false;
}
function closeResultModal() { $("#result").hidden = true; }
function renderProgress(evt) {
  const t = $("#result-progress-text");
  t.textContent = evt.phase === "scanning" ? "Re-scanning for updates…"
    : `Hashing ${evt.i} / ${evt.n} · ${evt.name}…`;
}
function resultError(msg, retry = false) {
  $("#result-progress").hidden = true;
  const err = $("#result-error"); err.textContent = msg; err.hidden = false;
  $("#result-close").hidden = false;
  $("#result-foot").hidden = !retry;
  $("#commit-btn").disabled = false; $("#discard-btn").disabled = false;
}
function renderDiff(text) {
  if (!text || !text.trim()) return '<p class="muted">No diff available.</p>';
  const cls = (l) =>
    l.startsWith("+++") || l.startsWith("---") ? "meta" :
    l.startsWith("@@") ? "hunk" :
    l.startsWith("+") ? "add" :
    l.startsWith("-") ? "del" :
    (l.startsWith("diff ") || l.startsWith("index ") || l.startsWith("new file") || l.startsWith("deleted file")) ? "meta" : "";
  const lines = text.split("\n").map((l) => `<div class="dl ${cls(l)}">${esc(l) || "&nbsp;"}</div>`).join("");
  return `<div class="diff">${lines}</div>`;
}
function resultSummaryHtml() {
  const upd = [...state.selected].map((id) => state.candidates.find((c) => c.mod_id === id)).filter(Boolean);
  const rem = [...state.removals].map((id) => state.pack.find((m) => m.mod_id === id) || { mod_id: id, name: id });
  const autoAdds = computeAutoDeps().map(({ dep, requiredBy }) => ({ name: dep.name || dep.slug, version: dep.version, auto: true, requiredBy }));
  const adds = [...state.adds, ...autoAdds];
  const sec = (title, items, render) => items.length
    ? `<div class="review-sec">${title} (${items.length})</div>` + items.map(render).join("") : "";
  return (
    sec("Updates", upd, (c) => `<div class="review-item">${esc(c.name)} <span class="muted">${esc(c.current_version)} → ${esc(c.latest_version)}</span></div>`) +
    sec("Adds", adds, (a) => `<div class="review-item">+ ${esc(a.name)} <span class="muted">${esc(a.version)}</span>${a.auto ? ` <span class="dep-chip">dep of ${esc(a.requiredBy.join(", "))}</span>` : ""}</div>`) +
    sec("Removals", rem, (m) => `<div class="review-item">− ${esc(m.name)}</div>`)
  ) || '<p class="muted">Nothing queued.</p>';
}
function renderResult(result) {
  $("#result-progress").hidden = true;
  const body = $("#result-body"), foot = $("#result-foot");
  const failures = result.failures || [];
  if (failures.length) {
    $("#result-title").textContent = "Generate failed";
    body.innerHTML = `<p class="muted">No file was written — these downloads failed:</p>` +
      failures.map((f) => `<div class="review-item">✕ ${esc(f.id)} <span class="muted">${esc(f.error)}</span></div>`).join("");
    body.hidden = false; foot.hidden = true; $("#result-close").hidden = false; return;
  }
  if (!result.written_file) {
    $("#result-title").textContent = "Nothing written";
    body.innerHTML = `<p class="muted">${esc(result.note || "Nothing queued.")}</p>`;
    body.hidden = false; foot.hidden = true; $("#result-close").hidden = false; return;
  }
  $("#result-title").textContent = "Review & commit preview";
  const manual = result.manual_count
    ? `<div class="manual-note">⚠ ${result.manual_count} mod(s) in this scan need manual updating (CurseForge-blocked) and were not included.</div>` : "";
  body.innerHTML = manual + resultSummaryHtml() +
    `<div class="review-sec">Diff — ${esc(result.written_file)} + preview pack</div>` +
    renderDiff(result.diff);
  body.hidden = false;
  const date = (result.written_file.match(/updates-(\d{4}-\d{2}-\d{2})/) || [])[1] || "";
  const b = batchCounts();
  const segs = [];
  if (b.u) segs.push(`${b.u} update${b.u > 1 ? "s" : ""}`);
  if (b.a) segs.push(`${b.a} add${b.a > 1 ? "s" : ""}`);
  if (b.r) segs.push(`${b.r} removal${b.r > 1 ? "s" : ""}`);
  $("#commit-message").value = `chore(preview): update ${date} — ${segs.join(", ")}`;
  foot.hidden = false; $("#result-close").hidden = false;
}
$("#generate").addEventListener("click", generate);
$("#review-generate").addEventListener("click", generate);
async function commitPreview() {
  const message = $("#commit-message").value.trim();
  if (!message) { $("#commit-message").focus(); return; }
  $("#result-error").hidden = true;
  $("#commit-btn").disabled = true; $("#discard-btn").disabled = true;
  $("#result-title").textContent = "Touch your YubiKey to sign the commit…";
  try {
    const res = await fetch("/api/commit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
    const data = await res.json();
    if (data.ok) {
      $("#result-title").textContent = "Committed ✓";
      $("#result-foot").hidden = true;
      $("#result-body").innerHTML = `<p>Committed <b>${esc(data.sha)}</b>. Run <code>git push</code> when you're ready to make the preview live for MCUpdater testing.</p>`;
      $("#result-close").hidden = false;
    } else {
      $("#discard-btn").disabled = false;
      resultError(data.error || "Commit failed.", true);
    }
  } catch (e) { $("#discard-btn").disabled = false; resultError("Commit failed: " + e.message, true); }
}
async function discardChanges() {
  if (!confirm("Discard the generated changes? This reverts the preview pack and deletes the new update file.")) return;
  $("#discard-btn").disabled = true; $("#commit-btn").disabled = true;
  try {
    const res = await fetch("/api/discard", { method: "POST" });
    const data = await res.json();
    if (data.ok === false) { resultError(data.error || "Discard failed.", true); }
    else { closeResultModal(); setStatus("Discarded the generated changes — working tree restored."); }
  } catch (e) { resultError("Discard failed: " + e.message); }
}
$("#commit-btn").addEventListener("click", commitPreview);
$("#discard-btn").addEventListener("click", discardChanges);
$("#result-close").addEventListener("click", closeResultModal);

// ---- shared helpers ----
function setStatus(msg, isError = false) { const el = $("#status"); el.textContent = msg; el.className = "status" + (isError ? " error" : ""); el.hidden = false; }
function showLoading() { const el = $("#loading"); el.hidden = false; el.classList.remove("error"); $("#loading-text").textContent = "Scanning for updates…"; $("#loading-retry").hidden = true; }
function hideLoading() { $("#loading").hidden = true; }
function loadingError(msg) { const el = $("#loading"); el.hidden = false; el.classList.add("error"); $("#loading-text").textContent = msg; $("#loading-retry").hidden = false; }
$("#loading-retry").addEventListener("click", () => load(true));
load();
loadPack();  // eager: so the "already in pack" check works on the Add tab from a cold start
