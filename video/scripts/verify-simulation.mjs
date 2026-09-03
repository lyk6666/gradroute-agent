import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {validateTake} from '../src/director.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const edit = JSON.parse(await readFile(path.join(root, 'script/simulation-edit.json'), 'utf8'));
const take = validateTake(edit, JSON.parse(await readFile(path.join(root, 'public/captures/simulation-take.json'), 'utf8')));
const probe = path.join(root, 'node_modules/@remotion/compositor-win32-x64-msvc/ffprobe.exe');
const metadata = (file) => JSON.parse(execFileSync(probe, ['-v', 'error', '-show_entries', 'format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels', '-of', 'json', file], {encoding: 'utf8'}));
const source = metadata(path.join(root, 'public', take.footage));
const sourceVideo = source.streams.find((stream) => stream.codec_type === 'video');
if (!sourceVideo || sourceVideo.codec_name !== 'h264' || sourceVideo.width !== 1920 || sourceVideo.height !== 1080 || sourceVideo.r_frame_rate !== '25/1') throw new Error('The take is not the expected high-quality 1080p/25 H.264 source.');
let previousStart = -1;
for (const shot of edit) {
  const clip = take.shots[shot.id];
  if (clip.sourceStart <= previousStart) throw new Error(`Non-chronological clip: ${shot.id}`);
  if (clip.sourceStart + shot.seconds > Number(source.format.duration)) throw new Error(`Clip exceeds source: ${shot.id}`);
  previousStart = clip.sourceStart;
  if (shot.speech) {
    const duration = Number(metadata(path.join(root, 'public/audio', `${shot.id}.mp3`)).format.duration);
    if (duration > shot.seconds - 0.05) throw new Error(`Narration spills beyond ${shot.id}: ${duration}s > ${shot.seconds}s`);
    console.log(`${shot.id}: ${duration.toFixed(2)}s narration / ${shot.seconds}s shot`);
  }
}
const movieArg = process.argv.find((arg) => arg.startsWith('--movie='));
if (movieArg) {
  const movie = metadata(path.resolve(root, movieArg.slice('--movie='.length)));
  const video = movie.streams.find((stream) => stream.codec_type === 'video');
  const audio = movie.streams.find((stream) => stream.codec_type === 'audio');
  if (!video || !audio || Math.abs(Number(movie.format.duration) - 115) > 0.15) throw new Error('Rendered movie is missing a stream or has the wrong duration.');
  console.log(JSON.stringify(movie, null, 2));
}
console.log(`Verified ${edit.length} actual clips, complete S7/S2 outcomes, and all narration boundaries.`);
