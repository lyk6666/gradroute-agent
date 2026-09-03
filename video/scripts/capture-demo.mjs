import {mkdir, readFile, rename, rm, writeFile} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const currentFile = fileURLToPath(import.meta.url);
const videoRoot = path.resolve(path.dirname(currentFile), '..');
const captureRoot = path.join(videoRoot, 'public', 'captures');
const rawRoot = path.join(videoRoot, 'artifacts', 'raw');
const browserViewport = {width: 1920, height: 1080};
const deviceScaleFactor = 2;
const viewport = {width: 3840, height: 2160};

function argument(name, fallback) {
  const prefix = `--${name}=`;
  const item = process.argv.find((value) => value.startsWith(prefix));
  return item ? item.slice(prefix.length) : fallback;
}

const frontendUrl = argument('frontend-url', 'http://localhost:3000').replace(/\/$/, '');
const backendUrl = argument('backend-url', 'http://127.0.0.1:8000').replace(/\/$/, '');
const headed = argument('headed', 'false') === 'true';
const keepRawVideo = argument('raw-video', 'true') !== 'false';
const holdMs = Number(argument('hold-ms', '650'));
const takes = new Set(argument('takes', 'tour,s7,s2,proof').split(',').map((item) => item.trim()).filter(Boolean));
const cleanCapture = argument('clean', 'true') !== 'false';

const manifest = {
  schemaVersion: 1,
  capturedAt: new Date().toISOString(),
  viewport,
  executionMode: 'unknown',
  source: {
    frontendUrl,
    backendUrl,
    disclosure: 'Recorded from a real system run using grounded public sources and simulated operational data.',
  },
  frames: {},
  rawVideos: {},
  runs: {},
};

function safeId(value) {
  return value.toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-|-$/g, '');
}

function unionBoxes(boxes) {
  if (!boxes.length) return {x: 0, y: 0, width: viewport.width, height: viewport.height};
  const x = Math.min(...boxes.map((box) => box.x));
  const y = Math.min(...boxes.map((box) => box.y));
  const right = Math.max(...boxes.map((box) => box.x + box.width));
  const bottom = Math.max(...boxes.map((box) => box.y + box.height));
  return {x, y, width: right - x, height: bottom - y};
}

async function focusBox(page, selectors) {
  const boxes = [];
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    if (await locator.count()) {
      const box = await locator.boundingBox();
      if (box) boxes.push({
        x: box.x * deviceScaleFactor,
        y: box.y * deviceScaleFactor,
        width: box.width * deviceScaleFactor,
        height: box.height * deviceScaleFactor,
      });
    }
  }
  return unionBoxes(boxes);
}

async function captureFrame(page, id, {selectors = [], caption, metadata = {}}) {
  const filename = `${safeId(id)}.png`;
  const target = await focusBox(page, selectors);
  await page.screenshot({path: path.join(captureRoot, filename), animations: 'disabled'});
  manifest.frames[id] = {
    id,
    file: `captures/${filename}`,
    target,
    caption,
    metadata,
  };
  return manifest.frames[id];
}

async function waitForWorkspace(page) {
  await page.getByRole('status').filter({hasText: 'Operational'}).waitFor({state: 'visible', timeout: 60000});
  await page.locator('[data-demo-target="agent-graph"]').waitFor({state: 'visible', timeout: 30000});
  await page.waitForTimeout(400);
}

async function createTake(browser, takeName) {
  const contextOptions = {
    viewport: browserViewport,
    deviceScaleFactor,
    colorScheme: 'light',
    reducedMotion: 'reduce',
  };
  if (keepRawVideo) contextOptions.recordVideo = {dir: rawRoot, size: viewport};
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();
  await page.addInitScript(() => {
    document.documentElement.dataset.demoCapture = 'true';
  });
  await page.addStyleTag({content: '*{caret-color:transparent!important} html{scroll-behavior:auto!important}'}).catch(() => undefined);
  const video = keepRawVideo ? page.video() : null;
  return {
    page,
    async close() {
      await context.close();
      if (video) {
        const temporary = await video.path();
        const destination = path.join(rawRoot, `${takeName}.webm`);
        await rm(destination, {force: true});
        await rename(temporary, destination);
        manifest.rawVideos[takeName] = `artifacts/raw/${takeName}.webm`;
      }
    },
  };
}

async function captureTour(browser) {
  const take = await createTake(browser, 'system-tour');
  const {page} = take;
  try {
    await page.goto(frontendUrl, {waitUntil: 'networkidle'});
    await waitForWorkspace(page);
    await captureFrame(page, 'tour-main-full', {
      selectors: ['.main-dashboard-grid'],
      caption: 'One workspace connects intake, orchestration, evidence, human checkpoints, and the verified outcome.',
      metadata: {page: 'main', region: 'full'},
    });
    await captureFrame(page, 'tour-main-input', {
      selectors: ['[data-demo-target="case-input"]'],
      caption: 'Cases can begin from a prepared scenario or from validated manual input.',
      metadata: {page: 'main', region: 'input'},
    });
    await captureFrame(page, 'tour-main-graph', {
      selectors: ['[data-demo-target="agent-graph"]'],
      caption: 'The graph makes planning, specialist checks, verification, approvals, execution, and replanning visible.',
      metadata: {page: 'main', region: 'graph'},
    });
    await captureFrame(page, 'tour-main-inspector', {
      selectors: ['[data-demo-target="case-overview"]'],
      caption: 'The case overview explains the current situation, material history, and relevant past lessons.',
      metadata: {page: 'main', region: 'inspector'},
    });
    await captureFrame(page, 'tour-main-lower', {
      selectors: ['[data-demo-target="execution-timeline"]', '[data-demo-target="final-response"]'],
      caption: 'The timeline remains readable, while the final response stays gated by verification.',
      metadata: {page: 'main', region: 'lower'},
    });

    await page.locator('[data-demo-target="nav-data"]').click();
    await page.locator('[data-demo-target="data-page"]').waitFor({state: 'visible', timeout: 30000});
    await page.getByText('records', {exact: false}).first().waitFor({state: 'visible', timeout: 30000});
    await page.waitForTimeout(900);
    await captureFrame(page, 'tour-data-full', {
      selectors: ['[data-demo-target="data-page"]'],
      caption: 'Grounded public sources and simulated operational records remain visibly separated.',
      metadata: {page: 'data', region: 'full'},
    });
    await captureFrame(page, 'tour-data-table', {
      selectors: ['[data-demo-target="data-table"]', '[data-demo-target="data-inspector"]'],
      caption: 'Processed records expose useful relationships and provenance without revealing evaluator-only ground truth.',
      metadata: {page: 'data', region: 'records'},
    });

    await page.locator('[data-demo-target="nav-evaluation"]').click();
    await page.locator('[data-demo-target="evaluation-page"]').waitFor({state: 'visible', timeout: 30000});
    await page.getByText('Acceptance gate', {exact: true}).waitFor({state: 'visible', timeout: 30000});
    await page.waitForTimeout(900);
    await captureFrame(page, 'tour-evaluation-full', {
      selectors: ['[data-demo-target="evaluation-page"]'],
      caption: 'Evaluation connects each observed run to explicit outcome and safety criteria.',
      metadata: {page: 'evaluation', region: 'full'},
    });
    await captureFrame(page, 'tour-evaluation-metrics', {
      selectors: ['[data-demo-target="evaluation-metrics"]'],
      caption: 'Completion, consistency, reasoning quality, violations, and latency are measured separately.',
      metadata: {page: 'evaluation', region: 'metrics'},
    });

    await page.locator('[data-demo-target="nav-main"]').click();
    await waitForWorkspace(page);
    for (let family = 1; family <= 7; family += 1) {
      const scenarioId = `S${family}-M01`;
      await page.getByLabel('Scenario', {exact: true}).selectOption(scenarioId);
      await page.waitForTimeout(250);
      await captureFrame(page, `scenario-${family}`, {
        selectors: ['[aria-label="Selected scenario preview"]', '[aria-label="Synthetic student information"]'],
        caption: `S${family} · ${await page.getByLabel('Scenario', {exact: true}).locator('option:checked').innerText()}`,
        metadata: {page: 'main', scenarioId, region: 'scenario-preview'},
      });
    }
  } finally {
    await take.close();
  }
}

function snapshotFromResponse(payload) {
  return payload?.snapshot ?? payload;
}

function latestNode(snapshot) {
  return snapshot.timeline?.at(-1)?.node_id ?? snapshot.current_node ?? null;
}

function nodeAttempt(snapshot, nodeId) {
  return snapshot.node_details?.[nodeId]?.attempt
    ?? snapshot.node_history?.[nodeId]?.at(-1)?.attempt
    ?? snapshot.timeline?.filter((item) => item.node_id === nodeId).at(-1)?.attempt
    ?? 1;
}

async function recordSnapshot(page, scenarioId, snapshot, sequence) {
  const nodeId = latestNode(snapshot) ?? 'intake_context';
  const attempt = nodeAttempt(snapshot, nodeId);
  const status = snapshot.node_statuses?.[nodeId] ?? snapshot.status;
  const id = `${scenarioId.toLowerCase()}-step-${String(sequence).padStart(2, '0')}-${nodeId}-${attempt}`;
  const selectors = [`.react-flow__node[data-id="${nodeId}"]`, '[data-demo-target="node-inspector"]'];
  const node = page.locator(`.react-flow__node[data-id="${nodeId}"]`);
  if (await node.count()) await node.click();
  await page.waitForTimeout(holdMs);
  return captureFrame(page, id, {
    selectors,
    caption: snapshot.node_details?.[nodeId]?.narrative?.summary
      ?? snapshot.timeline?.at(-1)?.label
      ?? nodeId.replaceAll('_', ' '),
    metadata: {
      page: 'main', scenarioId, nodeId, attempt, status,
      runStatus: snapshot.status,
      pauseKind: snapshot.pause?.kind ?? null,
      hasFinalResponse: Boolean(snapshot.final_response),
      sequence,
    },
  });
}

async function waitForStepSettlement(page, initialSnapshot, previousSequence) {
  let snapshot = initialSnapshot;
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    const progressed = snapshot.latest_event_sequence > previousSequence;
    const settled = snapshot.can_advance || ['waiting', 'completed', 'failed'].includes(snapshot.status);
    if (progressed && settled) return snapshot;
    await page.waitForTimeout(500);
    const response = await page.request.get(`${backendUrl}/api/v1/runs/${snapshot.run_id}`);
    if (!response.ok()) throw new Error(`Could not poll run ${snapshot.run_id}.`);
    snapshot = await response.json();
  }
  throw new Error(`Run ${snapshot.run_id} did not settle after a graph step.`);
}

async function clickAndReadResponse(page, button, urlPattern) {
  const responsePromise = page.waitForResponse((response) => (
    response.request().method() === 'POST' && urlPattern.test(new URL(response.url()).pathname)
  ), {timeout: 120000});
  await button.click();
  const response = await responsePromise;
  if (!response.ok()) throw new Error(`Runtime request failed while capturing: ${response.status()} ${response.url()}`);
  return snapshotFromResponse(await response.json());
}

async function captureScenarioRun(browser, scenarioId, takeName) {
  const take = await createTake(browser, takeName);
  const {page} = take;
  const recorded = [];
  try {
    await page.goto(frontendUrl, {waitUntil: 'networkidle'});
    await waitForWorkspace(page);
    await page.getByRole('button', {name: /Demo/}).click();
    await page.getByLabel('Scenario', {exact: true}).selectOption(scenarioId);
    await page.getByRole('button', {name: 'Step-by-step'}).click();
    await page.waitForTimeout(300);
    await captureFrame(page, `${scenarioId.toLowerCase()}-ready`, {
      selectors: ['[data-demo-target="case-input"]', '[data-demo-target="agent-graph"]'],
      caption: `${scenarioId} begins with its simulated student record and case request visible.`,
      metadata: {page: 'main', scenarioId, phase: 'ready'},
    });

    let snapshot = await clickAndReadResponse(
      page,
      page.getByRole('button', {name: 'Start grounded run'}),
      /\/api\/v1\/runs$/,
    );
    snapshot = await waitForStepSettlement(page, snapshot, -1);
    manifest.runs[scenarioId] = {runId: snapshot.run_id, status: snapshot.status};
    let sequence = 0;
    recorded.push(await recordSnapshot(page, scenarioId, snapshot, sequence));

    while (!['completed', 'failed'].includes(snapshot.status)) {
      if (snapshot.status === 'waiting') {
        if (snapshot.pause?.kind !== 'approval') {
          throw new Error(`${scenarioId} paused for unsupported ${snapshot.pause?.kind ?? 'unknown'} input during the scripted demo.`);
        }
        const approvalNode = snapshot.node_details?.human_approval ? 'human_approval' : 'pause_checkpoint';
        await page.locator(`.react-flow__node[data-id="${approvalNode}"]`).click();
        const approveButton = page.getByRole('button', {name: 'Approve', exact: true});
        await approveButton.waitFor({state: 'visible', timeout: 30000});
        const approvalDeadline = Date.now() + 30000;
        while (!(await approveButton.isEnabled()) && Date.now() < approvalDeadline) {
          await page.waitForTimeout(250);
        }
        if (!(await approveButton.isEnabled())) throw new Error(`${scenarioId} approval controls did not become active.`);
        await page.waitForTimeout(350);
        await captureFrame(page, `${scenarioId.toLowerCase()}-approval-decision`, {
          selectors: ['[data-demo-target="node-inspector"]'],
          caption: 'A simulated human reviewer sees the exact request, policy basis, and prepared evidence before deciding.',
          metadata: {page: 'main', scenarioId, nodeId: approvalNode, phase: 'approval-decision'},
        });
        await approveButton.scrollIntoViewIfNeeded();
        await page.waitForTimeout(350);
        await captureFrame(page, `${scenarioId.toLowerCase()}-approval-action`, {
          selectors: ['[data-demo-target="node-inspector"]'],
          caption: 'The simulated approving role explicitly authorises the prepared request; the agent cannot self-approve.',
          metadata: {page: 'main', scenarioId, nodeId: approvalNode, phase: 'approval-action'},
        });
        const previousSequence = snapshot.latest_event_sequence;
        snapshot = await clickAndReadResponse(
          page,
          approveButton,
          /\/api\/v1\/runs\/[^/]+\/resume$/,
        );
        snapshot = await waitForStepSettlement(page, snapshot, previousSequence);
      } else if (snapshot.can_advance) {
        const previousSequence = snapshot.latest_event_sequence;
        snapshot = await clickAndReadResponse(
          page,
          page.getByRole('button', {name: 'Run next graph step'}),
          /\/api\/v1\/runs\/[^/]+\/advance$/,
        );
        snapshot = await waitForStepSettlement(page, snapshot, previousSequence);
      } else {
        await page.waitForTimeout(300);
        const response = await page.request.get(`${backendUrl}/api/v1/runs/${snapshot.run_id}`);
        if (!response.ok()) throw new Error(`Could not poll run ${snapshot.run_id}.`);
        snapshot = await response.json();
      }
      sequence += 1;
      recorded.push(await recordSnapshot(page, scenarioId, snapshot, sequence));
      if (sequence > 50) throw new Error(`${scenarioId} exceeded the 50-step capture safety limit.`);
    }

    await page.waitForTimeout(700);
    await captureFrame(page, `${scenarioId.toLowerCase()}-final-response`, {
      selectors: ['[data-demo-target="final-response"]'],
      caption: snapshot.final_response?.narrative ?? snapshot.final_response?.message ?? `${scenarioId} completed.`,
      metadata: {page: 'main', scenarioId, phase: 'final-response', status: snapshot.status},
    });
    await captureFrame(page, `${scenarioId.toLowerCase()}-completed-route`, {
      selectors: ['[data-demo-target="agent-graph"]'],
      caption: `${scenarioId} preserves the complete observed route, including any repeated node visits.`,
      metadata: {page: 'main', scenarioId, phase: 'completed-route', status: snapshot.status},
    });
    manifest.runs[scenarioId] = {
      ...manifest.runs[scenarioId],
      status: snapshot.status,
      finalHeadline: snapshot.final_response?.headline ?? null,
      capturedSteps: recorded.length,
    };
  } finally {
    await take.close();
  }
}

async function captureEvaluationProof(browser) {
  const take = await createTake(browser, 'evaluation-proof');
  const {page} = take;
  try {
    await page.goto(`${frontendUrl}/evaluation`, {waitUntil: 'networkidle'});
    await page.locator('[data-demo-target="evaluation-page"]').waitFor({state: 'visible', timeout: 30000});
    await page.getByText('Acceptance gate', {exact: true}).waitFor({state: 'visible', timeout: 30000});
    await page.waitForTimeout(900);
    await captureFrame(page, 'proof-evaluation', {
      selectors: ['[data-demo-target="evaluation-page"]'],
      caption: 'Observed runs remain comparable with their expected outcomes and safety gates.',
      metadata: {page: 'evaluation', region: 'proof'},
    });
    await captureFrame(page, 'proof-metrics', {
      selectors: ['[data-demo-target="evaluation-metrics"]'],
      caption: 'The closing evidence reports the current accepted campaign values directly from the application.',
      metadata: {page: 'evaluation', region: 'metrics'},
    });
  } finally {
    await take.close();
  }
}

async function main() {
  await mkdir(captureRoot, {recursive: true});
  await mkdir(rawRoot, {recursive: true});
  if (!cleanCapture) {
    try {
      const existing = JSON.parse(await readFile(path.join(captureRoot, 'manifest.json'), 'utf8'));
      Object.assign(manifest.frames, existing.frames ?? {});
      Object.assign(manifest.rawVideos, existing.rawVideos ?? {});
      for (const [key, value] of Object.entries(manifest.rawVideos)) {
        if (typeof value === 'string') manifest.rawVideos[key] = value.replace('captures/raw/', 'artifacts/raw/');
      }
      Object.assign(manifest.runs, existing.runs ?? {});
    } catch {
      // A partial capture may start without an earlier manifest.
    }
  } else {
    for (const item of await import('node:fs/promises').then(({readdir}) => readdir(captureRoot))) {
      if (item.endsWith('.png')) await rm(path.join(captureRoot, item), {force: true});
    }
  }
  const health = await fetch(`${backendUrl}/api/v1/health`).then((response) => response.json());
  manifest.executionMode = health.execution_mode ?? 'unknown';

  let browser;
  try {
    browser = await chromium.launch({channel: 'chrome', headless: !headed});
  } catch {
    browser = await chromium.launch({headless: !headed});
  }
  try {
    if (takes.has('tour')) await captureTour(browser);
    if (takes.has('s7')) await captureScenarioRun(browser, 'S7-M01', 's7-dynamic-recovery');
    if (takes.has('s2')) await captureScenarioRun(browser, 'S2-M01', 's2-human-approval');
    if (takes.has('proof')) await captureEvaluationProof(browser);
  } finally {
    await browser.close();
  }

  await writeFile(path.join(captureRoot, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  console.log(`Captured ${Object.keys(manifest.frames).length} directed 4K frames.`);
  console.log(`Manifest: ${path.join(captureRoot, 'manifest.json')}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : error);
  process.exitCode = 1;
});
