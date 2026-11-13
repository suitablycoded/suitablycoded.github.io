import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { sampleDay } from '../js/model.js';
import { parseCsv, importJobsCsv, exportJobsCsv, exportScheduleCsv, SCHEDULE_COLUMNS } from '../js/csv.js';
import { autoSchedule, evaluatePlan } from '../js/scheduler.js';

const HEADER = 'id,customer,area,x_km,y_km,duration_min,window_start,window_end,skill,priority';

test('parser handles quotes, commas, doubled quotes and CRLF', () => {
  const recs = parseCsv('a,b\r\n"x, y","say ""hi"""\r\n\r\nlast,1');
  assert.deepEqual(recs.map((r) => r.fields), [['a', 'b'], ['x, y', 'say "hi"'], ['last', '1']]);
  assert.deepEqual(recs.map((r) => r.line), [1, 2, 4]);
});

test('bad rows are reported by line number and good rows kept', () => {
  const text = [
    HEADER,
    'A1,Good Ltd,,5,5,30,08:00,12:00,CCTV,2',
    'A2,Bad time,,5,5,30,8am,12:00,CCTV,2',
    '',
    'A3,Off map,,55,5,30,08:00,12:00,CCTV,2',
    'A4,Unknown skill,,5,5,30,08:00,12:00,Plumbing,2',
    'A1,Duplicate,,5,5,30,08:00,12:00,CCTV,2',
    'A5,Too few,5,5',
    'A6,Backwards,,5,5,30,12:00,08:00,cctv,high',
  ].join('\n');
  const { jobs, errors } = importJobsCsv(text);
  assert.deepEqual(jobs.map((j) => j.id), ['A1']);
  assert.deepEqual(errors.map((e) => e.line), [3, 5, 6, 7, 8, 9]);
  assert.match(errors[0].message, /window_start/);
  assert.match(errors[1].message, /x_km/);
  assert.match(errors[2].message, /skill/);
  assert.match(errors[3].message, /more than once/);
  assert.match(errors[4].message, /Expected 10 values/);
  assert.match(errors[5].message, /after window_start/);
  assert.equal(jobs[0].area, 'Birstwith'); // filled from nearest area
});

test('missing header columns and empty files are reported', () => {
  assert.equal(importJobsCsv('').errors[0].line, 1);
  assert.match(importJobsCsv('id,customer\nA,B').errors[0].message, /missing column/);
});

test('job export then import gives the same jobs', () => {
  const { jobs } = sampleDay();
  jobs[0] = { ...jobs[0], customer: 'Quote "and", comma Ltd' };
  const back = importJobsCsv(exportJobsCsv(jobs));
  assert.deepEqual(back.errors, []);
  assert.deepEqual(back.jobs, jobs);
});

test('shipped sample CSV imports with no errors', () => {
  const text = readFileSync(new URL('../sample-jobs.csv', import.meta.url), 'utf8');
  const { jobs, errors } = importJobsCsv(text);
  assert.deepEqual(errors, []);
  assert.ok(jobs.length >= 10);
});

test('schedule export has one row per visit and reads back to the same plan', () => {
  const { jobs, techs } = sampleDay();
  const { routes } = autoSchedule(jobs, techs);
  const plan = evaluatePlan(jobs, techs, routes);
  const recs = parseCsv(exportScheduleCsv(plan, techs, jobs));
  assert.deepEqual(recs[0].fields, SCHEDULE_COLUMNS);
  const rows = recs.slice(1).map((r) => r.fields);
  const visitRows = rows.filter((r) => r[0] !== '');
  const total = Object.values(routes).flat().length;
  assert.equal(visitRows.length, total);
  assert.equal(rows.length - visitRows.length, plan.unassigned.length);
  // Rebuild routes from the file and compare.
  const nameToId = Object.fromEntries(techs.map((t) => [t.name, t.id]));
  const rebuilt = Object.fromEntries(techs.map((t) => [t.id, []]));
  for (const r of visitRows) rebuilt[nameToId[r[0]]][Number(r[1]) - 1] = r[2];
  assert.deepEqual(rebuilt, routes);
});

test('an unclosed quote is reported at its line and not counted as one bad row', () => {
  const text = [HEADER, 'A1,Good,,5,5,30,08:00,12:00,CCTV,2', 'A2,"oops,,5,5,30,08:00,12:00,CCTV,2',
    'A3,Good,,5,5,30,08:00,12:00,CCTV,2', 'A4,Good,,5,5,30,08:00,12:00,CCTV,2'].join('\n');
  const { jobs, errors } = importJobsCsv(text);
  assert.deepEqual(jobs.map((j) => j.id), ['A1']);
  assert.equal(errors.length, 1);
  assert.equal(errors[0].line, 3);
  assert.match(errors[0].message, /never closed/);
});

test('ids differing only in capitals are duplicates; semicolons and short windows are explained', () => {
  const dup = importJobsCsv([HEADER, 'A1,X,,5,5,30,08:00,12:00,CCTV,2', 'a1,Y,,5,5,30,08:00,12:00,CCTV,2'].join('\n'));
  assert.equal(dup.jobs.length, 1);
  assert.equal(dup.errors[0].line, 3);
  const semi = importJobsCsv(HEADER.replace(/,/g, ';') + '\nA1;X;;5;5;30;08:00;12:00;CCTV;2');
  assert.match(semi.errors[0].message, /semicolons/);
  const short = importJobsCsv([HEADER, 'A1,X,,5,5,60,08:00,08:30,CCTV,2'].join('\n'));
  assert.equal(short.errors[0].line, 2);
  assert.match(short.errors[0].message, /shorter than the job/);
});

test('text that a spreadsheet would run as a formula is made safe and still round trips', () => {
  const { jobs } = sampleDay();
  const risky = jobs.slice(0, 3).map((j, i) => ({ ...j, customer: ['=SUM(A1)', '+44 Shop', '@home'][i] }));
  const text = exportJobsCsv(risky);
  assert.ok(text.includes("'=SUM(A1)"));
  assert.ok(!/(^|,)=SUM/m.test(text));
  assert.deepEqual(importJobsCsv(text).jobs, risky);
  const plan = evaluatePlan(risky, sampleDay().techs, { T1: [], T2: [], T3: [], T4: [], T5: [], T6: [] });
  assert.ok(exportScheduleCsv(plan, sampleDay().techs, risky).includes("'=SUM(A1)"));
});

test('tab-separated and header-only files get a clear message', () => {
  assert.match(importJobsCsv(HEADER.replace(/,/g, '\t') + '\nA1\tX').errors[0].message, /tabs/);
  const only = importJobsCsv(HEADER + '\n');
  assert.equal(only.jobs.length, 0);
  assert.match(only.errors[0].message, /no jobs/);
});
