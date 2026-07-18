const state = { candidates: [], selected: new Set(), active: null,
                filters: { severity: "", source: "" } };

const $ = (sel) => document.querySelector(sel);

async function load(refresh = false) {
  setStatus("Scanning for updates…");
  try {
    const res = await fetch("/api/updates" + (refresh ? "?refresh=1" : ""));
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    state.candidates = data.candidates || [];
    state.selected = new Set(state.candidates.filter(c => c.status === "ok").map(c => c.mod_id));
    hideStatus();
    render();
  } catch (e) {
    setStatus("Couldn't load updates: " + e.message, true);
  }
}

function visible() {
  return state.candidates.filter(c =>
    (!state.filters.severity || c.severity === state.filters.severity) &&
    (!state.filters.source || c.platform === state.filters.source));
}

function render() {
  const list = $("#mod-list");
  list.innerHTML = "";
  for (const c of visible()) {
    const row = document.createElement("div");
    row.className = "row " + (c.status !== "ok" ? c.status : "") +
                    (state.active === c.mod_id ? " active" : "");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = state.selected.has(c.mod_id);
    cb.disabled = c.status !== "ok";
    cb.addEventListener("click", (e) => { e.stopPropagation(); toggle(c.mod_id); });
    const main = document.createElement("div");
    main.className = "main";
    main.innerHTML = `<div class="name">${esc(c.name)}</div>
      <div class="ver">${esc(c.current_version)} → <b>${esc(c.latest_version)}</b></div>`;
    row.append(cb, main);
    if (c.platform === "curseforge") row.append(tag("CF"));
    row.append(badge(c.severity));
    row.addEventListener("click", () => { state.active = c.mod_id; render(); });
    list.append(row);
  }
  $("#update-count").textContent = `${state.candidates.length} updates`;
  $("#selected-count").textContent = `${state.selected.size} selected`;
  renderReader();
}

function renderReader() {
  const c = state.candidates.find(x => x.mod_id === state.active);
  const r = $("#reader");
  if (!c) { r.innerHTML = '<p class="muted">Select a mod to read its changelog.</p>'; return; }
  const link = c.platform === "modrinth" ? "Open on Modrinth ↗" : "Open on CurseForge ↗";
  let html = `<h2>${esc(c.name)} <span class="ver">${esc(c.current_version)} → <b>${esc(c.latest_version)}</b></span></h2>`;
  if (c.project_url && /^https?:\/\//i.test(c.project_url))
    html += `<a class="open" href="${esc(c.project_url)}" target="_blank" rel="noopener">${link}</a>`;
  if (c.note) html += `<div class="dep">${esc(c.note)}</div>`;
  for (const e of c.changelogs) {
    html += `<div class="cl-ver">${esc(e.version)}<span class="cl-date">${esc(e.date)}</span></div>`;
    html += `<div class="cl-body">${e.body_html || '<span class="muted">No changelog provided.</span>'}</div>`;
  }
  for (const d of c.added_dependencies) {
    const label = esc(d.name || d.id);
    const inner = d.url && /^https?:\/\//i.test(d.url)
      ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">${label} ↗</a>`
      : `<b>${label}</b>`;
    html += `<div class="dep">⚠ New required dependency: ${inner}${d.satisfied ? "" : " — not in your pack"}</div>`;
  }
  r.innerHTML = html;
}

function toggle(id) {
  if (state.selected.has(id)) state.selected.delete(id); else state.selected.add(id);
  render();
}

async function generate() {
  const ids = [...state.selected];
  if (!ids.length) { setStatus("Nothing selected.", true); return; }
  setStatus(`Downloading and hashing ${ids.length} jar(s)…`);
  try {
    const res = await fetch("/api/generate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_mod_ids: ids }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (data.failures && data.failures.length) {
      setStatus(`Wrote nothing — failures: ${data.failures.map(f => f.id).join(", ")}`, true);
    } else if (!data.written_file) {
      setStatus(data.note || "Nothing to generate.", true);
    } else {
      setStatus(`Wrote ${data.written_file}, bumped preview revision to ${data.new_revision}. ` +
                `Review the git diff, then commit & push.`);
    }
  } catch (e) {
    setStatus("Generate failed: " + e.message, true);
  }
}

function badge(sev) { const s = document.createElement("span"); s.className = "badge " + sev; s.textContent = sev; return s; }
function tag(t) { const s = document.createElement("span"); s.className = "tag"; s.textContent = t; return s; }
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}
function setStatus(msg, isError = false) { const el = $("#status"); el.textContent = msg; el.className = "status" + (isError ? " error" : ""); el.hidden = false; }
function hideStatus() { $("#status").hidden = true; }

$("#filter-severity").addEventListener("change", (e) => { state.filters.severity = e.target.value; render(); });
$("#filter-source").addEventListener("change", (e) => { state.filters.source = e.target.value; render(); });
$("#select-all").addEventListener("click", () => {
  const vis = visible().filter(c => c.status === "ok");
  const allSelected = vis.every(c => state.selected.has(c.mod_id));
  for (const c of vis) { if (allSelected) state.selected.delete(c.mod_id); else state.selected.add(c.mod_id); }
  render();
});
$("#generate").addEventListener("click", generate);
load();
