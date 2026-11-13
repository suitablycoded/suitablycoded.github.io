import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sampleDay, PARAMS, mulberry32 } from '../js/model.js';
import {
  travelMinutes, distanceKm, evaluateRoute, evaluatePlan, manualPlan, autoSchedule, improve,
  explainUnassigned, indexJobs, moveJob, emptyRoutes, insertionOnly, makeRoom, isBetter,
} from '../js/scheduler.js';

const day = sampleDay();
const auto = autoSchedule(day.jobs, day.techs);
const techById = new Map(day.techs.map((t) => [t.id, t]));
const jobById = indexJobs(day.jobs);

test('sample day is the same every time', () => {
  assert.deepEqual(sampleDay(), sampleDay());
  assert.equal(day.jobs.length, 40);
  assert.equal(day.techs.length, 6);
});

test('travel time is straight line x road factor at average speed', () => {
  const a = { x: 0, y: 0 };
  const b = { x: 3, y: 4 }; // 5 km straight line
  assert.equal(distanceKm(a, b, { roadFactor: 1.3, speedKmh: 30 }), 6.5);
  assert.equal(travelMinutes(a, b, { roadFactor: 1.3, speedKmh: 30 }), 13);
  assert.equal(travelMinutes(a, b, { roadFactor: 1, speedKmh: 60 }), 5);
});

test('auto-schedule finishes quickly for 40 jobs', () => {
  const t0 = performance.now();
  autoSchedule(day.jobs, day.techs);
  assert.ok(performance.now() - t0 < 2000);
});

test('no job is assigned twice and every job is either routed or unassigned', () => {
  const routed = Object.values(auto.routes).flat();
  assert.equal(new Set(routed).size, routed.length);
  assert.equal(routed.length + auto.unassigned.length, day.jobs.length);
  for (const id of auto.unassigned) assert.ok(!routed.includes(id));
});

test('skills are respected', () => {
  for (const [tid, ids] of Object.entries(auto.routes)) {
    for (const id of ids) assert.ok(techById.get(tid).skills.includes(jobById.get(id).skill), `${id} on ${tid}`);
  }
});

test('time windows, working hours and lunch are respected', () => {
  for (const tech of day.techs) {
    const ev = evaluateRoute(tech, auto.routes[tech.id], jobById);
    assert.ok(ev.feasible);
    assert.ok(ev.backAt <= tech.end + 1e-6);
    for (const v of ev.visits) {
      const job = jobById.get(v.jobId);
      assert.ok(v.start >= job.windowStart - 1e-6);
      assert.ok(v.finish <= job.windowEnd + 1e-6);
      assert.ok(v.depart >= tech.start - 1e-6);
      // Neither the travel leg nor the visit overlaps lunch.
      for (const [s, e] of [[v.depart, v.arrive], [v.start, v.finish]]) {
        assert.ok(e <= tech.lunchStart + 1e-6 || s >= tech.lunchEnd - 1e-6, `${v.jobId} crosses lunch`);
      }
    }
  }
});

test('route timing waits for the window and pushes work past lunch', () => {
  const tech = { id: 'X', depot: { x: 0, y: 0 }, start: 480, end: 1020, lunchStart: 720, lunchEnd: 750, skills: ['CCTV'] };
  const jobs = indexJobs([
    { id: 'A', x: 0, y: 0, duration: 30, windowStart: 600, windowEnd: 1020, skill: 'CCTV' },
    { id: 'B', x: 0, y: 0, duration: 120, windowStart: 480, windowEnd: 1020, skill: 'CCTV' },
  ]);
  const ev = evaluateRoute(tech, ['A', 'B'], jobs, PARAMS);
  assert.equal(ev.visits[0].start, 600); // waited for window
  assert.equal(ev.visits[1].start, 750); // 630 + 120 would cross lunch
  assert.ok(ev.feasible);
});

test('late, overtime and wrong-skill moves are flagged, not fixed', () => {
  const tech = day.techs.find((t) => t.id === 'T2'); // Intruder alarm, CCTV
  const fireJob = day.jobs.find((j) => j.skill === 'Fire alarm');
  const routes = moveJob(auto.routes, fireJob.id, 'T2', 0);
  assert.equal(routes.T2[0], fireJob.id);
  const ev = evaluateRoute(tech, routes.T2, jobById);
  assert.ok(ev.visits[0].flags.includes('skill'));
  assert.ok(!ev.feasible);
  const late = evaluateRoute(tech, [], jobById);
  assert.ok(late.feasible);
  const tight = { id: 'L', x: 19, y: 13, duration: 30, windowStart: 480, windowEnd: 500, skill: 'CCTV' };
  const ev2 = evaluateRoute(tech, ['L'], indexJobs([tight]));
  assert.ok(ev2.visits[0].flags.includes('late'));
});

test('the improver never makes total travel worse', () => {
  const rand = mulberry32(7);
  for (let trial = 0; trial < 5; trial++) {
    // Random feasible starting plans built from shuffled insertion order.
    const shuffled = [...day.jobs].sort(() => rand() - 0.5);
    const routes = emptyRoutes(day.techs);
    for (const job of shuffled) {
      for (const tech of day.techs.filter((t) => t.skills.includes(job.skill))) {
        const cand = [...routes[tech.id], job.id];
        if (evaluateRoute(tech, cand, jobById).feasible) { routes[tech.id] = cand; break; }
      }
    }
    const before = evaluatePlan(day.jobs, day.techs, routes).totals.travelMin;
    const improved = improve(routes, day.jobs, day.techs);
    const after = evaluatePlan(day.jobs, day.techs, improved).totals;
    assert.ok(after.travelMin <= before + 1e-9, `${after.travelMin} > ${before}`);
    assert.equal(after.ruleBreaks, 0);
    assert.deepEqual(Object.values(improved).flat().sort(), Object.values(routes).flat().sort());
  }
});

const scoreOf = (jobs, techs, routes) => {
  const t = evaluatePlan(jobs, techs, routes).totals;
  return { placed: jobs.length - t.unassigned, late: t.ruleBreaks, travel: t.travelMin };
};

test('sample day: at least 38 placed, nothing late, travel at or below 370 minutes', () => {
  const s = scoreOf(day.jobs, day.techs, auto.routes);
  assert.ok(s.placed >= 38, `placed ${s.placed}`);
  assert.equal(s.late, 0);
  assert.ok(s.travel <= 370, `travel ${s.travel}`);
  assert.ok(!auto.unassigned.includes('J010'));
});

test('auto-schedule is the same every time', () => {
  assert.deepEqual(autoSchedule(day.jobs, day.techs).routes, auto.routes);
});

test('on other seeded days auto-schedule is never worse than insertion alone', () => {
  for (const seed of [1, 2, 3, 4, 5, 6]) {
    const d = sampleDay(seed);
    const ins = scoreOf(d.jobs, d.techs, insertionOnly(d.jobs, d.techs));
    const res = scoreOf(d.jobs, d.techs, autoSchedule(d.jobs, d.techs).routes);
    assert.ok(!isBetter(ins, res), `seed ${seed}: insertion ${JSON.stringify(ins)} beat ${JSON.stringify(res)}`);
    assert.equal(res.late, 0);
  }
});

test('manual plan: nearest technician with the skill (ties shared), in time-window order', () => {
  const routes = manualPlan(day.jobs, day.techs);
  for (const [tid, ids] of Object.entries(routes)) {
    const tech = techById.get(tid);
    for (let i = 0; i < ids.length; i++) {
      const job = jobById.get(ids[i]);
      assert.ok(tech.skills.includes(job.skill));
      const mine = distanceKm(tech.depot, job);
      for (const other of day.techs.filter((t) => t.skills.includes(job.skill))) {
        assert.ok(mine <= distanceKm(other.depot, job) + 1e-9);
      }
      if (i) assert.ok(jobById.get(ids[i - 1]).windowStart <= job.windowStart);
    }
  }
});

test('unassigned jobs get a reason that is true', () => {
  const noSkill = { id: 'Z1', customer: 'c', x: 5, y: 5, duration: 30, windowStart: 480, windowEnd: 1020, skill: 'Access control', priority: 2 };
  assert.equal(explainUnassigned(noSkill, day.techs).code, 'skill');
  assert.match(explainUnassigned(noSkill, day.techs).text, /No technician has the Access control skill/);
  const tight = { id: 'Z2', customer: 'c', x: 1, y: 1, duration: 60, windowStart: 480, windowEnd: 545, skill: 'CCTV', priority: 2 };
  assert.equal(explainUnassigned(tight, day.techs).code, 'window');
  for (const id of auto.unassigned) {
    const r = auto.reasons[id];
    assert.ok(['skill', 'window', 'noroom', 'nogap'].includes(r.code), `${id} ${r.code}`);
    if (r.code === 'noroom') assert.equal(makeRoom(jobById.get(id), auto.routes, day.jobs, day.techs), null);
  }
});

test('a job that only fits after moving another is not called full', () => {
  // Rebuild the checker's case: the insertion plan cannot take J010 directly,
  // but moving one job makes room, so the reason must say so.
  const ins = insertionOnly(day.jobs, day.techs);
  const j010 = jobById.get('J010');
  const r = explainUnassigned(j010, day.techs, ins, day.jobs);
  if (Object.values(ins).flat().includes('J010')) return;
  assert.notEqual(r.code, 'noroom');
  assert.ok(!/full/i.test(r.text));
  if (r.code === 'room') assert.ok(makeRoom(j010, ins, day.jobs, day.techs));
});

test('makeRoom places the left-over job without dropping any other', () => {
  const routes = Object.fromEntries(Object.entries(auto.routes).map(([k, v]) => [k, [...v]]));
  const victim = routes.T3[0];
  routes.T3 = routes.T3.slice(1);
  const out = makeRoom(jobById.get(victim), routes, day.jobs, day.techs);
  if (out) {
    const all = Object.values(out).flat();
    assert.ok(all.includes(victim));
    assert.equal(all.length, Object.values(routes).flat().length + 1);
    assert.equal(evaluatePlan(day.jobs, day.techs, out).totals.ruleBreaks, 0);
  }
});

test('a High job is never left out while a Low job that could give way is placed', () => {
  const tech = { id: 'T1', name: 'Asha', depot: { x: 10, y: 7.9 }, start: 480, end: 990, lunchStart: 720, lunchEnd: 750, skills: ['Fire alarm'] };
  const mk = (id, x, priority) => ({ id, customer: id, area: 'a', x, y: 7.9, duration: 225, windowStart: 480, windowEnd: 1020, skill: 'Fire alarm', priority });
  const jobs = [mk('HIGH', 13, 1), mk('LOW1', 11, 3), mk('LOW2', 10.5, 3)];
  const res = autoSchedule(jobs, [tech]);
  assert.ok(res.routes.T1.includes('HIGH'));
  assert.deepEqual(res.unassigned.length, 1);
  assert.equal(jobs.find((j) => j.id === res.unassigned[0]).priority, 3);
});

test('plans are compared by High, then Normal, then Low jobs placed', () => {
  assert.ok(isBetter({ byPriority: [1, 0, 0], placed: 1, late: 0, travel: 99 }, { byPriority: [0, 0, 2], placed: 2, late: 0, travel: 1 }));
  assert.ok(isBetter({ byPriority: [0, 1, 0], placed: 1, late: 0, travel: 99 }, { byPriority: [0, 0, 5], placed: 5, late: 0, travel: 1 }));
  for (const seed of [1, 2, 3]) {
    const d = sampleDay(seed);
    const res = autoSchedule(d.jobs, d.techs);
    const byId = indexJobs(d.jobs);
    for (const id of res.unassigned) assert.notEqual(res.reasons[id].code, 'giveway');
    for (const id of res.unassigned) {
      const r = explainUnassigned(byId.get(id), d.techs, res.routes, d.jobs);
      assert.ok(['skill', 'window', 'noroom'].includes(r.code), `${seed} ${id} ${r.code}`);
    }
  }
});

test('duplicate job ids are refused instead of looping', () => {
  const jobs = [day.jobs[0], { ...day.jobs[1], id: day.jobs[0].id }];
  assert.throws(() => autoSchedule(jobs, day.techs), /own id/);
});
