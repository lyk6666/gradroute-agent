"""Generate replaceable scene narration with a natural Singapore-English voice."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import edge_tts


VIDEO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = VIDEO_ROOT / "script" / "simulation-edit.json"
AUDIO_ROOT = VIDEO_ROOT / "public" / "audio"


async def generate(voice: str, force: bool, script_path: Path) -> None:
    entries = json.loads(script_path.read_text(encoding="utf-8"))
    AUDIO_ROOT.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        text = entry.get("speech", entry.get("text"))
        if not text:
            continue
        destination = AUDIO_ROOT / f"{entry['id']}.mp3"
        if destination.exists() and not force:
            continue
        rate = int(entry.get("rate", 0))
        communicator = edge_tts.Communicate(
            text=str(text),
            voice=voice,
            rate=f"{rate:+d}%",
        )
        await communicator.save(str(destination))
        print(f"Generated {destination.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", default="en-SG-LunaNeural")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--script", type=Path, default=SCRIPT_PATH)
    args = parser.parse_args()
    asyncio.run(generate(args.voice, args.force, args.script))


if __name__ == "__main__":
    main()
