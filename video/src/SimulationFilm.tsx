import {Audio} from '@remotion/media';
import {useEffect, useMemo, useState} from 'react';
import {
  AbsoluteFill,
  Img,
  Sequence,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {OUTPUT_HEIGHT, OUTPUT_WIDTH, STORYBOARD, type DirectedShot, type FrameQuery} from './storyboard';
import './styles.css';

type CaptureRect = {x: number; y: number; width: number; height: number};
type CaptureFrame = {
  id: string;
  file: string;
  target: CaptureRect;
  caption: string;
  metadata: Record<string, unknown>;
};
type CaptureManifest = {
  schemaVersion: number;
  capturedAt: string | null;
  viewport: {width: number; height: number};
  executionMode: string;
  source?: {disclosure?: string};
  frames: Record<string, CaptureFrame>;
};

const accents = {
  blue: '#2f6fec',
  green: '#009b72',
  amber: '#e58a00',
  red: '#dc3d4b',
  purple: '#8554e8',
};

function matchesQuery(frame: CaptureFrame, query: FrameQuery) {
  return Object.entries(query).every(([key, value]) => frame.metadata[key] === value);
}

function resolveFrame(manifest: CaptureManifest, shot: DirectedShot) {
  if (shot.frameId && manifest.frames[shot.frameId]) return manifest.frames[shot.frameId];
  if (shot.query) {
    const candidates = Object.values(manifest.frames)
      .filter((frame) => matchesQuery(frame, shot.query!))
      .sort((first, second) => Number(first.metadata.sequence ?? 0) - Number(second.metadata.sequence ?? 0));
    if (candidates.length) return candidates.at(-1)!;
    const relaxed = Object.values(manifest.frames).find((frame) => (
      (!shot.query?.scenarioId || frame.metadata.scenarioId === shot.query.scenarioId)
      && (!shot.query?.nodeId || frame.metadata.nodeId === shot.query.nodeId)
    ));
    if (relaxed) return relaxed;
  }
  return manifest.frames['tour-main-full'] ?? Object.values(manifest.frames)[0] ?? null;
}

function cameraFor(target: CaptureRect, source: CaptureManifest['viewport'], full: boolean) {
  if (full) return {scale: 1, x: 0, y: 0};
  const padding = 150;
  const scale = Math.max(1, Math.min(
    2.35,
    OUTPUT_WIDTH / Math.max(1, target.width + padding * 2),
    OUTPUT_HEIGHT / Math.max(1, target.height + padding * 2),
  ));
  const targetCenterX = target.x + target.width / 2;
  const targetCenterY = target.y + target.height / 2;
  const x = OUTPUT_WIDTH / 2 - targetCenterX * scale;
  const y = OUTPUT_HEIGHT / 2 - targetCenterY * scale;
  const sourceWidth = source.width * scale;
  const sourceHeight = source.height * scale;
  return {
    scale,
    x: Math.min(0, Math.max(OUTPUT_WIDTH - sourceWidth, x)),
    y: Math.min(0, Math.max(OUTPUT_HEIGHT - sourceHeight, y)),
  };
}

function MissingCapture({id}: {id: string}) {
  return (
    <AbsoluteFill className="missing-capture">
      <strong>Capture required</strong>
      <span>{id}</span>
      <small>Run the automated capture pipeline before rendering.</small>
    </AbsoluteFill>
  );
}

function ApprovalPulse({color}: {color: string}) {
  const frame = useCurrentFrame();
  const progress = spring({frame: Math.max(0, frame - 100), fps: 30, config: {damping: 12, stiffness: 100}});
  return (
    <div className="approval-pulse" style={{borderColor: color, opacity: interpolate(progress, [0, 1], [0, 0.9]), transform: `translateX(-50%) scale(${interpolate(progress, [0, 1], [0.65, 1.2])})`}}>
      <i style={{backgroundColor: color}} />
      <span>Simulated human approval</span>
    </div>
  );
}

function DirectedFrame({capture, shot, chapter, durationInFrames, source}: {
  capture: CaptureFrame | null;
  shot: DirectedShot;
  chapter: string;
  durationInFrames: number;
  source: CaptureManifest['viewport'];
}) {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (!capture) return <MissingCapture id={shot.frameId ?? shot.id} />;
  const targetCamera = cameraFor(capture.target, source, shot.focus === 'full');
  const settle = spring({frame, fps, config: {damping: 24, stiffness: 65, mass: 1.1}, durationInFrames: Math.min(38, durationInFrames)});
  const scale = interpolate(settle, [0, 1], [Math.max(1, targetCamera.scale * 0.94), targetCamera.scale]);
  const centerX = OUTPUT_WIDTH / 2 - (OUTPUT_WIDTH / 2 - targetCamera.x) * (scale / targetCamera.scale);
  const centerY = OUTPUT_HEIGHT / 2 - (OUTPUT_HEIGHT / 2 - targetCamera.y) * (scale / targetCamera.scale);
  const fade = interpolate(frame, [0, 10, durationInFrames - 9, durationInFrames - 1], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const accent = accents[shot.accent ?? 'blue'];

  return (
    <AbsoluteFill className="shot" style={{opacity: fade}}>
      <Img
        className="capture-image"
        src={staticFile(capture.file)}
        style={{
          width: source.width,
          height: source.height,
          transform: `translate3d(${centerX}px, ${centerY}px, 0) scale(${scale})`,
          transformOrigin: 'top left',
        }}
      />
      <div className="film-vignette" />
      <div className="chapter-chip"><i style={{background: accent}} />{chapter}</div>
      <div className="capture-badge"><i />REAL SYSTEM RUN</div>
      <div className="caption-card" style={{borderColor: accent}}>
        <span>{shot.caption}</span>
      </div>
      {shot.approvalClick ? <ApprovalPulse color={accent} /> : null}
    </AbsoluteFill>
  );
}

function useCaptureManifest() {
  const [manifest, setManifest] = useState<CaptureManifest | null>(null);
  const [handle] = useState(() => delayRender('Loading directed system capture'));
  useEffect(() => {
    let active = true;
    fetch(staticFile('captures/manifest.json'))
      .then((response) => {
        if (!response.ok) throw new Error(`Capture manifest returned ${response.status}`);
        return response.json() as Promise<CaptureManifest>;
      })
      .then((value) => {
        if (!Object.keys(value.frames).length) throw new Error('Capture manifest is empty. Run npm run capture first.');
        if (active) {
          setManifest(value);
          continueRender(handle);
        }
      })
      .catch((error) => {
        console.error(error);
        continueRender(handle);
      });
    return () => { active = false; };
  }, [handle]);
  return manifest;
}

export function SimulationFilm() {
  const manifest = useCaptureManifest();
  const timeline = useMemo(() => {
    let cursor = 0;
    return STORYBOARD.map((scene) => {
      const sceneStart = cursor;
      const shots = scene.shots.map((shot) => {
        const start = cursor;
        const duration = Math.round(shot.seconds * 30);
        cursor += duration;
        return {shot, start, duration};
      });
      return {scene, sceneStart, duration: cursor - sceneStart, shots};
    });
  }, []);

  if (!manifest) return <MissingCapture id="manifest" />;

  return (
    <AbsoluteFill className="film-root">
      {timeline.map(({scene, sceneStart, duration}) => (
        <Sequence key={scene.id} from={sceneStart} durationInFrames={duration} name={scene.chapter}>
          <Audio src={staticFile(scene.audioFile)} volume={0.96} />
        </Sequence>
      ))}
      {timeline.flatMap(({scene, shots}) => shots.map(({shot, start, duration}) => (
        <Sequence key={shot.id} from={start} durationInFrames={duration} name={shot.id}>
          <DirectedFrame
            capture={resolveFrame(manifest, shot)}
            shot={shot}
            chapter={scene.chapter}
            durationInFrames={duration}
            source={manifest.viewport}
          />
        </Sequence>
      )))}
      <div className="film-disclosure">{manifest.source?.disclosure ?? 'Grounded public sources · simulated operational data'}</div>
    </AbsoluteFill>
  );
}
