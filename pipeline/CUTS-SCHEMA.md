# `cuts.json` — the contract

Everything upstream of this file is judgement. Everything downstream is FFmpeg.

`cuts.json` is the only place where a decision about the video lives. `plan.py` writes a
draft of it, you or an agent edit it, and `assemble.py` executes it without opinions. It
is designed to be **read and edited by hand** — if you need a tool to change a cut, the
format has failed.

---

## Shape

```jsonc
{
  "version": 1,
  "slug": "sample",                    // names the output folder: build/<slug>/
  "fps": 30,
  "headline": "the line that stays on screen",   // used by render/, not by the cut

  "pad": [0.06, 0.06],                 // seconds added before/after every segment
  "loudness": { "i": -14, "tp": -1.5, "lra": 11 },

  "takes": {
    "A": {
      "path": "media/take-a.mp4",
      "words": "build/sample/A.words.json"      // optional; needed for captions
    },
    "B": { "path": "media/take-b.mp4" }
  },

  "segments": [
    {
      "take": "A",
      "start": 22.14,
      "end": 27.80,
      "beat": "hook",
      "kind": "structural",
      "reason": "opens on the question; recorded at 0:22, moved to 0:00"
    },
    {
      "take": "A",
      "start": 3.02,
      "end": 11.65,
      "beat": "build",
      "kind": "mechanical"
    }
  ]
}
```

## Fields

| Field | Required | Meaning |
|-------|----------|---------|
| `version` | yes | Always `1`. Bumped only for a breaking change. |
| `slug` | yes | Output folder name. `[a-z0-9-]` — it becomes a path. |
| `fps` | no (30) | Output frame rate. Every segment is normalised to it. |
| `headline` | no | The persistent line in the reel's top bar. Ignored by `assemble.py`. |
| `pad` | no (`[0.06, 0.06]`) | Seconds of word-boundary padding on each side of every segment. Whisper's word boundaries land slightly inside the phoneme; without padding, joins clip consonants. 60–80ms is the working range. |
| `loudness` | no | Target for the final `loudnorm` pass. `i` is integrated LUFS, `tp` true peak, `lra` loudness range. |
| `takes` | yes | Map of take id → source. Ids are yours; single-take jobs conventionally use `"A"`. |
| `takes[].path` | yes | Path to the media, relative to the repo root or absolute. |
| `takes[].words` | no | Word-timestamp JSON from `transcribe.py`. Without it you get a cut but no captions. |
| `segments` | yes | Ordered. **The order in this array is the order in the cut** — it is not sorted by timestamp, because moving the hook to 0:00 is the entire point. |
| `segments[].take` | yes | Key into `takes`. |
| `segments[].start` / `.end` | yes | Seconds in the **source** take, before padding. |
| `segments[].beat` | no | Free-text label: `hook`, `build`, `conflict`, `payoff`, `cta`, `close`. Shows up in the assemble log and the verify report. |
| `segments[].kind` | no (`mechanical`) | `structural` or `mechanical`. |
| `segments[].reason` | **yes if `structural`** | One line, tied to the focus. `assemble.py` refuses to run if a structural segment has no reason. |

## Why `reason` is enforced

A structural cut is a claim about the video: *this belongs here, that doesn't*. The rule
from `agent/knowledge/01-METHOD.md` is that every structural cut carries a reason and
mechanical cuts are batch-listed. Enforcing it in the schema means the reasoning survives
into the next session, instead of living in a chat log nobody reads again.

Mechanical segments — silence trims, flub removals — don't need one. They were generated
by a rule, and the rule is the reason.

## What `plan.py` writes and what it doesn't

`plan.py` reads a words file, detects silences, and emits a draft where every segment is
`"kind": "mechanical"`. It performs two of the five cut passes:

- **(b) flub removal** — near-duplicate sentence starts, keeping the last attempt
- **(c) the silence pass** — gaps ≥ `--min-silence` at thought boundaries, holding back the beat before a payoff

It cannot perform the other three, and does not pretend to:

- **(a) best take per beat** — needs a judgement about energy
- **(d) tangent trims** — needs to know what the focus is
- **(e) hook surgery** — needs to know what the hook is

Those are yours. Make them by reordering and editing `segments`, marking each one
`structural`, and writing the reason.

## Editing it by hand

The three edits you will make most:

**Move the hook to the front** — cut the segment out of the array, paste it first, mark it structural:

```jsonc
{ "take": "A", "start": 22.14, "end": 27.80, "beat": "hook",
  "kind": "structural", "reason": "the actual question; everything before it was wind-up" }
```

**Drop a tangent** — delete the segment, and record the deletion on the neighbour so the reasoning isn't lost:

```jsonc
{ "take": "A", "start": 40.10, "end": 52.66, "beat": "point-2",
  "kind": "structural", "reason": "the pricing digression at 0:36-0:40 was cut — it serves a different focus" }
```

**Splice a better take in** — change `take`, keep the beat:

```jsonc
{ "take": "B", "start": 4.90, "end": 9.30, "beat": "payoff",
  "kind": "structural", "reason": "take B's payoff has the laugh; take A's is flat" }
```

## Guarantees

- Segments are extracted with a re-encode, never `-c copy`. Stream copy snaps to keyframes and drifts off word boundaries.
- Every segment is normalised to the same resolution, fps, and pixel format before concat.
- Every output is `yuv420p`.
- `assemble.py` writes `build/<slug>/cuts.resolved.json` next to the cut: the same plan with padding applied, measured segment durations, and the offset of each segment in the final timeline. That file is what `verify.py` checks against, so a passing verify means the plan and the file agree.
