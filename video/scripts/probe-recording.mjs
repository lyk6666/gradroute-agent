import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
import {startHighQualityRecording} from './high-quality-recorder.mjs';

await mkdir('artifacts/recorder-probe', {recursive: true});
const browser = await chromium.launch({channel: 'chrome'});
try {
  const page = await browser.newPage({viewport: {width: 1920, height: 1080}, deviceScaleFactor: 2});
  const recording = await startHighQualityRecording(page, 'node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe', 'artifacts/recorder-probe/source.mp4');
  await page.setContent('<div style="font:14px Segoe UI;padding:40px"><h1>Recording fidelity check</h1><p>Policy, prerequisite evidence and course availability remain legible.</p><button>Approve</button></div>');
  await page.waitForTimeout(1500);
  await page.getByRole('button').click();
  await page.waitForTimeout(1500);
  console.log(JSON.stringify({viewport: recording.viewport, ...await recording.stop()}));
} finally { await browser.close(); }
