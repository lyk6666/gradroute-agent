import {existsSync} from 'node:fs';
import {Config} from '@remotion/cli/config';

const systemChrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

if (existsSync(systemChrome)) {
  Config.setBrowserExecutable(systemChrome);
}

Config.setDelayRenderTimeoutInMilliseconds(120_000);
Config.setVideoImageFormat('jpeg');
Config.setColorSpace('bt709');
Config.setAudioBitrate('320k');
Config.setSampleRate(48_000);
