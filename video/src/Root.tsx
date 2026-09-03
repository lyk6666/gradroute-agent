import {Composition} from 'remotion';
import {SimulationFilm, UI_ONLY_FRAMES} from './SimulationFilm';
import {FPS} from './director.mjs';

export function RemotionRoot() {
  return (
    <>
      <Composition id="SimulationPreview720p" component={SimulationFilm} durationInFrames={UI_ONLY_FRAMES} fps={FPS} width={1280} height={720} />
      <Composition id="SimulationUIOnly4K" component={SimulationFilm} durationInFrames={UI_ONLY_FRAMES} fps={FPS} width={3840} height={2160} />
    </>
  );
}
