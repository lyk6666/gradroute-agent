import {mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {startHighQualityRecording} from './high-quality-recorder.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const edit = JSON.parse(await readFile(path.join(root, 'script/simulation-edit.json'), 'utf8'));
const arg = (name, fallback) => process.argv.find((item) => item.startsWith(`--${name}=`))?.split('=').slice(1).join('=') ?? fallback;
const frontend = arg('frontend-url', 'http://localhost:3000');
const backend = arg('backend-url', 'http://127.0.0.1:8000');
const viewport = {width: 1920, height: 1080};
const takeId = new Date().toISOString().replace(/[:.]/g, '-');
const artifactRoot = path.join(root, 'artifacts', `ui-only-${takeId}`);
const footageRoot = path.join(root, 'public/footage');
const manifestPath = path.join(root, 'public/captures/simulation-take.json');
const manifest = {schemaVersion: 2, capturedAt: new Date().toISOString(), viewport, executionMode: 'unknown', footage: `footage/ui-only-${takeId}.mp4`, shots: {}, runs: {}};
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const expand = (box, horizontal, vertical) => ({x: Math.max(0, box.x - horizontal), y: Math.max(0, box.y - vertical), width: Math.min(viewport.width - Math.max(0, box.x - horizontal), box.width + horizontal * 2), height: Math.min(viewport.height - Math.max(0, box.y - vertical), box.height + vertical * 2)});

async function main() {
  await mkdir(artifactRoot, {recursive: true});
  await mkdir(footageRoot, {recursive: true});
  await mkdir(path.dirname(manifestPath), {recursive: true});
  const health = await fetch(`${backend}/api/v1/health`).then((response) => response.json());
  manifest.executionMode = health.execution_mode ?? 'unknown';
  let browser;
  try { browser = await chromium.launch({channel: 'chrome', headless: arg('headed', 'false') !== 'true'}); }
  catch { browser = await chromium.launch({headless: arg('headed', 'false') !== 'true'}); }
  const context = await browser.newContext({viewport, deviceScaleFactor: 1, colorScheme: 'light'});
  const page = await context.newPage();
  const ffmpeg = path.join(root, 'node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe');
  const recording = await startHighQualityRecording(page, ffmpeg, path.join(root, 'public', manifest.footage));
  const epoch = recording.startedAt;
  const now = () => recording.elapsed();
  let latest = null;
  let failure = null;

  async function box(selector) {
    const result = await page.locator(selector).first().boundingBox();
    if (!result) throw new Error(`No visible bounds for ${selector}`);
    return result;
  }

  async function focus(shot) {
    if (shot.focus === 'request') {
      const request = page.locator('.scenario-preview-section').filter({has: page.getByText('Request', {exact: true})});
      await request.scrollIntoViewIfNeeded();
      const rect = await request.boundingBox();
      if (!rect) throw new Error('Request is not visible');
      return {target: expand(rect, 42, 100), highlight: rect};
    }
    if (shot.focus === 'graph') {
      const rect = await box(`[data-demo-node="${shot.nodeId}"]`);
      return {target: expand(rect, 245, 150), highlight: rect};
    }
    if (shot.focus === 'response') {
      await page.locator('.response-content').evaluate((element) => element.scrollTo({top: 0}));
      const rect = await box('[data-demo-target="final-response"]');
      return {target: expand(rect, 40, 70), highlight: rect};
    }
    if (shot.focus === 'approval') {
      const rect = await box('.approval-preview-card');
      return {target: expand(rect, 45, 35), highlight: shot.phase === 'approval-action' ? await box('.approval-buttons') : rect};
    }
    const selector = shot.focus === 'action' ? '.human-interaction-card' : '.node-detail-card';
    await page.locator(selector).evaluate((element) => element.scrollTo({top: 0}));
    if (shot.focus === 'action') {
      const details = page.locator(`${selector} details`).first();
      if (await details.count() && !(await details.evaluate((element) => element.open))) await details.locator('summary').click();
    }
    const rect = await box(selector);
    return {target: expand(rect, 45, 40), highlight: rect};
  }

  async function record(shot, during, motionStart) {
    const framing = await focus(shot);
    if (shot.phase === 'ready') {
      framing.interaction = {at: 4.5, target: expand(await box('[data-demo-target="run-controls"]'), 45, 45), highlight: await box('.start-run-button')};
    }
    await delay(250);
    const sourceStart = motionStart ?? now();
    const screenshot = path.join(artifactRoot, `${shot.id}.png`);
    await page.screenshot({path: screenshot});
    if (during) {
      await delay((shot.phase === 'ready' ? 6 : Math.min(3, shot.seconds / 2)) * 1000);
      await during();
    } else if (shot.phase === 'approval-evidence') {
      await delay(4000);
      await page.locator('.approval-preview-card').evaluate((element) => {
        const evidence = element.querySelector('.approval-evidence');
        if (evidence) element.scrollTo({top: evidence.getBoundingClientRect().top - element.getBoundingClientRect().top + element.scrollTop - 12, behavior: 'smooth'});
      });
    } else if (shot.focus === 'response') {
      await delay(4500);
      await page.locator('.response-content').evaluate((element) => {
        const reasoning = element.querySelector('.response-reasoning');
        const top = reasoning
          ? reasoning.getBoundingClientRect().top - element.getBoundingClientRect().top + element.scrollTop - 8
          : 160;
        element.scrollTo({top, behavior: 'smooth'});
      });
    }
    await delay(Math.max(0, (shot.seconds + 0.3 - (now() - sourceStart)) * 1000));
    manifest.shots[shot.id] = {sourceStart, sourceEnd: now(), ...framing, scenarioId: shot.scenarioId, nodeId: shot.nodeId ?? null, attempt: shot.attempt ?? null, status: latest?.status ?? 'ready'};
    await writeFile(path.join(artifactRoot, 'capture-checkpoint.json'), JSON.stringify({...manifest, captureEpochUnixMs: epoch}, null, 2));
    console.log(`Recorded ${shot.id} (${shot.seconds}s, ${shot.focus})`);
  }

  async function settled(snapshot, previous) {
    const deadline = Date.now() + 180000;
    while (Date.now() < deadline) {
      if (snapshot.latest_event_sequence > previous && (snapshot.can_advance || ['waiting', 'completed', 'failed'].includes(snapshot.status))) {
        await delay(650);
        return snapshot;
      }
      await delay(500);
      const response = await page.request.get(`${backend}/api/v1/runs/${snapshot.run_id}`);
      if (!response.ok()) throw new Error(`Polling failed: ${response.status()}`);
      snapshot = await response.json();
    }
    throw new Error(`Run did not settle: ${snapshot.run_id}`);
  }

  async function submit(button, suffix, previous = latest?.latest_event_sequence ?? -1) {
    const [response] = await Promise.all([
      page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith(suffix), {timeout: 180000}),
      button.click(),
    ]);
    if (!response.ok()) throw new Error(`Runtime request failed: ${response.status()} ${suffix}`);
    const payload = await response.json();
    latest = await settled(payload.snapshot ?? payload, previous);
  }

  try {
    if (recording.viewport.width !== viewport.width || recording.viewport.height !== viewport.height) throw new Error('Recording dimensions differ from the measured UI coordinate system.');
    await page.goto(frontend, {waitUntil: 'networkidle'});
    await page.getByRole('status').filter({hasText: 'Operational'}).waitFor({timeout: 60000});
    await page.locator('[data-demo-target="agent-graph"]').waitFor({timeout: 30000});

    for (const scenarioId of ['S7-M01', 'S2-M01']) {
      latest = null;
      await page.getByLabel('Scenario', {exact: true}).selectOption(scenarioId);
      await page.getByRole('button', {name: 'Step-by-step', exact: true}).click();
      await delay(700);
      const caseShots = edit.filter((shot) => shot.scenarioId === scenarioId);
      await record(caseShots.find((shot) => shot.phase === 'ready'), async () => {
        await submit(page.getByRole('button', {name: /^Start (grounded run|a new run)$/}), '/api/v1/runs', -1);
      });
      let steps = 0;
      const seenEvents = new Set();
      let approvalPerformed = false;
      while (!['completed', 'failed'].includes(latest.status)) {
        const event = latest.timeline?.at(-1);
        const nodeId = event?.node_id ?? latest.current_node;
        const attempt = latest.node_details?.[nodeId]?.attempt ?? event?.attempt ?? 1;
        const eventKey = `${nodeId}:${attempt}`;
        const shot = caseShots.find((item) => item.nodeId === nodeId && item.attempt === attempt);
        if (shot && !seenEvents.has(eventKey)) {
          await page.locator(`.react-flow__node[data-id="${nodeId}"]`).click();
          await delay(400);
          await record(shot);
          await writeFile(path.join(artifactRoot, `${shot.id}.json`), JSON.stringify(latest, null, 2));
          seenEvents.add(eventKey);
        }
        if (latest.status === 'waiting') {
          if (scenarioId !== 'S2-M01' || latest.pause?.kind !== 'approval') throw new Error(`Unexpected ${latest.pause?.kind} checkpoint in ${scenarioId}`);
          await page.locator('.react-flow__node[data-id="human_approval"]').click();
          const approve = page.getByRole('button', {name: 'Approve', exact: true});
          await approve.waitFor({state: 'visible'});
          await page.waitForFunction(() => [...document.querySelectorAll('button')].some((button) => button.textContent?.trim() === 'Approve' && !button.disabled));
          const approvalPanel = page.locator('.approval-preview-card');
          await approvalPanel.evaluate((element) => element.scrollTo({top: 0}));
          await record(caseShots.find((item) => item.phase === 'approval-evidence'));
          const approvalScrollAt = now();
          await approvalPanel.evaluate((element) => element.scrollTo({top: element.scrollHeight, behavior: 'smooth'}));
          await delay(650);
          await record(caseShots.find((item) => item.phase === 'approval-action'), async () => {
            await submit(approve, '/resume');
            approvalPerformed = true;
          }, approvalScrollAt);
        } else if (latest.can_advance) {
          await submit(page.getByRole('button', {name: 'Run next graph step', exact: true}), '/advance');
        } else {
          throw new Error(`Unexpected unsettled run state: ${latest.status}`);
        }
        if (++steps > 55) throw new Error('Capture exceeded its bounded step budget.');
      }
      if (latest.status !== 'completed' || !latest.final_response) throw new Error(`${scenarioId} did not complete with a verified response.`);
      if (scenarioId === 'S2-M01' && !approvalPerformed) throw new Error('S2 never received an explicit simulated reviewer action.');
      await page.getByRole('button', {name: 'Start a new run', exact: true}).waitFor({state: 'visible', timeout: 20000});
      await record(caseShots.find((item) => item.phase === 'final'));
      await writeFile(path.join(artifactRoot, `${scenarioId}-final.json`), JSON.stringify(latest, null, 2));
      manifest.runs[scenarioId] = {runId: latest.run_id, status: latest.status, approvalPerformed, headline: latest.final_response.headline, capturedSteps: steps};
    }
    for (const shot of edit) if (!manifest.shots[shot.id]) throw new Error(`Missing required observed clip: ${shot.id}`);
  } catch (error) { failure = error; }
  finally {
    try { manifest.recording = await recording.stop(); }
    finally { await context.close(); await browser.close(); }
  }

  manifest.clockOffsetSeconds = 0;
  await writeFile(path.join(artifactRoot, 'simulation-take.json'), JSON.stringify(manifest, null, 2));
  if (failure) throw failure;
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`Continuous ${manifest.executionMode} take complete: ${Object.keys(manifest.shots).length} clips; ${manifest.footage}`);
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
