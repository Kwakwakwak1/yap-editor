# Credits

The code here is mine. The judgement encoded in `agent/` is not — it is distilled
from people who published how they work. Where a rule in `agent/knowledge/` came
from one of them, it carries their tag.

## The editing method (`agent/`)

| Tag | Source | Where the video is | What it contributed |
|-----|--------|--------------------|---------------------|
| **OREN** | *The Art of Yapping (full guide to talking on video)* — orenmeetsworld | `youtube.com/watch?v=CS0A4hJfcy4` | The format taxonomy (standard / walking / car / graphic), the five content frameworks, the script frameworks (Hook-Story-P1-P2, the 8 Mile, the Four Things), re-recording the intro at the end of a session, the ~2s graphic cadence. The primary playbook. |
| **SARAEV** | *How I automated my YouTube channel in 24 mins* — Nick Saraev | `youtube.com/watch?v=S3kdxriOESk` | The automated cut pipeline: silence removal at a 0.5s threshold, spoken mistake-markers for retakes, hardware-accelerated encoding, and the "directives, not scripts" architecture this repo's `pipeline/` follows. |
| **HOYOS** | *The Secret to Telling a Great Story in Less Than 60 Seconds* — Jenny Hoyos (TED) | `youtube.com/watch?v=ZmNpeXTj2c4` | The sub-60s story spine: question hook, constant progression, conflict before the answer, uncertain answer, fast payoff. The rule that you cut flatness, never conflict. |
| **VINH** | *In 7 Minutes, You'll Be 170% Better At Presentations* — Vinh Giang | `youtube.com/watch?v=Sh-se-i0afA` | The engagement-device palette and the discipline of using one or two of them rather than all of them. |
| **JAKE** | *Yapping Full Guide: How to yap properly* — Jake YuJune | `youtube.com/watch?v=Xlym0eOVu9I` | The flow-state criterion for what a good take sounds like — no resistance between the thought and the mouth — which is why takes here are ranked by flow rather than cleanliness. |

Roughly 23,000 words across five videos. That is a small corpus, so every rule in
`agent/knowledge/` is cited per source and the thin evidence stays visible. None of
those transcripts are redistributed here; only the distilled rules are.

## The cutout path (`cutout/`)

- **SAM 2.1** — Meta FAIR's promptable video segmentation model, and the published
  description of how Instagram Edits' Cutouts works
  (`ai.meta.com/blog/instagram-edits-cutouts-segment-anything/`). The click-to-keep,
  approve-the-seed, propagate-both-directions flow here is modelled on it.
- **`sam2-mlx`** by avbiswas — the Apple Silicon port this repo drives, with the
  `sam2.1-hiera-small-mlx` checkpoint on Hugging Face.

## The layout (`render/`)

The 9:16-black-with-a-centred-16:9-band composition was reverse-engineered from a
reference reel by **@kairubok** (`instagram.com/reels/DafvbrBT7hH/`) by measuring its
frames — the 31.7% video band, the persistent headline above it, the lowercase
captions on the lower third. No footage, audio, or artwork from it is in this repo.

## Fonts

DM Sans, by Colophon Foundry and Jonny Pinhorn, under the SIL Open Font License 1.1.
The licence ships alongside the font in `render/public/fonts/`.

## Tools

FFmpeg, Remotion, Whisper, and the Python scientific stack do the actual work. This
repo is mostly a set of opinions about how to point them at footage.
