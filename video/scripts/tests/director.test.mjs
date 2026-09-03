import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {buildTimeline, cameraFor, moveCamera, validateTake} from '../../src/director.mjs';

const edit = JSON.parse(await readFile(new URL('../../script/simulation-edit.json', import.meta.url), 'utf8'));
const rect = {x: 500, y: 250, width: 270, height: 220};
function take() {
  return {schemaVersion: 2, footage: 'footage/actual.mp4', viewport: {width: 1920, height: 1080}, shots: Object.fromEntries(edit.map((shot, index) => [shot.id, {sourceStart: index * 20 + 5, sourceEnd: index * 20 + 5 + shot.seconds + 0.3, scenarioId: shot.scenarioId, nodeId: shot.nodeId ?? null, attempt: shot.attempt ?? null, target: rect, highlight: rect, ...(shot.phase === 'ready' ? {interaction: {at: 4.5, target: rect, highlight: rect}} : {})}])), runs: {'S7-M01': {status: 'completed'}, 'S2-M01': {status: 'completed', approvalPerformed: true}}};
}

test('simulation-only edit is exactly 115 seconds and S7 precedes S2', () => {
  const timeline = buildTimeline(edit);
  assert.equal(timeline.at(-1).start + timeline.at(-1).duration, 115 * 30);
  assert.deepEqual([...new Set(edit.map((shot) => shot.scenarioId))], ['S7-M01', 'S2-M01']);
  assert.equal(new Set(edit.map((shot) => shot.id)).size, edit.length);
  assert.ok(edit.filter((shot) => !shot.speech).length >= 6);
});
test('strict evidence matching accepts the complete take', () => assert.equal(validateTake(edit, take()).schemaVersion, 2));
test('missing clips never fall back to another state', () => {
  const value = take(); delete value.shots['s7-failure'];
  assert.throws(() => validateTake(edit, value), /Missing actual footage/);
});
test('replanning must use the second visit', () => {
  const value = take(); value.shots['s7-replan'].attempt = 1;
  assert.throws(() => validateTake(edit, value), /node\/visit mismatch/);
});
test('short or unapproved takes are rejected', () => {
  const value = take(); value.shots['s2-approve'].sourceEnd = value.shots['s2-approve'].sourceStart + 1;
  assert.throws(() => validateTake(edit, value), /Insufficient recorded duration/);
  const unapproved = take(); unapproved.runs['S2-M01'].approvalPerformed = false;
  assert.throws(() => validateTake(edit, unapproved), /explicit simulated S2 approval/);
});
test('the two start interactions must be visibly framed', () => {
  const value = take(); delete value.shots['s2-request'].interaction;
  assert.throws(() => validateTake(edit, value), /visible start interaction/);
});
test('camera supports larger close-ups without revealing empty edges', () => {
  const source = {width: 1920, height: 1080};
  const closeup = cameraFor(rect, source);
  assert.ok(closeup.scale > 2.35 && closeup.scale <= 3.15);
  for (const target of [rect, {x: 1650, y: 880, width: 270, height: 200}, {x: 0, y: 0, width: 1920, height: 1080}]) {
    const view = cameraFor(target, source);
    assert.ok(view.x <= 0 && view.y <= 0);
    assert.ok(view.x + source.width * view.scale >= source.width);
    assert.ok(view.y + source.height * view.scale >= source.height);
  }
});
test('camera carries the previous view into the next shot without resetting', () => {
  const previous = {x: -500, y: -240, scale: 2.8};
  const next = {x: -20, y: -40, scale: 2.5};
  assert.deepEqual(moveCamera(previous, next, 0), previous);
  assert.deepEqual(moveCamera(previous, next, 30), next);
});
test('composition uses moving footage with no caption or dimming layers', async () => {
  const component = await readFile(new URL('../../src/SimulationFilm.tsx', import.meta.url), 'utf8');
  const css = await readFile(new URL('../../src/styles.css', import.meta.url), 'utf8');
  assert.match(component, /OffthreadVideo/);
  assert.doesNotMatch(component, /<Img|caption-card|film-vignette|chapter-chip|capture-badge|film-disclosure/);
  assert.doesNotMatch(css, /gradient|backdrop-filter/);
});
