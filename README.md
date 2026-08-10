# landscape-on-black

## What this is

This is a small end-to-end talking-head reel system: transcribe footage, plan a cut, assemble it, render a 9:16 reel, review it on a phone, and approve it before promotion. The finished frame is black with a 16:9 clip band across the middle at 31.7% of the height, a persistent headline above it, and lowercase karaoke captions on the lower third of the video band.

## The five-minute quickstart

```bash
git clone <repo-url>
cd landscape-on-black
cd render && npm install
cd ..
make quickstart
open out/sample-reel.mp4
```

Prerequisites are `ffmpeg`, `python3`, and Node 18 or newer. The only setup step for the renderer is `cd render && npm install`. On the first render, Remotion downloads a headless Chrome, so the first run takes longer than later runs.

`make quickstart` uses the committed `sample/cuts.json` and does not need a transcription backend.

## The worked example

`sample/sample-16x9.mp4` is 31.333 seconds of deliberately badly structured narration. The hook starts at about 0:06 behind wind-up. A restart begins around 0:18 and the later attempt resolves at about 0:22. `sample/cuts.json` moves the hook to 0:00, drops the wind-up, keeps the later attempt, and lands at about 17 seconds.

The assembled run produced these values:

| Measurement | Result |
| --- | ---: |
| Planned duration | 17.604s |
| Cut duration | 17.610s |
| Loudness measurement | -14.55 LUFS |
| Pixel format | yuv420p |
| Reel dimensions | 1080x1920 |

The five kept segments were 4.687s, 5.721s, 4.088s, 2.154s, and 0.954s after word-boundary padding. The verification report records the optional join check as skipped because the available transcription package could not access its model in the build environment.

## Bring your own footage

Transcribe the footage:

```bash
python3 pipeline/transcribe.py media/take-a.mp4 -o build/take-a.words.json
```

Draft the mechanical passes:

```bash
python3 pipeline/plan.py build/take-a.words.json -o build/take-a.cuts.draft.json --media media/take-a.mp4
```

Edit `cuts.json` by hand. It is the decision file: put the best take per beat, tangent trims, hook surgery, and structural reasons there.

Assemble and stage the cut:

```bash
python3 pipeline/assemble.py build/take-a.cuts.json
```

Render and verify:

```bash
cd render
npx remotion render src/index.ts LandscapeOnBlack ../out/take-a-reel.mp4 --props=public/reels/take-a/props.json
cd ..
python3 pipeline/verify.py build/take-a/cut.mp4
```

## What's in here

| Directory | Purpose |
| --- | --- |
| `agent/` | Editing method, craft references, execution protocol, and quality bar. |
| `pipeline/` | Transcription, mechanical planning, FFmpeg assembly, captions, and verification. |
| `render/` | Standalone Remotion composition for the landscape-on-black reel. |
| `cutout/` | Apple-Silicon `mlx-sam` greenscreen segmentation and compositing path. |
| `review/` | Static phone review page, publishing, decision collection, and approval gate. |

## The method

The editing method is documented in `agent/AGENT.md` and the linked knowledge files. `pipeline/CUTS-SCHEMA.md` is the contract between editorial judgement and deterministic assembly.

## Requirements

Install the optional transcription, cutout, and publishing dependencies from the commented lines in `pipeline/requirements.txt`. The core plan, assembly, verification, review build, collection, and finalize scripts use Python's standard library plus `ffmpeg` and `ffprobe`.

## Licence

MIT. See `LICENSE`.

## Credits

The editing method and source references are listed in `CREDITS.md`.
