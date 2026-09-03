export const FPS = 30;

export function buildTimeline(edit) {
  let cursor = 0;
  return edit.map((shot) => {
    const duration = Math.round(shot.seconds * FPS);
    const result = {...shot, start: cursor, duration};
    cursor += duration;
    return result;
  });
}

export function validateTake(edit, take) {
  if (take.schemaVersion !== 2 || !take.footage || !take.shots) throw new Error('A continuous simulation take is required.');
  for (const shot of edit) {
    const clip = take.shots[shot.id];
    if (!clip) throw new Error(`Missing actual footage for ${shot.id}`);
    if (clip.scenarioId !== shot.scenarioId || clip.nodeId !== (shot.nodeId ?? null) || clip.attempt !== (shot.attempt ?? null)) throw new Error(`Observed node/visit mismatch for ${shot.id}`);
    if (!Number.isFinite(clip.sourceStart) || clip.sourceStart < 0 || clip.sourceEnd - clip.sourceStart < shot.seconds - 0.08) throw new Error(`Insufficient recorded duration for ${shot.id}`);
    for (const key of ['target', 'highlight']) {
      const box = clip[key];
      if (!box || ![box.x, box.y, box.width, box.height].every(Number.isFinite) || box.width <= 0 || box.height <= 0) throw new Error(`Invalid ${key} for ${shot.id}`);
    }
    if (shot.phase === 'ready') {
      if (!clip.interaction || !Number.isFinite(clip.interaction.at) || clip.interaction.at <= 0 || clip.interaction.at >= shot.seconds) throw new Error(`Missing visible start interaction for ${shot.id}`);
      for (const key of ['target', 'highlight']) {
        const box = clip.interaction[key];
        if (!box || ![box.x, box.y, box.width, box.height].every(Number.isFinite) || box.width <= 0 || box.height <= 0) throw new Error(`Invalid start-button ${key} for ${shot.id}`);
      }
    }
  }
  if (take.runs?.['S7-M01']?.status !== 'completed' || take.runs?.['S2-M01']?.status !== 'completed' || !take.runs?.['S2-M01']?.approvalPerformed) throw new Error('Both cases must finish, with explicit simulated S2 approval.');
  return take;
}

export function cameraFor(target, source) {
  // Capture bounds already include context padding; do not pad twice and shrink text.
  const scale = Math.max(1, Math.min(3.15, source.width / target.width, source.height / target.height));
  return {
    scale,
    x: Math.min(0, Math.max(source.width * (1 - scale), source.width / 2 - (target.x + target.width / 2) * scale)),
    y: Math.min(0, Math.max(source.height * (1 - scale), source.height / 2 - (target.y + target.height / 2) * scale)),
  };
}

export function moveCamera(from, to, frame, fps = FPS) {
  const progress = Math.min(1, Math.max(0, frame / (fps * 0.85)));
  const eased = progress * progress * (3 - 2 * progress);
  return Object.fromEntries(['x', 'y', 'scale'].map((key) => [key, from[key] + (to[key] - from[key]) * eased]));
}
