import {Composition} from 'remotion';
import {SimulationFilm} from './SimulationFilm';
import {FPS, OUTPUT_HEIGHT, OUTPUT_WIDTH, TOTAL_FRAMES} from './storyboard';

export function RemotionRoot() {
  return (
    <Composition
      id="SimulationDemo4K"
      component={SimulationFilm}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={OUTPUT_WIDTH}
      height={OUTPUT_HEIGHT}
    />
  );
}
