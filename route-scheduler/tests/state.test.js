import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sampleDay, validateState } from '../js/model.js';

test('good saved state is accepted', () => {
  const { jobs, techs } = sampleDay();
  const s = validateState(JSON.parse(JSON.stringify({ jobs, techs, routes: { T1: [jobs[0].id] }, mode: 'auto' })));
  assert.ok(s);
  assert.equal(s.jobs.length, 40);
  assert.equal(validateState({ jobs, techs, routes: {}, mode: 'hand' }).mode, 'manual');
});

test('corrupt saved state of the right shape is rejected', () => {
  const { jobs, techs } = sampleDay();
  const bad = [
    null, {}, { jobs: [null], techs: [], routes: {} }, { jobs: [null], techs, routes: {} },
    { jobs: [{ id: 'A' }], techs, routes: {} }, { jobs, techs: [{ id: 'T1' }], routes: {} },
    { jobs, techs, routes: { T1: 'J001' } }, { jobs, techs, routes: [] }, { jobs: 'x', techs, routes: {} },
    { jobs: [jobs[0], { ...jobs[0], id: jobs[0].id.toLowerCase() }], techs, routes: {} },
  ];
  for (const b of bad) assert.equal(validateState(b), null, JSON.stringify(b)?.slice(0, 60));
});
