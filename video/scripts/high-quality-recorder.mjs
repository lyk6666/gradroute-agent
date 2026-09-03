import {spawn} from 'node:child_process';

/** Lossless browser PNG frames, encoded once at high quality on a fixed video clock. */
export async function startHighQualityRecording(page, ffmpeg, destination) {
  const fps = 25;
  const session = await page.context().newCDPSession(page);
  const encoder = spawn(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-vcodec', 'png', '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '12', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-y', destination], {windowsHide: true, stdio: ['pipe', 'ignore', 'pipe']});
  let diagnostics = '';
  let fault = null;
  let latest = null;
  let frames = 0;
  let startedAt = 0;
  let width = 0;
  let height = 0;
  let resolveReady;
  const ready = new Promise((resolve) => { resolveReady = resolve; });
  encoder.stderr.on('data', (chunk) => { diagnostics = (diagnostics + chunk.toString()).slice(-6000); });
  encoder.stdin.on('error', (error) => { fault = error; });
  const closed = new Promise((resolve) => {
    encoder.once('close', resolve);
    encoder.once('error', (error) => { fault = error; resolve(-1); });
  });
  function flush() {
    if (!latest || fault) return;
    const required = Math.floor((Date.now() - startedAt) / 1000 * fps) + 1;
    while (frames < required) {
      if (encoder.stdin.writableLength > 192 * 1024 * 1024) {
        fault = new Error('The high-quality recorder cannot keep up; refusing a desynchronised take.');
        return;
      }
      encoder.stdin.write(latest);
      frames += 1;
    }
  }
  session.on('Page.screencastFrame', (event) => {
    flush();
    latest = Buffer.from(event.data, 'base64');
    if (!startedAt) {
      startedAt = Date.now();
      width = latest.readUInt32BE(16);
      height = latest.readUInt32BE(20);
      resolveReady();
    }
    session.send('Page.screencastFrameAck', {sessionId: event.sessionId}).catch((error) => { fault = error; });
  });
  await session.send('Page.startScreencast', {format: 'png', maxWidth: 3840, maxHeight: 2160, everyNthFrame: 1});
  let timer;
  try {
    await Promise.race([ready, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('No browser recording frame arrived.')), 15000); })]);
  } catch (error) {
    encoder.stdin.end();
    await session.detach();
    throw error;
  } finally { clearTimeout(timer); }
  const interval = setInterval(flush, 20);
  return {
    viewport: {width, height},
    startedAt,
    elapsed() {
      if (fault) throw new Error(`${fault.message}\n${diagnostics}`);
      return (Date.now() - startedAt) / 1000;
    },
    async stop() {
      await session.send('Page.stopScreencast');
      clearInterval(interval);
      flush();
      encoder.stdin.end();
      const code = await closed;
      await session.detach();
      if (code !== 0 || fault) throw new Error(`High-quality recording failed (${code}): ${fault?.message ?? diagnostics}`);
      return {frames, fps, seconds: frames / fps};
    },
  };
}
