// Interface: reads state, draws the map, timeline and lists, and wires up controls.
import { sampleDay, PARAMS, SKILLS, PRIORITIES, AREAS, MAP, formatTime, validateJob } from './model.js';
import { evaluatePlan, manualPlan, autoSchedule, explainUnassigned, moveJob } from './scheduler.js';
import { importJobsCsv, exportScheduleCsv, exportJobsCsv } from './csv.js';
import { loadState, saveState, clearState } from './storage.js';

const $ = (sel) => document.querySelector(sel);
const SVG = 'http://www.w3.org/2000/svg';
const PLAN_LABELS = { manual: 'Manual plan', auto: 'Auto-scheduled', edited: 'Changed by hand' };
const FLAG_TEXT = {
  skill: 'technician does not have the skill',
  late: 'finishes after the window closes',
  overtime: 'finishes after working hours',
};

let state;
let selectedId = null;
let lastRunMs = null;

function freshState() {
  const { jobs, techs } = sampleDay();
  return { jobs, techs, routes: manualPlan(jobs, techs), mode: 'manual' };
}

function cleanRoutes(s) {
  const ids = new Set(s.jobs.map((j) => j.id));
  const seen = new Set();
  const routes = {};
  for (const t of s.techs) {
    routes[t.id] = (s.routes[t.id] || []).filter((id) => ids.has(id) && !seen.has(id) && seen.add(id));
  }
  return routes;
}

function init() {
  const saved = loadState();
  state = saved.state ? { ...saved.state, routes: cleanRoutes(saved.state) } : freshState();
  $('#a-factor').textContent = PARAMS.roadFactor;
  $('#a-speed').textContent = `${PARAMS.speedKmh} km/h`;
  $('#skill-select').innerHTML = SKILLS.map((s) => `<option>${s}</option>`).join('');
  bindControls();
  try {
    render();
    if (saved.discarded) setStatus('Saved data in this browser could not be read, so it was cleared and the sample day was loaded.', true);
  } catch {
    clearState();
    state = freshState();
    render();
    setStatus('Saved data in this browser could not be used, so it was cleared and the sample day was loaded.', true);
  }
}

function commit(mode, message, focusTarget) {
  if (mode) state.mode = mode;
  if (!saveState(state)) setStatus(`${message ? message + ' ' : ''}(Saving is unavailable in this browser, so changes last until the page is closed.)`);
  else if (message) setStatus(message);
  render(focusTarget);
}

function setStatus(text, isError = false) {
  const el = $('#status');
  el.textContent = text;
  el.classList.toggle('error', isError);
}

const techIndex = (id) => state.techs.findIndex((t) => t.id === id) + 1;
const jobById = () => new Map(state.jobs.map((j) => [j.id, j]));
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Remember which control had focus so a redraw does not throw keyboard users back to the top.
function focusKey() {
  const a = document.activeElement;
  if (!a || a === document.body) return null;
  if (a.id) return `#${a.id}`;
  for (const k of ['job', 'select', 'edit', 'remove']) {
    if (a.dataset && a.dataset[k]) {
      const box = ['#timeline', '#map', '#jobs-table', '#unassigned', '#issues'].find((b) => a.closest(b));
      return `${box ? box + ' ' : ''}[data-${k}="${a.dataset[k]}"]`;
    }
  }
  return null;
}

function restoreFocus(key) {
  let target = key ? document.querySelector(key) : null;
  if (target && target.disabled) target = null;
  if (!target && key && selectedId) {
    target = document.querySelector(`#timeline [data-job="${selectedId}"]`) || document.querySelector(`#unassigned [data-select="${selectedId}"]`);
  }
  if (!target && key) target = document.querySelector('#selected-title');
  if (target && target !== document.activeElement) {
    if (target.id === 'selected-title') target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
  }
}

function render(focusTarget) {
  const key = focusTarget === undefined ? focusKey() : focusTarget;
  draw();
  restoreFocus(key);
}

function draw() {
  const plan = evaluatePlan(state.jobs, state.techs, state.routes);
  const hand = evaluatePlan(state.jobs, state.techs, manualPlan(state.jobs, state.techs));
  if (selectedId && !state.jobs.some((j) => j.id === selectedId)) selectedId = null;
  renderStats(plan.totals, hand.totals);
  renderMap(plan);
  renderTimeline(plan);
  renderUnassigned(plan);
  renderIssues(plan);
  renderSelected(plan);
  renderJobs(plan);
}

function renderStats(now, was) {
  $('#plan-label').textContent = PLAN_LABELS[state.mode] + (state.mode === 'auto' && lastRunMs !== null ? ` in ${lastRunMs} ms` : '');
  const items = [
    ['Total travel', now.travelMin, was.travelMin, (v) => `${v.toFixed(1)} min`, -1],
    ['Total distance', now.distKm, was.distKm, (v) => `${v.toFixed(1)} km`, -1],
    ['Jobs done', now.jobsDone, was.jobsDone, String, 1],
    ['Jobs late', now.jobsLate, was.jobsLate, String, -1],
    ['Jobs unassigned', now.unassigned, was.unassigned, String, -1],
    ['Rule breaks', now.ruleBreaks, was.ruleBreaks, String, -1],
  ];
  $('#stats').innerHTML = items.map(([label, n, w, f, dir]) => {
    const diff = Math.round((n - w) * 10) / 10;
    const cls = diff === 0 ? '' : (diff * dir > 0 ? 'better' : 'worse');
    return `<div class="stat"><div class="label">${label}</div><div class="now ${cls}" data-stat="${label}">${f(n)}</div><div class="was">Manual plan: ${f(w)}</div></div>`;
  }).join('');
}

function el(name, attrs = {}, parent) {
  const node = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function renderMap(plan) {
  const svg = $('#map');
  svg.textContent = '';
  const k = 200 / MAP.width;
  // Real map of the Harrogate area (OpenStreetMap), 20 x 14 km, matching the job grid.
  el('image', { class: 'basemap', href: 'harrogate-district.jpg', x: 0, y: 0, width: 200, height: 140, preserveAspectRatio: 'none' }, svg);
  const cr = el('text', { class: 'map-credit', x: 197, y: 138 }, svg); cr.textContent = '© OpenStreetMap contributors';
  for (const a of AREAS) {
    const t = el('text', { class: 'area-label', x: a.x * k, y: a.y * k - 14 }, svg);
    t.textContent = a.name;
  }
  el('line', { class: 'scale', x1: 4, y1: 136, x2: 24, y2: 136 }, svg);
  const st = el('text', { class: 'map-note', x: 4, y: 133 }, svg); st.textContent = '2 km';

  const byId = jobById();
  for (const tech of state.techs) {
    const ids = state.routes[tech.id];
    if (!ids.length) continue;
    const pts = [tech.depot, ...ids.map((id) => byId.get(id)), tech.depot].map((p) => `${(p.x * k).toFixed(1)},${(p.y * k).toFixed(1)}`);
    el('polyline', { class: `route c${techIndex(tech.id)}`, points: pts.join(' ') }, svg);
  }
  const depots = new Map();
  for (const t of state.techs) depots.set(`${t.depot.x},${t.depot.y}`, t);
  for (const t of depots.values()) {
    const r = el('rect', { class: 'depot', x: t.depot.x * k - 2.5, y: t.depot.y * k - 2.5, width: 5, height: 5 }, svg);
    el('title', {}, r).textContent = t.depotName;
  }
  const owner = new Map();
  const flagged = new Set();
  for (const tech of state.techs) {
    for (const v of plan.evals[tech.id].visits) {
      owner.set(v.jobId, tech.id);
      if (v.flags.length) flagged.add(v.jobId);
    }
  }
  for (const job of state.jobs) {
    const tid = owner.get(job.id);
    const cls = ['pin', tid ? `assigned c${techIndex(tid)}` : 'unassigned', flagged.has(job.id) ? 'bad' : '', job.id === selectedId ? 'selected' : ''].join(' ');
    const c = el('circle', { class: cls, cx: job.x * k, cy: job.y * k, r: job.id === selectedId ? 3 : 2.2, tabindex: 0, 'data-job': job.id, role: 'button', 'aria-label': `${job.id} ${job.customer}` }, svg);
    el('title', {}, c).textContent = `${job.id} ${job.customer} (${job.skill})${tid ? '' : ', unassigned'}`;
    if (job.id === selectedId) {
      const lbl = el('text', { class: 'pin-label', x: job.x * k + 4, y: job.y * k + 1.2 }, svg);
      lbl.textContent = job.id;
    }
  }
  $('#legend').innerHTML = state.techs.map((t, i) => `<li class="c${i + 1}"><i></i>${esc(t.name)}</li>`).join('') +
    '<li class="muted">Hollow pin: unassigned. Square: depot.</li>';
}

function timeRange(plan) {
  let lo = Math.min(...state.techs.map((t) => t.start), 480);
  let hi = Math.max(...state.techs.map((t) => t.end), 1020);
  for (const ev of Object.values(plan.evals)) hi = Math.max(hi, ev.backAt);
  lo = Math.floor(lo / 60) * 60;
  hi = Math.ceil(hi / 60) * 60;
  return [lo, hi];
}

function renderTimeline(plan) {
  const [lo, hi] = timeRange(plan);
  const span = hi - lo;
  const pct = (m) => `${(((m - lo) / span) * 100).toFixed(3)}%`;
  const wid = (a, b) => `${(((b - a) / span) * 100).toFixed(3)}%`;
  const hours = [];
  for (let m = lo; m <= hi; m += 60) hours.push(m);
  const grid = hours.map((m) => `<div class="tl-hour" style="left:${pct(m)}"></div>`).join('');
  let html = `<div class="tl-row head"><div class="tl-name"></div><div class="tl-track">${hours.slice(0, -1).map((m) => `<span class="tl-hour-label" style="left:${pct(m)}">${formatTime(m)}</span>`).join('')}</div></div>`;
  const byId = jobById();
  for (const tech of state.techs) {
    const ev = plan.evals[tech.id];
    const ci = techIndex(tech.id);
    let blocks = `<div class="tl-off" style="left:0;width:${wid(lo, tech.start)}"></div><div class="tl-off" style="left:${pct(tech.end)};right:0"></div>${grid}`;
    blocks += `<div class="tl-lunch" style="left:${pct(tech.lunchStart)};width:${wid(tech.lunchStart, tech.lunchEnd)}" title="Lunch ${formatTime(tech.lunchStart)} to ${formatTime(tech.lunchEnd)}"></div>`;
    for (const v of ev.visits) {
      const job = byId.get(v.jobId);
      if (v.travelMin > 0.5) blocks += `<div class="tl-travel" style="left:${pct(v.depart)};width:${wid(v.depart, v.arrive)}" title="Travel ${Math.round(v.travelMin)} min"></div>`;
      const bad = v.flags.length > 0;
      const tip = `${v.jobId} ${job.customer}. ${job.skill}, ${job.duration} min. Window ${formatTime(job.windowStart)} to ${formatTime(job.windowEnd)}. Arrive ${formatTime(v.arrive)}, start ${formatTime(v.start)}, finish ${formatTime(v.finish)}.${bad ? ' Breaks rule: ' + v.flags.map((f) => FLAG_TEXT[f]).join(', ') + '.' : ''}`;
      blocks += `<button type="button" class="tl-job c${ci}${bad ? ' bad' : ''}${v.jobId === selectedId ? ' selected' : ''}" draggable="true" data-job="${v.jobId}" style="left:${pct(v.start)};width:${wid(v.start, v.finish)}" title="${esc(tip)}" aria-label="${esc(tip)}">${v.jobId.replace(/^J0*/, '')}</button>`;
    }
    if (ev.visits.length && ev.returnTravelMin > 0.5) {
      blocks += `<div class="tl-travel return${ev.returnLate ? ' bad' : ''}" style="left:${pct(ev.returnDepart)};width:${wid(ev.returnDepart, ev.backAt)}" title="Back to depot at ${formatTime(ev.backAt)}"></div>`;
    }
    html += `<div class="tl-row c${ci}" data-tech="${tech.id}"><div class="tl-name"><strong>${esc(tech.name)}</strong><span>${formatTime(tech.start)} to ${formatTime(tech.end)}</span><span>${ev.visits.length} jobs, ${Math.round(ev.travelMin)} min travel</span></div><div class="tl-track" data-lo="${lo}" data-span="${span}">${blocks}</div></div>`;
  }
  $('#timeline').innerHTML = html;
}

function renderUnassigned(plan) {
  const byId = jobById();
  const list = $('#unassigned');
  if (!plan.unassigned.length) { list.innerHTML = '<li class="empty">None. Every job has a technician.</li>'; return; }
  list.innerHTML = plan.unassigned.map((id) => {
    const job = byId.get(id);
    const reason = explainUnassigned(job, state.techs, state.routes, state.jobs, undefined, { deep: plan.unassigned.length <= 30 }).text;
    return `<li draggable="true" data-job="${id}"><button type="button" class="linklike" data-select="${id}">${id} ${esc(job.customer)}</button> <span class="muted small">${job.skill}, ${job.duration} min</span><span class="reason">${esc(reason)}</span></li>`;
  }).join('');
}

function renderIssues(plan) {
  const items = [];
  const byId = jobById();
  for (const tech of state.techs) {
    const ev = plan.evals[tech.id];
    for (const v of ev.visits) {
      for (const f of v.flags) {
        let detail = '';
        if (f === 'late') detail = ` (finishes ${formatTime(v.finish)}, window closes ${formatTime(byId.get(v.jobId).windowEnd)})`;
        if (f === 'overtime') detail = ` (finishes ${formatTime(v.finish)}, hours end ${formatTime(tech.end)})`;
        if (f === 'skill') detail = ` (needs ${byId.get(v.jobId).skill})`;
        items.push(`<li><button type="button" class="linklike" data-select="${v.jobId}">${v.jobId}</button> with ${esc(tech.name)}: <span class="bad-text">${FLAG_TEXT[f]}</span>${detail}</li>`);
      }
    }
    if (ev.returnLate) items.push(`<li>${esc(tech.name)}: <span class="bad-text">back at depot ${formatTime(ev.backAt)}, after hours end ${formatTime(tech.end)}</span></li>`);
  }
  $('#issues').innerHTML = items.length ? items.join('') : '<li class="empty">None. Every route keeps to skills, windows, hours and lunch.</li>';
}

function findVisit(plan, id) {
  for (const tech of state.techs) {
    const v = plan.evals[tech.id].visits.find((x) => x.jobId === id);
    if (v) return { tech, v };
  }
  return null;
}

function renderSelected(plan) {
  const box = $('#selected');
  if (!selectedId) { box.innerHTML = '<p class="muted">Select a job on the timeline, map or lists to move, edit or remove it.</p>'; return; }
  const job = jobById().get(selectedId);
  const at = findVisit(plan, selectedId);
  const route = at ? state.routes[at.tech.id] : null;
  const idx = route ? route.indexOf(selectedId) : -1;
  const status = at
    ? `${esc(at.tech.name)}, visit ${idx + 1} of ${route.length}. Start ${formatTime(at.v.start)}, finish ${formatTime(at.v.finish)}.` +
      (at.v.flags.length ? ` <span class="bad-text">Breaks rule: ${at.v.flags.map((f) => FLAG_TEXT[f]).join(', ')}.</span>` : '')
    : `Unassigned. ${esc(explainUnassigned(job, state.techs, state.routes, state.jobs).text)}`;
  const options = [`<option value="">Unassigned</option>`, ...state.techs.map((t) =>
    `<option value="${t.id}"${at && at.tech.id === t.id ? ' selected' : ''}>${esc(t.name)}${t.skills.includes(job.skill) ? '' : ' (no skill)'}</option>`)].join('');
  box.innerHTML = `<dl>
    <dt>Job</dt><dd>${job.id} ${esc(job.customer)}</dd>
    <dt>Area</dt><dd>${esc(job.area)} (${job.x}, ${job.y} km)</dd>
    <dt>Work</dt><dd>${job.skill}, ${job.duration} min, ${PRIORITIES[job.priority]} priority</dd>
    <dt>Window</dt><dd>${formatTime(job.windowStart)} to ${formatTime(job.windowEnd)}</dd>
    <dt>Plan</dt><dd>${status}</dd></dl>
    <div class="control-row"><label for="move-tech">Assign to</label><select id="move-tech">${options}</select>
      <button type="button" class="btn small" id="btn-move">Move</button></div>
    <div class="control-row">
      <button type="button" class="btn small" id="btn-earlier"${idx > 0 ? '' : ' disabled'}>Visit earlier</button>
      <button type="button" class="btn small" id="btn-later"${route && idx < route.length - 1 ? '' : ' disabled'}>Visit later</button>
      <button type="button" class="btn small" id="btn-edit">Edit</button>
      <button type="button" class="btn small" id="btn-remove">Remove</button>
      <button type="button" class="btn small subtle" id="btn-clear">Clear selection</button>
    </div>`;
  $('#btn-move').onclick = () => {
    const tid = $('#move-tech').value || null;
    const cur = at ? at.tech.id : null;
    applyMove(selectedId, tid, tid ? (tid === cur ? idx : state.routes[tid].length) : 0);
  };
  $('#btn-earlier').onclick = () => applyMove(selectedId, at.tech.id, idx - 1);
  $('#btn-later').onclick = () => applyMove(selectedId, at.tech.id, idx + 1);
  $('#btn-edit').onclick = () => openForm(job);
  $('#btn-remove').onclick = () => removeJob(job.id);
  $('#btn-clear').onclick = () => { const id = selectedId; selectedId = null; render(`#timeline [data-job="${id}"]`); };
}

function renderJobs(plan) {
  const owner = new Map();
  for (const tech of state.techs) for (const v of plan.evals[tech.id].visits) owner.set(v.jobId, { tech, v });
  $('#job-count').textContent = `${state.jobs.length} jobs`;
  const rows = state.jobs.map((j) => {
    const o = owner.get(j.id);
    return `<tr data-job="${j.id}"${j.id === selectedId ? ' class="selected"' : ''}>
      <td><button type="button" class="linklike" data-select="${j.id}">${j.id}</button></td><td>${esc(j.customer)}</td><td>${esc(j.area)}</td>
      <td>${j.skill}</td><td class="num">${j.duration}</td><td class="num">${formatTime(j.windowStart)} to ${formatTime(j.windowEnd)}</td>
      <td>${PRIORITIES[j.priority]}</td><td>${o ? esc(o.tech.name) + ' ' + formatTime(o.v.start) : '<span class="muted">Unassigned</span>'}${o && o.v.flags.length ? ' <span class="bad-text">!</span>' : ''}</td>
      <td><button type="button" class="btn small" data-edit="${j.id}">Edit</button> <button type="button" class="btn small" data-remove="${j.id}">Remove</button></td></tr>`;
  }).join('');
  $('#jobs-table').innerHTML = `<thead><tr><th>Id</th><th>Customer</th><th>Area</th><th>Skill</th><th>Min</th><th>Window</th><th>Priority</th><th>Planned</th><th><span class="muted">Actions</span></th></tr></thead><tbody>${rows}</tbody>`;
}

function applyMove(jobId, techId, position) {
  state.routes = moveJob(state.routes, jobId, techId, position);
  selectedId = jobId;
  const plan = evaluatePlan(state.jobs, state.techs, state.routes);
  const at = findVisit(plan, jobId);
  const msg = !techId ? `${jobId} is now unassigned.`
    : at.v.flags.length ? `${jobId} moved to ${at.tech.name}. This breaks a rule: ${at.v.flags.map((f) => FLAG_TEXT[f]).join(', ')}.`
      : `${jobId} moved to ${at.tech.name}, visit ${at.v.order}.`;
  commit('edited', msg);
}

function removeJob(id) {
  if (!window.confirm(`Remove job ${id}? This cannot be undone except by resetting to the sample day.`)) return;
  const i = state.jobs.findIndex((j) => j.id === id);
  state.jobs = state.jobs.filter((j) => j.id !== id);
  state.routes = moveJob(state.routes, id, null);
  if (selectedId === id) selectedId = null;
  const neighbour = state.jobs[Math.min(i, state.jobs.length - 1)];
  commit('edited', `Removed ${id}.`, neighbour ? `#jobs-table [data-remove="${neighbour.id}"]` : '#btn-add');
}

let editingId = null;
function openForm(job) {
  const form = $('#job-form');
  editingId = job ? job.id : null;
  $('#dialog-title').textContent = job ? `Edit ${job.id}` : 'Add job';
  const nextId = () => {
    let n = state.jobs.length + 1;
    while (state.jobs.some((j) => j.id === `J${String(n).padStart(3, '0')}`)) n++;
    return `J${String(n).padStart(3, '0')}`;
  };
  const j = job || { id: nextId(), customer: '', x: 10, y: 7, duration: 45, windowStart: 480, windowEnd: 1020, skill: SKILLS[0], priority: 2 };
  form.id.value = j.id;
  form.id.readOnly = !!job;
  form.customer.value = j.customer;
  form.x.value = j.x;
  form.y.value = j.y;
  form.duration.value = j.duration;
  form.windowStart.value = formatTime(j.windowStart);
  form.windowEnd.value = formatTime(j.windowEnd);
  form.skill.value = j.skill;
  form.priority.value = String(j.priority);
  $('#form-errors').textContent = '';
  $('#job-dialog').showModal();
  form.customer.focus();
}

function saveForm(ev) {
  ev.preventDefault();
  const f = $('#job-form');
  const raw = { id: f.id.value, customer: f.customer.value, x: f.x.value, y: f.y.value, duration: f.duration.value,
    windowStart: f.windowStart.value, windowEnd: f.windowEnd.value, skill: f.skill.value, priority: f.priority.value };
  const res = validateJob(raw);
  const errors = res.errors ? [...res.errors] : [];
  if (!editingId && state.jobs.some((j) => j.id === raw.id.trim())) errors.push(`id ${raw.id.trim()} is already used`);
  if (errors.length) { $('#form-errors').textContent = `Please fix: ${errors.join('; ')}.`; return; }
  if (editingId) {
    state.jobs = state.jobs.map((j) => (j.id === editingId ? res.job : j));
    $('#job-dialog').close();
    selectedId = res.job.id;
    commit('edited', `Saved ${res.job.id}. Its place in the plan is kept; check the timeline for any rule it now breaks.`, `#timeline [data-job="${res.job.id}"]`);
  } else {
    state.jobs = [...state.jobs, res.job];
    $('#job-dialog').close();
    selectedId = res.job.id;
    commit('edited', `Added ${res.job.id} as unassigned. Run Auto-schedule or move it onto a technician.`, `#unassigned [data-select="${res.job.id}"]`);
  }
}

function download(name, text) {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function importFile(file) {
  const reader = new FileReader();
  reader.onload = () => {
    const { jobs, errors } = importJobsCsv(String(reader.result));
    if (!jobs.length) {
      setStatus(`No jobs imported. ${errors.map((e) => `Line ${e.line}: ${e.message}`).join(' ')}`, true);
      return;
    }
    state.jobs = jobs;
    state.routes = manualPlan(jobs, state.techs);
    selectedId = null;
    commit('manual', '');
    const skipped = errors.length ? ` ${errors.length} row(s) not imported. ${errors.map((e) => `Line ${e.line}: ${e.message}`).join(' ')}` : '';
    setStatus(`Imported ${jobs.length} jobs from ${file.name} and made the manual plan.${skipped}`, errors.length > 0);
  };
  reader.onerror = () => setStatus('The file could not be read.', true);
  reader.readAsText(file);
}

// Drag and drop on the timeline and the unassigned list.
let dragId = null;
function dropIndex(track, clientX, techId) {
  const rect = track.getBoundingClientRect();
  const lo = Number(track.dataset.lo);
  const span = Number(track.dataset.span);
  const minute = lo + ((clientX - rect.left) / rect.width) * span;
  const plan = evaluatePlan(state.jobs, state.techs, state.routes);
  return plan.evals[techId].visits.filter((v) => v.jobId !== dragId && (v.start + v.finish) / 2 < minute).length;
}

function bindControls() {
  $('#btn-hand').onclick = () => {
    state.routes = manualPlan(state.jobs, state.techs);
    commit('manual', 'Showing the manual plan: each job to the nearest technician with the skill, visited in time-window order.');
  };
  $('#btn-auto').onclick = () => {
    const t0 = performance.now();
    const res = autoSchedule(state.jobs, state.techs);
    lastRunMs = Math.max(1, Math.round(performance.now() - t0));
    state.routes = res.routes;
    const counts = { skill: 0, window: 0, other: 0 };
    for (const r of Object.values(res.reasons)) counts[r.code === 'skill' || r.code === 'window' ? r.code : 'other']++;
    const parts = [];
    if (counts.skill) parts.push(`${counts.skill} ${counts.skill === 1 ? 'needs' : 'need'} a skill no technician has`);
    if (counts.window) parts.push(`${counts.window} ${counts.window === 1 ? 'has' : 'have'} a window that cannot be met`);
    if (counts.other) parts.push(`${counts.other} did not fit into the ${state.techs.length} technicians' working hours`);
    const why = res.unassigned.length ? ` ${res.unassigned.length} could not be placed: ${parts.join(', ')}.` : '';
    commit('auto', `Auto-schedule placed ${state.jobs.length - res.unassigned.length} of ${state.jobs.length} jobs in ${lastRunMs} ms.${why}`);
  };
  $('#btn-add').onclick = () => openForm(null);
  $('#btn-import').onclick = () => $('#file-input').click();
  $('#file-input').onchange = (e) => { const f = e.target.files[0]; if (f) importFile(f); e.target.value = ''; };
  $('#btn-export').onclick = () => {
    const plan = evaluatePlan(state.jobs, state.techs, state.routes);
    download('schedule.csv', exportScheduleCsv(plan, state.techs, state.jobs));
    setStatus('Exported schedule.csv (one row per visit, then unassigned jobs).');
  };
  $('#btn-export-jobs').onclick = () => {
    download('jobs.csv', exportJobsCsv(state.jobs));
    setStatus('Exported jobs.csv. This file can be imported again.');
  };
  $('#btn-reset').onclick = () => {
    if (!window.confirm('Reset to the sample day? Your jobs and changes will be replaced.')) return;
    clearState();
    state = freshState();
    selectedId = null;
    commit(null, 'Reset to the sample day.', '#btn-reset');
  };
  $('#btn-cancel').onclick = () => $('#job-dialog').close();
  $('#job-dialog').addEventListener('close', () => {
    if (document.activeElement === document.body) restoreFocus(selectedId ? `#timeline [data-job="${selectedId}"]` : '#btn-add');
  });
  $('#job-form').addEventListener('submit', saveForm);

  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-select], .tl-job, #map .pin, [data-edit], [data-remove]');
    if (!t) return;
    if (t.dataset.edit) { openForm(state.jobs.find((j) => j.id === t.dataset.edit)); return; }
    if (t.dataset.remove) { removeJob(t.dataset.remove); return; }
    selectedId = t.dataset.select || t.dataset.job;
    render();
    if (window.matchMedia('(max-width: 900px)').matches) $('#selected-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  $('#map').addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.dataset.job) { e.preventDefault(); selectedId = e.target.dataset.job; render(); }
  });

  document.addEventListener('dragstart', (e) => {
    const t = e.target.closest('[draggable="true"][data-job]');
    if (!t) return;
    dragId = t.dataset.job;
    e.dataTransfer.setData('text/plain', dragId);
    e.dataTransfer.effectAllowed = 'move';
    t.classList.add('dragging');
  });
  document.addEventListener('dragend', () => {
    dragId = null;
    document.querySelectorAll('.drop-target, .dragging').forEach((n) => n.classList.remove('drop-target', 'dragging'));
  });
  document.addEventListener('dragover', (e) => {
    const zone = e.target.closest('.tl-row[data-tech], [data-drop="unassigned"]');
    if (!zone || !dragId) return;
    e.preventDefault();
    document.querySelectorAll('.drop-target').forEach((n) => n !== zone && n.classList.remove('drop-target'));
    zone.classList.add('drop-target');
  });
  document.addEventListener('drop', (e) => {
    const zone = e.target.closest('.tl-row[data-tech], [data-drop="unassigned"]');
    if (!zone || !dragId) return;
    e.preventDefault();
    const id = dragId;
    if (zone.dataset.drop === 'unassigned') { applyMove(id, null); return; }
    const techId = zone.dataset.tech;
    applyMove(id, techId, dropIndex(zone.querySelector('.tl-track'), e.clientX, techId));
  });
}

init();
