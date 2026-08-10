# CUT CRAFT — the tool workflow

The deterministic layer (SARAEV's architecture). This file is the directive; the scripts
in `pipeline/` are its implementation. If you change a rule here, change the script, and
vice versa — a directive that has drifted from its script is worse than no directive.

Paths below are relative to the repo root.

## Transcription — word timestamps are the cut points

```bash
python3 pipeline/transcribe.py media/take-a.mp4 -o build/take-a.words.json
```

Three backends, auto-detected in this order and overridable with `--backend` or
`TRANSCRIBE_BACKEND`:

| Backend | Install | Notes |
|---------|---------|-------|
| `mlx` | `pip install mlx-whisper` | Apple Silicon only. Fastest by a wide margin. |
| `faster` | `pip install faster-whisper` | CTranslate2, CPU or CUDA. The portable default. |
| `openai` | `pip install openai-whisper` | Reference implementation. Slowest. |

All three are asked for `word_timestamps=True` and normalised into the same JSON shape,
so nothing downstream knows or cares which one ran.

Segment-level timestamps are not a substitute. Cutting on segment boundaries clips words.

## Silence and flub detection

```bash
ffmpeg -i media/take-a.mp4 -af silencedetect=noise=-35dB:d=0.5 -f null - 2>&1 | grep silence_
```

- Cross-check `silencedetect` against the whisper word gaps. Trust the **word timestamps for where to cut** and `silencedetect` for **what is cuttable**.
- A noise floor of −35dB is the general-purpose default. For close-mic'd indoor audio, −25dB catches breaths and mouth noise that sit below −35dB and would otherwise survive the cut as audible artefacts at a join. `plan.py --noise -25dB` when the room is quiet.
- **Flub and retake detection:** normalised near-duplicate sentence starts, within a take or across takes, are a restart. Keep the **last** attempt — the speaker restarted for a reason, and later means warmed up. If the speaker uses a spoken mistake-marker convention, honour it: cut from the marker back to the start of the flubbed passage.
- **The pause rule:** cut pauses ≥0.5s at thought boundaries; keep the beat before a payoff or a punchline, capped at about 0.4s.

## Cutting and assembly — frame accurate

```bash
# per keep-segment: re-encode. NEVER -c copy — stream copy snaps to keyframes and
# drifts off word boundaries, which clips words at every join.
ffmpeg -ss 12.340 -to 18.920 -i media/take-a.mp4 \
  -c:v libx264 -preset veryfast -crf 18 -c:a aac -b:a 192k \
  -pix_fmt yuv420p -avoid_negative_ts make_zero build/seg_001.mp4

# concat segments that share resolution, fps, and pixel format
printf "file 'seg_%03d.mp4'\n" 1 2 3 > build/list.txt
ffmpeg -f concat -safe 0 -i build/list.txt -c copy build/rough.mp4

# loudness normalise for social; one pass is acceptable for talking-head audio
ffmpeg -i build/rough.mp4 -c:v copy -af loudnorm=I=-14:TP=-1.5:LRA=11 \
  -pix_fmt yuv420p build/cut.mp4
```

`assemble.py` runs exactly this. Notes that matter:

- **Hardware encoders are a legitimate swap** for the per-segment pass: `h264_videotoolbox` on macOS, `h264_nvenc` on NVIDIA. `assemble.py --encoder` takes them. Fall back to `libx264 -crf 18` the moment you see artefacts.
- **Word-boundary padding:** extend every keep by 60–80ms on each side of the whisper word boundary. Never cut mid-phoneme.
- **All segments must share resolution, fps, and pixel format before concat.** Normalise at extraction if the takes differ — this is the single most common cause of a concat that produces a 3-second file.
- Every output is `yuv420p`. Anything else fails to decode on some phone, somewhere, silently.

## Audio enhancement (optional)

Location audio — wind, ocean, street, a room with a fridge in it — benefits from a
levelling and denoise pass after the cut is assembled, remuxed back in without touching
the video:

```bash
ffmpeg -i build/cut.mp4 -i build/cut-enhanced.flac \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart build/cut-enhanced.mp4
```

Two ways to get that FLAC:

- **Local, free, no account:** `ffmpeg -af "highpass=f=80,afftdn=nf=-25,dynaudnorm=f=200:g=5"`. Good enough for most rooms.
- **A hosted service** (Auphonic and friends) when the location audio is genuinely bad. Extract lossless first (`-vn -c:a flac -ar 48000`) and upload the **audio only**, never the video — it's faster and it's cheaper. One production per cut, then remux into every variant of that cut, because all variants share a timeline.

Whichever you use: verify afterwards that the duration is unchanged within 0.05s, that
loudness is −14 ±1, and that **the re-transcription still matches**. Aggressive denoise
eats words, and it eats them quietly.

Credentials for any hosted service go in `.env`. Never hardcode a key, and never put one
in a script, a prompt, or a commit.

## Captions and overlays

- Emit captions from the kept words, regrouped to short lines and synced to the **cut's** timeline. `assemble.py` writes both `captions.srt` (for anything that eats SRT) and `captions.json` (`{from, to, text}` — what `render/` consumes).
- The renderer lowercases captions on screen; keep them sentence-case in the file so the SRT stays useful elsewhere.
- Graphic yap: emit `overlays.json` as `{t, duration, suggestion}` at roughly a 2s cadence. The agent plans; it does not fabricate brand assets.

## Verification — non-negotiable before handoff

1. `ffprobe` the final duration: it equals the sum of the planned keeps within 0.5s.
2. **Re-transcribe the output** and diff against the planned keep-text. Zero dropped or doubled words at joins.
3. Loudness: `ffmpeg -i build/cut.mp4 -af loudnorm=print_format=json -f null -` → `input_i` within −14 ±1 LUFS.
4. Look at the first and last 3 seconds and one random join. No black frames, no drift.

`verify.py` runs 1, 3, and 4 unconditionally and 2 when a transcription backend is
installed. When it can't run a check it prints `SKIPPED` and says why. Quote it as
skipped; do not round it up to a pass.
