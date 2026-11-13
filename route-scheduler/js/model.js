// Data model, sample day generator and shared validation. No DOM access.

export const MAP = { width: 20, height: 14 }; // kilometres
export const PARAMS = { roadFactor: 1.3, speedKmh: 30 };

export const SKILLS = [
  'Fire alarm',
  'Intruder alarm',
  'CCTV',
  'Extinguishers',
  'Emergency lighting',
  'Access control',
];

export const PRIORITIES = { 1: 'High', 2: 'Normal', 3: 'Low' };

export const AREAS = [
  { name: 'Birstwith', x: 4, y: 3.6 },
  { name: 'Nidd', x: 10, y: 3 },
  { name: 'Farnham', x: 16, y: 3.8 },
  { name: 'Beckwithshaw', x: 4, y: 10.6 },
  { name: 'Pannal', x: 10.4, y: 10.4 },
  { name: 'Follifoot', x: 16, y: 10.6 },
];

export function nearestArea(x, y) {
  let best = AREAS[0];
  let bestD = Infinity;
  for (const a of AREAS) {
    const d = Math.hypot(a.x - x, a.y - y);
    if (d < bestD) { bestD = d; best = a; }
  }
  return best.name;
}

// Small deterministic random number generator.
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function parseTime(text) {
  const m = /^\s*(\d{1,2}):(\d{2})\s*$/.exec(String(text ?? ''));
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return null;
  return h * 60 + min;
}

export function formatTime(minutes) {
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export const SAMPLE_TECHS = [
  { id: 'T1', name: 'Asha', depot: { x: 10.6, y: 7.9 }, depotName: 'Main depot', start: 480, end: 990, lunchStart: 720, lunchEnd: 750, skills: ['Fire alarm', 'Emergency lighting', 'Extinguishers'] },
  { id: 'T2', name: 'Ben', depot: { x: 10.6, y: 7.9 }, depotName: 'Main depot', start: 480, end: 990, lunchStart: 750, lunchEnd: 780, skills: ['Intruder alarm', 'CCTV'] },
  { id: 'T3', name: 'Carys', depot: { x: 2.6, y: 6.2 }, depotName: 'West yard', start: 510, end: 1020, lunchStart: 750, lunchEnd: 780, skills: ['Fire alarm', 'Intruder alarm'] },
  { id: 'T4', name: 'Dev', depot: { x: 17.6, y: 7.4 }, depotName: 'East yard', start: 480, end: 990, lunchStart: 780, lunchEnd: 810, skills: ['CCTV', 'Intruder alarm', 'Emergency lighting'] },
  { id: 'T5', name: 'Elin', depot: { x: 10.6, y: 7.9 }, depotName: 'Main depot', start: 450, end: 960, lunchStart: 720, lunchEnd: 750, skills: ['Extinguishers', 'Fire alarm', 'Emergency lighting'] },
  { id: 'T6', name: 'Femi', depot: { x: 11.2, y: 12.8 }, depotName: 'South yard', start: 540, end: 1050, lunchStart: 780, lunchEnd: 810, skills: ['Fire alarm', 'CCTV', 'Extinguishers'] },
];

const SITE_TYPES = [
  'Dental Practice', 'Primary School', 'Care Home', 'Bakery', 'Library', 'Garage', 'Hotel',
  'Medical Centre', 'Warehouse', 'Community Hall', 'Pharmacy', 'Office Block', 'Sports Centre',
  'Vet Clinic', 'Print Works', 'Cafe', 'Leisure Centre', 'Builders Yard', 'Nursery', 'Chapel Hall',
];

function pick(rand, list) { return list[Math.floor(rand() * list.length)]; }

function weighted(rand, pairs) {
  const total = pairs.reduce((s, p) => s + p[1], 0);
  let r = rand() * total;
  for (const [v, w] of pairs) { r -= w; if (r < 0) return v; }
  return pairs[pairs.length - 1][0];
}

const round1 = (v) => Math.round(v * 10) / 10;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export function sampleDay(seed = 20261112) {
  const rand = mulberry32(seed);
  const jobs = [];
  const seen = new Set();
  for (let i = 1; i <= 38; i++) {
    const area = pick(rand, AREAS);
    const x = round1(clamp(area.x + (rand() - 0.5) * 5, 0.5, MAP.width - 0.5));
    const y = round1(clamp(area.y + (rand() - 0.5) * 4, 0.5, MAP.height - 0.5));
    let customer = `${area.name} ${pick(rand, SITE_TYPES)}`;
    if (seen.has(customer)) customer += ' (annexe)';
    seen.add(customer);
    const skill = weighted(rand, [['Fire alarm', 34], ['Intruder alarm', 20], ['CCTV', 16], ['Extinguishers', 18], ['Emergency lighting', 12]]);
    const duration = pick(rand, [20, 30, 30, 45, 45, 60, 60, 90]);
    const kind = weighted(rand, [['day', 50], ['am', 20], ['pm', 20], ['slot', 10]]);
    let windowStart = 480;
    let windowEnd = 1020;
    if (kind === 'am') { windowEnd = 750; }
    if (kind === 'pm') { windowStart = 750; }
    if (kind === 'slot') { windowStart = 540 + 30 * Math.floor(rand() * 10); windowEnd = windowStart + 120; }
    const priority = weighted(rand, [[1, 15], [2, 60], [3, 25]]);
    jobs.push({ id: `J${String(i).padStart(3, '0')}`, customer, area: nearestArea(x, y), x, y, duration, windowStart, windowEnd, skill, priority });
  }
  // Two jobs that show the plain-words reasons for unassigned work.
  jobs.push({ id: 'J039', customer: 'Farnham Data Centre', area: 'Farnham', x: 17.2, y: 2.4, duration: 60, windowStart: 540, windowEnd: 960, skill: 'Access control', priority: 2 });
  jobs.push({ id: 'J040', customer: 'Birstwith Boat Store', area: 'Birstwith', x: 1.2, y: 1.4, duration: 60, windowStart: 480, windowEnd: 540, skill: 'Intruder alarm', priority: 2 });
  return { jobs, techs: SAMPLE_TECHS.map((t) => ({ ...t, depot: { ...t.depot }, skills: [...t.skills] })) };
}

// Validates a raw job record (strings or numbers). Returns { job } or { errors }.
export function validateJob(raw) {
  const errors = [];
  const id = String(raw.id ?? '').trim();
  if (!id) errors.push('id is missing');
  else if (!/^[A-Za-z0-9_-]{1,20}$/.test(id)) errors.push('id may only use letters, digits, - and _ (max 20)');
  const customer = String(raw.customer ?? '').trim();
  if (!customer) errors.push('customer is missing');
  const x = Number(String(raw.x ?? '').trim() === '' ? NaN : raw.x);
  const y = Number(String(raw.y ?? '').trim() === '' ? NaN : raw.y);
  if (!Number.isFinite(x) || x < 0 || x > MAP.width) errors.push(`x_km must be a number from 0 to ${MAP.width}`);
  if (!Number.isFinite(y) || y < 0 || y > MAP.height) errors.push(`y_km must be a number from 0 to ${MAP.height}`);
  const duration = Number(String(raw.duration ?? '').trim() === '' ? NaN : raw.duration);
  if (!Number.isInteger(duration) || duration < 5 || duration > 480) errors.push('duration_min must be a whole number from 5 to 480');
  const ws = typeof raw.windowStart === 'number' ? raw.windowStart : parseTime(raw.windowStart);
  const we = typeof raw.windowEnd === 'number' ? raw.windowEnd : parseTime(raw.windowEnd);
  if (ws === null) errors.push('window_start must be a time like 08:30');
  if (we === null) errors.push('window_end must be a time like 17:00');
  if (ws !== null && we !== null && we <= ws) errors.push('window_end must be after window_start');
  else if (ws !== null && we !== null && Number.isInteger(duration) && we - ws < duration) {
    errors.push(`the window (${we - ws} min) is shorter than the job (${duration} min), so it could never be done`);
  }
  const skill = SKILLS.find((s) => s.toLowerCase() === String(raw.skill ?? '').trim().toLowerCase());
  if (!skill) errors.push(`skill must be one of: ${SKILLS.join(', ')}`);
  const pText = String(raw.priority ?? '').trim().toLowerCase();
  const priority = { '1': 1, '2': 2, '3': 3, high: 1, normal: 2, low: 3 }[pText];
  if (!priority) errors.push('priority must be 1, 2, 3 or High, Normal, Low');
  if (errors.length) return { errors };
  const areaText = String(raw.area ?? '').trim();
  return { job: { id, customer, area: areaText || nearestArea(x, y), x, y, duration, windowStart: ws, windowEnd: we, skill, priority } };
}

// Checks data read back from browser storage. Returns clean state or null.
export function validateState(data) {
  if (!data || typeof data !== 'object') return null;
  if (!Array.isArray(data.jobs) || !Array.isArray(data.techs) || !data.techs.length) return null;
  if (!data.routes || typeof data.routes !== 'object' || Array.isArray(data.routes)) return null;
  const jobs = [];
  const ids = new Set();
  for (const raw of data.jobs) {
    if (!raw || typeof raw !== 'object') return null;
    const res = validateJob(raw);
    if (res.errors || ids.has(res.job.id.toLowerCase())) return null;
    ids.add(res.job.id.toLowerCase());
    jobs.push(res.job);
  }
  const num = Number.isFinite;
  for (const t of data.techs) {
    if (!t || typeof t.id !== 'string' || typeof t.name !== 'string' || !t.depot || !num(t.depot.x) || !num(t.depot.y)) return null;
    if (![t.start, t.end, t.lunchStart, t.lunchEnd].every(num) || t.start >= t.end || t.lunchStart >= t.lunchEnd) return null;
    if (!Array.isArray(t.skills) || !t.skills.every((k) => SKILLS.includes(k))) return null;
  }
  for (const r of Object.values(data.routes)) {
    if (!Array.isArray(r) || !r.every((id) => typeof id === 'string')) return null;
  }
  const mode = ['manual', 'auto', 'edited'].includes(data.mode) ? data.mode : 'manual';
  return { jobs, techs: data.techs, routes: data.routes, mode };
}
