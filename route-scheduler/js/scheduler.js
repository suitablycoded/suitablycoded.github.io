// Scheduling logic: route timing, plan totals, the manual plan, insertion and improvement.
// Pure functions, no DOM access.
import { PARAMS, formatTime, mulberry32 } from './model.js';

const EPS = 1e-6;

export function distanceKm(a, b, p = PARAMS) {
  return Math.hypot(a.x - b.x, a.y - b.y) * p.roadFactor;
}

export function travelMinutes(a, b, p = PARAMS) {
  return (distanceKm(a, b, p) / p.speedKmh) * 60;
}

// Nothing (travel or work) runs across the lunch break: it waits until lunch ends.
function avoidLunch(t, dur, tech) {
  if (t < tech.lunchEnd - EPS && t + dur > tech.lunchStart + EPS) return tech.lunchEnd;
  return t;
}

export function evaluateRoute(tech, ids, jobsById, p = PARAMS) {
  const visits = [];
  let t = tech.start;
  let pos = tech.depot;
  let travel = 0;
  let dist = 0;
  ids.forEach((id, i) => {
    const job = jobsById.get(id);
    const d = distanceKm(pos, job, p);
    const tr = (d / p.speedKmh) * 60;
    const depart = avoidLunch(t, tr, tech);
    const arrive = depart + tr;
    const start = avoidLunch(Math.max(arrive, job.windowStart), job.duration, tech);
    const finish = start + job.duration;
    const flags = [];
    if (!tech.skills.includes(job.skill)) flags.push('skill');
    if (finish > job.windowEnd + EPS) flags.push('late');
    if (finish > tech.end + EPS) flags.push('overtime');
    visits.push({ jobId: id, order: i + 1, depart, travelMin: tr, distKm: d, arrive, start, finish, flags });
    travel += tr;
    dist += d;
    t = finish;
    pos = job;
  });
  let returnTravelMin = 0;
  let returnDepart = t;
  let backAt = t;
  if (ids.length) {
    const d = distanceKm(pos, tech.depot, p);
    returnTravelMin = (d / p.speedKmh) * 60;
    returnDepart = avoidLunch(t, returnTravelMin, tech);
    backAt = returnDepart + returnTravelMin;
    travel += returnTravelMin;
    dist += d;
  }
  const returnLate = backAt > tech.end + EPS;
  const feasible = !returnLate && visits.every((v) => v.flags.length === 0);
  return { techId: tech.id, visits, travelMin: travel, distKm: dist, returnTravelMin, returnDepart, backAt, returnLate, feasible };
}

export function indexJobs(jobs) {
  return new Map(jobs.map((j) => [j.id, j]));
}

export function emptyRoutes(techs) {
  return Object.fromEntries(techs.map((t) => [t.id, []]));
}

export function unassignedIds(jobs, routes) {
  const used = new Set(Object.values(routes).flat());
  return jobs.filter((j) => !used.has(j.id)).map((j) => j.id);
}

export function evaluatePlan(jobs, techs, routes, p = PARAMS) {
  const byId = indexJobs(jobs);
  const evals = {};
  const totals = { travelMin: 0, distKm: 0, jobsDone: 0, jobsLate: 0, unassigned: 0, ruleBreaks: 0 };
  for (const tech of techs) {
    const ev = evaluateRoute(tech, routes[tech.id] || [], byId, p);
    evals[tech.id] = ev;
    totals.travelMin += ev.travelMin;
    totals.distKm += ev.distKm;
    for (const v of ev.visits) {
      if (!v.flags.includes('skill') && !v.flags.includes('overtime')) totals.jobsDone++;
      if (v.flags.includes('late')) totals.jobsLate++;
      totals.ruleBreaks += v.flags.length;
    }
    if (ev.returnLate) totals.ruleBreaks++;
  }
  const unassigned = unassignedIds(jobs, routes);
  totals.unassigned = unassigned.length;
  return { evals, totals, unassigned };
}


// The manual plan a dispatcher might make without a tool: each job goes to the
// nearest technician (by depot) who has the skill, sharing ties in turn, and each visits
// their jobs in time-window order. Nothing checks for clashes or hours.
export function manualPlan(jobs, techs, p = PARAMS) {
  const routes = emptyRoutes(techs);
  const sorted = [...jobs].sort((a, b) => a.windowStart - b.windowStart || a.windowEnd - b.windowEnd || a.id.localeCompare(b.id));
  for (const job of sorted) {
    let best = null;
    let bestD = Infinity;
    for (const t of techs) {
      if (!t.skills.includes(job.skill)) continue;
      const d = distanceKm(t.depot, job, p);
      // Technicians sharing a depot take turns: the one with fewer jobs so far.
      if (d < bestD - EPS || (Math.abs(d - bestD) <= EPS && routes[t.id].length < routes[best.id].length)) { bestD = d; best = t; }
    }
    if (best) routes[best.id].push(job.id);
  }
  return routes;
}

function cloneRoutes(routes) {
  return Object.fromEntries(Object.entries(routes).map(([k, v]) => [k, [...v]]));
}

function routeCosts(routes, techs, byId, p) {
  return Object.fromEntries(techs.map((t) => [t.id, evaluateRoute(t, routes[t.id], byId, p).travelMin]));
}

function bestInsertion(job, routes, techs, byId, costs, p) {
  let best = null;
  for (const tech of techs) {
    if (!tech.skills.includes(job.skill)) continue;
    const r = routes[tech.id];
    for (let pos = 0; pos <= r.length; pos++) {
      const cand = [...r.slice(0, pos), job.id, ...r.slice(pos)];
      const ev = evaluateRoute(tech, cand, byId, p);
      if (!ev.feasible) continue;
      const delta = ev.travelMin - costs[tech.id];
      if (!best || delta < best.delta - EPS || (Math.abs(delta - best.delta) <= EPS && ev.backAt < best.backAt)) {
        best = { techId: tech.id, route: cand, delta, travelMin: ev.travelMin, backAt: ev.backAt };
      }
    }
  }
  return best;
}

function insertAll(order, routes, techs, byId, p) {
  const costs = routeCosts(routes, techs, byId, p);
  const left = [];
  for (const job of order) {
    const best = bestInsertion(job, routes, techs, byId, costs, p);
    if (best) {
      routes[best.techId] = best.route;
      costs[best.techId] = best.travelMin;
    } else {
      left.push(job);
    }
  }
  return left;
}

// Tries to place a left-over job by taking one placed job out, putting the
// left-over job in, then finding the removed job a new place. Returns the new
// routes or null if no single move makes room.
export function makeRoom(job, routes, jobs, techs, p = PARAMS) {
  const byId = indexJobs(jobs);
  let best = null;
  for (const owner of techs) {
    for (const otherId of routes[owner.id]) {
      const trial = cloneRoutes(routes);
      trial[owner.id] = trial[owner.id].filter((id) => id !== otherId);
      const left = insertAll([job, byId.get(otherId)], trial, techs, byId, p);
      if (left.length) continue;
      const travel = techs.reduce((s, t) => s + evaluateRoute(t, trial[t.id], byId, p).travelMin, 0);
      if (!best || travel < best.travel - EPS) best = { routes: trial, travel };
    }
  }
  return best ? best.routes : null;
}

// Plain-words reason for a job that is not in the plan. Only says what was checked.
export function explainUnassigned(job, techs, routes = null, jobs = null, p = PARAMS, opts = {}) {
  const qualified = techs.filter((t) => t.skills.includes(job.skill));
  if (!qualified.length) return { code: 'skill', text: `No technician has the ${job.skill} skill.` };
  if (job.windowEnd - job.windowStart < job.duration) {
    return { code: 'window', text: `Window too short: the visit takes ${job.duration} minutes but the window ${formatTime(job.windowStart)} to ${formatTime(job.windowEnd)} is only ${job.windowEnd - job.windowStart} minutes.` };
  }
  const single = new Map([[job.id, job]]);
  if (!qualified.some((t) => evaluateRoute(t, [job.id], single, p).feasible)) {
    return { code: 'window', text: `Window too tight: even with an empty day, no qualified technician can travel there and finish between ${formatTime(job.windowStart)} and ${formatTime(job.windowEnd)} within their hours.` };
  }
  if (!routes || !jobs) return { code: 'fits-alone', text: 'Fits into an empty day for a qualified technician.' };
  const byId = indexJobs(jobs);
  const fit = qualified.find((t) => {
    const r = routes[t.id] || [];
    for (let pos = 0; pos <= r.length; pos++) {
      if (evaluateRoute(t, [...r.slice(0, pos), job.id, ...r.slice(pos)], byId, p).feasible) return true;
    }
    return false;
  });
  if (fit) return { code: 'fits', text: `Not in this plan, but it fits into ${fit.name}'s route as it stands. Move it there or run Auto-schedule.` };
  const names = qualified.map((t) => t.name).join(', ');
  if (opts.deep !== false) {
    if (makeRoom(job, routes, jobs, techs, p)) {
      return { code: 'room', text: `No gap in the routes as they stand, but it can fit if another job is moved. Run Auto-schedule.` };
    }
    if (giveWay(job, routes, jobs, techs, p)) {
      return { code: 'giveway', text: `No gap in the routes as they stand, but it fits if a lower-priority job gives way. Run Auto-schedule.` };
    }
    return { code: 'noroom', text: `No room in this plan: it fits nowhere in the routes of ${names}, even after trying to move any one other job out of the way or to take out a lower-priority job.` };
  }
  return { code: 'nogap', text: `No gap in the routes of ${names} as they stand.` };
}

// Local improvement. Only accepts a change when every route it touches stays within
// all rules and the total travel goes down, so travel can never get worse.
// Moves tried: reverse a stretch (2-opt), move a run of 1 to 3 jobs (or-opt, within
// or between routes), and swap two jobs between routes.
export function improve(routesIn, jobs, techs, p = PARAMS, maxRounds = 200) {
  const byId = indexJobs(jobs);
  const routes = cloneRoutes(routesIn);
  const cost = routeCosts(routes, techs, byId, p);
  const evalT = (t, r) => evaluateRoute(t, r, byId, p);
  let rounds = 0;
  let changed = true;
  while (changed && rounds++ < maxRounds) {
    changed = false;
    twoOpt: for (const tech of techs) {
      const r = routes[tech.id];
      for (let i = 0; i < r.length - 1; i++) {
        for (let j = i + 1; j < r.length; j++) {
          const cand = [...r.slice(0, i), ...r.slice(i, j + 1).reverse(), ...r.slice(j + 1)];
          const ev = evalT(tech, cand);
          if (ev.feasible && ev.travelMin < cost[tech.id] - EPS) {
            routes[tech.id] = cand; cost[tech.id] = ev.travelMin; changed = true; break twoOpt;
          }
        }
      }
    }
    if (changed) continue;
    orOpt: for (const a of techs) {
      for (let len = 1; len <= 3; len++) {
        const ra = routes[a.id];
        for (let i = 0; i + len <= ra.length; i++) {
          const seg = ra.slice(i, i + len);
          const without = [...ra.slice(0, i), ...ra.slice(i + len)];
          const evWithout = evalT(a, without);
          for (const b of techs) {
            if (!seg.every((id) => b.skills.includes(byId.get(id).skill))) continue;
            const base = b.id === a.id ? without : routes[b.id];
            for (let pos = 0; pos <= base.length; pos++) {
              if (b.id === a.id && pos === i) continue;
              for (const s of len > 1 ? [seg, [...seg].reverse()] : [seg]) {
                const cand = [...base.slice(0, pos), ...s, ...base.slice(pos)];
                const evB = evalT(b, cand);
                if (!evB.feasible) continue;
                if (b.id === a.id) {
                  if (evB.travelMin < cost[a.id] - EPS) {
                    routes[a.id] = cand; cost[a.id] = evB.travelMin; changed = true; break orOpt;
                  }
                } else if (evWithout.feasible && evWithout.travelMin + evB.travelMin < cost[a.id] + cost[b.id] - EPS) {
                  routes[a.id] = without; routes[b.id] = cand;
                  cost[a.id] = evWithout.travelMin; cost[b.id] = evB.travelMin; changed = true; break orOpt;
                }
              }
            }
          }
        }
      }
    }
    if (changed) continue;
    swap: for (let x = 0; x < techs.length; x++) {
      for (let y = x + 1; y < techs.length; y++) {
        const a = techs[x];
        const b = techs[y];
        const ra = routes[a.id];
        const rb = routes[b.id];
        for (let i = 0; i < ra.length; i++) {
          if (!b.skills.includes(byId.get(ra[i]).skill)) continue;
          for (let j = 0; j < rb.length; j++) {
            if (!a.skills.includes(byId.get(rb[j]).skill)) continue;
            const na = [...ra]; na[i] = rb[j];
            const nb = [...rb]; nb[j] = ra[i];
            const ea = evalT(a, na);
            if (!ea.feasible) continue;
            const eb = evalT(b, nb);
            if (eb.feasible && ea.travelMin + eb.travelMin < cost[a.id] + cost[b.id] - EPS) {
              routes[a.id] = na; routes[b.id] = nb;
              cost[a.id] = ea.travelMin; cost[b.id] = eb.travelMin; changed = true; break swap;
            }
          }
        }
      }
    }
  }
  return routes;
}

function score(routes, jobs, techs, p) {
  const byId = indexJobs(jobs);
  let placed = 0;
  let travel = 0;
  let late = 0;
  const byPriority = [0, 0, 0];
  for (const t of techs) {
    const ev = evaluateRoute(t, routes[t.id], byId, p);
    placed += routes[t.id].length;
    for (const id of routes[t.id]) byPriority[byId.get(id).priority - 1]++;
    travel += ev.travelMin;
    late += ev.visits.filter((v) => v.flags.length).length + (ev.returnLate ? 1 : 0);
  }
  return { placed, byPriority, late, travel };
}

export function planScore(routes, jobs, techs, p = PARAMS) {
  return score(routes, jobs, techs, p);
}

function samePlaced(a, b) {
  return a.placed === b.placed && (!a.byPriority || a.byPriority.every((n, i) => n === b.byPriority[i]));
}

// Order of priority: most High jobs placed, then most Normal, then most Low,
// then fewest rule breaks, then least travel.
export function isBetter(a, b) {
  if (a.byPriority && b.byPriority) {
    for (let i = 0; i < 3; i++) if (a.byPriority[i] !== b.byPriority[i]) return a.byPriority[i] > b.byPriority[i];
  }
  if (a.placed !== b.placed) return a.placed > b.placed;
  if (a.late !== b.late) return a.late < b.late;
  return a.travel < b.travel - EPS;
}

// Places a left-over job by taking out one placed job of lower priority. The
// removed job goes back in if it still fits anywhere. Returns new routes or null.
export function giveWay(job, routes, jobs, techs, p = PARAMS) {
  const byId = indexJobs(jobs);
  let best = null;
  for (const owner of techs) {
    if (!owner.skills.includes(job.skill)) continue;
    for (const otherId of routes[owner.id]) {
      if (byId.get(otherId).priority <= job.priority) continue;
      const trial = cloneRoutes(routes);
      trial[owner.id] = trial[owner.id].filter((id) => id !== otherId);
      const left = insertAll([job], trial, techs, byId, p);
      if (left.length) continue;
      insertAll([byId.get(otherId)], trial, techs, byId, p);
      const sc = score(trial, jobs, techs, p);
      if (!best || isBetter(sc, best.sc)) best = { routes: trial, sc };
    }
  }
  return best ? best.routes : null;
}

function insertionOrder(jobs) {
  return [...jobs].sort((a, b) =>
    a.priority - b.priority ||
    (a.windowEnd - a.windowStart) - (b.windowEnd - b.windowStart) ||
    a.id.localeCompare(b.id));
}

// Simple insertion alone, with no improvement. Used as the yardstick in tests.
export function insertionOnly(jobs, techs, p = PARAMS) {
  const routes = emptyRoutes(techs);
  insertAll(insertionOrder(jobs), routes, techs, indexJobs(jobs), p);
  return routes;
}

function fillLeftovers(routes, jobs, techs, p) {
  const byId = indexJobs(jobs);
  let current = routes;
  let left = insertAll(insertionOrder(unassignedIds(jobs, current).map((id) => byId.get(id))), current, techs, byId, p);
  let progress = true;
  while (progress && left.length && left.length <= 60) {
    progress = false;
    for (const job of left) {
      const made = makeRoom(job, current, jobs, techs, p) || giveWay(job, current, jobs, techs, p);
      if (made) { current = made; progress = true; break; }
    }
    left = unassignedIds(jobs, current).map((id) => byId.get(id));
  }
  return current;
}

// Full automatic plan.
// 1. Insertion: urgent and tight-window jobs first, each in its cheapest valid place.
// 2. Improvement (2-opt, or-opt, swap) and making room for left-over jobs.
//    A left-over job may also take the place of a lower-priority job.
// 3. A fixed number of "remove and rebuild" rounds from a fixed seed: take out a
//    small group of nearby jobs, put them and any left-over jobs back in a shuffled
//    order, and keep the result when it places more jobs or travels less.
// The result is the same every time. A time limit only applies to lists over 100 jobs.
export function autoSchedule(jobs, techs, p = PARAMS, opts = {}) {
  const { rounds = 3000, seed = 12345, timeLimitMs = 700, limitAbove = 100 } = opts;
  const t0 = Date.now();
  const byId = indexJobs(jobs);
  if (byId.size !== jobs.length) throw new Error('Every job needs its own id.');
  // The time limit only applies to long lists, so normal days give the same plan on any device.
  const useLimit = jobs.length > limitAbove;
  const rand = mulberry32(seed);
  const baseline = insertionOnly(jobs, techs, p);
  let cur = fillLeftovers(improve(baseline, jobs, techs, p), jobs, techs, p);
  cur = improve(cur, jobs, techs, p);
  let curScore = score(cur, jobs, techs, p);
  let best = cur;
  let bestScore = curScore;
  let roundsRun = 0;
  for (let it = 0; it < rounds; it++) {
    if (useLimit && Date.now() - t0 > timeLimitMs) break;
    roundsRun++;
    const routed = Object.values(cur).flat();
    if (!routed.length) break;
    const k = 2 + Math.floor(rand() * 7);
    let remove;
    if (rand() < 0.5) {
      const seedJob = byId.get(routed[Math.floor(rand() * routed.length)]);
      remove = new Set(routed
        .map((id) => [id, Math.hypot(byId.get(id).x - seedJob.x, byId.get(id).y - seedJob.y)])
        .sort((a, b) => a[1] - b[1]).slice(0, k).map((e) => e[0]));
    } else {
      remove = new Set();
      while (remove.size < Math.min(k, routed.length)) remove.add(routed[Math.floor(rand() * routed.length)]);
    }
    const cand = Object.fromEntries(Object.entries(cur).map(([t, r]) => [t, r.filter((id) => !remove.has(id))]));
    const pool = unassignedIds(jobs, cand).map((id) => byId.get(id));
    const keyed = pool.map((j) => [j, j.priority + rand() * 3]).sort((a, b) => a[1] - b[1]).map((e) => e[0]);
    insertAll(keyed, cand, techs, byId, p);
    const s = score(cand, jobs, techs, p);
    // Accept better plans, and now and then a slightly worse one with the same
    // number placed, so the search can step out of a dead end. The allowance
    // shrinks to nothing by the last round.
    const allowance = 25 * (1 - it / rounds) * rand();
    if (isBetter(s, curScore) || (samePlaced(s, curScore) && s.late === 0 && s.travel < curScore.travel + allowance)) {
      cur = cand;
      curScore = s;
      if (isBetter(s, bestScore)) {
        best = cand;
        bestScore = s;
      }
    }
  }
  best = fillLeftovers(best, jobs, techs, p);
  best = improve(best, jobs, techs, p);
  const finalScore = score(best, jobs, techs, p);
  const left = unassignedIds(jobs, best);
  const deep = left.length <= 30;
  const reasons = Object.fromEntries(left.map((id) => [id, explainUnassigned(byId.get(id), techs, best, jobs, p, { deep })]));
  return { routes: best, unassigned: left, reasons, rounds: roundsRun, score: finalScore };
}

// Move a job to a technician at a position (or unassign with techId null).
// Returns new routes. Never fixes anything the move breaks.
export function moveJob(routes, jobId, techId, position) {
  const next = Object.fromEntries(Object.entries(routes).map(([k, v]) => [k, v.filter((id) => id !== jobId)]));
  if (techId) {
    const r = next[techId];
    const pos = Math.max(0, Math.min(position ?? r.length, r.length));
    r.splice(pos, 0, jobId);
  }
  return next;
}
