import {Audio} from '@remotion/media';
import {useEffect, useState} from 'react';
import {AbsoluteFill, OffthreadVideo, Sequence, cancelRender, continueRender, delayRender, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import edit from '../script/simulation-edit.json';
import {buildTimeline, cameraFor, moveCamera, validateTake, type Camera, type Clip, type Shot, type Take} from './director.mjs';
import './styles.css';

export const TIMELINE = buildTimeline(edit);
export const UI_ONLY_FRAMES = TIMELINE.reduce((sum, shot) => sum + shot.duration, 0);

function RecordedMoment({clip, shot, source, footage, fromCamera}: {
  clip: Clip; shot: Shot; source: Take['viewport']; footage: string; fromCamera: Camera;
}) {
  const frame = useCurrentFrame();
  const {width, fps} = useVideoConfig();
  const initialCamera = cameraFor(clip.target, source);
  const interacting = Boolean(clip.interaction && frame >= clip.interaction.at * fps);
  const camera = interacting && clip.interaction
    ? moveCamera(initialCamera, cameraFor(clip.interaction.target, source), frame - clip.interaction.at * fps, fps)
    : moveCamera(fromCamera, initialCamera, frame, fps);
  const ratio = width / source.width;
  const highlight = interacting && clip.interaction ? clip.interaction.highlight : clip.highlight;
  const highlightOpacity = shot.speech ? interpolate(frame, [16, 28, shot.seconds * fps - 12, shot.seconds * fps - 1], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 0;
  const color = shot.focus === 'approval' ? '#e58a00' : '#2769e8';
  return (
    <AbsoluteFill className="ui-only-moment">
      <OffthreadVideo
        src={staticFile(footage)}
        trimBefore={Math.round(clip.sourceStart * fps)}
        muted
        style={{position: 'absolute', width: source.width, height: source.height, maxWidth: 'none', transformOrigin: '0 0', transform: `translate(${camera.x * ratio}px, ${camera.y * ratio}px) scale(${camera.scale * ratio})`}}
      />
      <div className="spoken-region" style={{
        opacity: highlightOpacity,
        left: (highlight.x * camera.scale + camera.x) * ratio - 3,
        top: (highlight.y * camera.scale + camera.y) * ratio - 3,
        width: highlight.width * camera.scale * ratio + 6,
        height: highlight.height * camera.scale * ratio + 6,
        borderColor: color,
      }} />
      {shot.speech ? <Audio src={staticFile(`audio/${shot.id}.mp3`)} volume={1} /> : null}
    </AbsoluteFill>
  );
}

export function SimulationFilm() {
  const [take, setTake] = useState<Take | null>(null);
  const [handle] = useState(() => delayRender('Loading actual continuous browser footage'));
  useEffect(() => {
    let active = true;
    fetch(staticFile('captures/simulation-take.json'))
      .then((response) => {
        if (!response.ok) throw new Error('Run npm run capture before rendering the UI-only film.');
        return response.json();
      })
      .then((value) => {
        const checked = validateTake(edit, value);
        if (active) { setTake(checked); continueRender(handle); }
      })
      .catch((error) => cancelRender(error));
    return () => { active = false; };
  }, [handle]);
  if (!take) return null;
  return (
    <AbsoluteFill className="ui-only-film">
      {TIMELINE.map((shot, index) => {
        const previous = index ? take.shots[TIMELINE[index - 1].id] : null;
        return (
          <Sequence key={shot.id} name={shot.id} from={shot.start} durationInFrames={shot.duration}>
            <RecordedMoment shot={shot} clip={take.shots[shot.id]} footage={take.footage} source={take.viewport} fromCamera={previous ? cameraFor(previous.interaction?.target ?? previous.target, take.viewport) : {x: 0, y: 0, scale: 1}} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
}
