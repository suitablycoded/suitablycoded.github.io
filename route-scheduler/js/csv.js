// CSV reading and writing. No DOM access.
import { validateJob, formatTime } from './model.js';

export const JOB_COLUMNS = ['id', 'customer', 'area', 'x_km', 'y_km', 'duration_min', 'window_start', 'window_end', 'skill', 'priority'];
export const SCHEDULE_COLUMNS = ['technician', 'order', 'job', 'customer', 'arrive', 'start', 'finish', 'travel_min', 'notes'];

// Returns records as { line, fields } where line is the 1-based line the record starts on.
export function parseCsv(text) {
  const src = String(text).replace(/^﻿/, '');
  const records = [];
  let fields = [];
  let field = '';
  let inQuotes = false;
  let line = 1;
  let recordLine = 1;
  let i = 0;
  const endRecord = () => {
    fields.push(field);
    if (!(fields.length === 1 && fields[0].trim() === '')) records.push({ line: recordLine, fields });
    fields = [];
    field = '';
  };
  while (i < src.length) {
    const c = src[i];
    if (inQuotes) {
      if (c === '"') {
        if (src[i + 1] === '"') { field += '"'; i += 2; continue; }
        inQuotes = false; i++; continue;
      }
      if (c === '\n') line++;
      field += c; i++; continue;
    }
    if (c === '"') { inQuotes = true; i++; continue; }
    if (c === ',') { fields.push(field); field = ''; i++; continue; }
    if (c === '\r') { i++; continue; }
    if (c === '\n') { endRecord(); line++; recordLine = line; i++; continue; }
    field += c; i++;
  }
  if (inQuotes) records.unterminatedLine = recordLine;
  if (field !== '' || fields.length) endRecord();
  return records;
}

// Text that a spreadsheet would run as a formula gets a leading apostrophe.
function cell(v) {
  let s = String(v ?? '');
  if (/^[=+\-@\t\r]/.test(s) && !/^-?\d+(\.\d+)?$/.test(s)) s = `'${s}`;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows) {
  return rows.map((r) => r.map(cell).join(',')).join('\r\n') + '\r\n';
}

export function importJobsCsv(text) {
  const records = parseCsv(text);
  const errors = [];
  if (!records.length) return { jobs: [], errors: [{ line: 1, message: 'The file is empty.' }] };
  const header = records[0].fields.map((h) => h.trim().toLowerCase());
  if (header.length === 1 && header[0].includes(';')) {
    return { jobs: [], errors: [{ line: records[0].line, message: 'The columns are separated by semicolons. Save the file as comma-separated CSV and try again.' }] };
  }
  if (header.length === 1 && header[0].includes('\t')) {
    return { jobs: [], errors: [{ line: records[0].line, message: 'The columns are separated by tabs. Save the file as comma-separated CSV and try again.' }] };
  }
  const missing = JOB_COLUMNS.filter((c) => c !== 'area' && !header.includes(c));
  if (missing.length) {
    return { jobs: [], errors: [{ line: records[0].line, message: `Header is missing column(s): ${missing.join(', ')}.` }] };
  }
  const col = (name) => header.indexOf(name);
  const jobs = [];
  const ids = new Set();
  const cut = records.unterminatedLine;
  if (cut) {
    errors.push({ line: cut, message: 'A quoted value starting on this line is never closed, so the rest of the file could not be read. Rows from this line on were not imported.' });
  }
  for (const rec of records.slice(1)) {
    if (cut && rec.line >= cut) break;
    const get = (name) => {
      const v = col(name) >= 0 ? rec.fields[col(name)] ?? '' : '';
      return /^'[=+\-@]/.test(v) ? v.slice(1) : v;
    };
    if (rec.fields.length !== header.length) {
      errors.push({ line: rec.line, message: `Expected ${header.length} values but found ${rec.fields.length}.` });
      continue;
    }
    const res = validateJob({
      id: get('id'), customer: get('customer'), area: get('area'), x: get('x_km'), y: get('y_km'),
      duration: get('duration_min'), windowStart: get('window_start'), windowEnd: get('window_end'),
      skill: get('skill'), priority: get('priority'),
    });
    if (res.errors) { errors.push({ line: rec.line, message: res.errors.join('; ') + '.' }); continue; }
    if (ids.has(res.job.id.toLowerCase())) { errors.push({ line: rec.line, message: `Job id ${res.job.id} appears more than once (ids are matched ignoring capitals).` }); continue; }
    ids.add(res.job.id.toLowerCase());
    jobs.push(res.job);
  }
  if (records.length === 1 && !errors.length) errors.push({ line: records[0].line, message: 'The file has a header row but no jobs.' });
  return { jobs, errors };
}

export function exportJobsCsv(jobs) {
  return toCsv([JOB_COLUMNS, ...jobs.map((j) => [
    j.id, j.customer, j.area, j.x, j.y, j.duration, formatTime(j.windowStart), formatTime(j.windowEnd), j.skill, j.priority,
  ])]);
}

const NOTE_TEXT = { skill: 'missing skill', late: 'late for window', overtime: 'after working hours' };

// One row per visit, plus one row per unassigned job (technician left blank).
export function exportScheduleCsv(plan, techs, jobs) {
  const byId = new Map(jobs.map((j) => [j.id, j]));
  const rows = [SCHEDULE_COLUMNS];
  for (const tech of techs) {
    for (const v of plan.evals[tech.id].visits) {
      rows.push([tech.name, v.order, v.jobId, byId.get(v.jobId).customer, formatTime(v.arrive), formatTime(v.start),
        formatTime(v.finish), Math.round(v.travelMin), v.flags.map((f) => NOTE_TEXT[f]).join('; ')]);
    }
  }
  for (const id of plan.unassigned) rows.push(['', '', id, byId.get(id).customer, '', '', '', '', 'unassigned']);
  return toCsv(rows);
}
