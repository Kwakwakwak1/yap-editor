#!/usr/bin/env python3
"""Per-10ms loudness for a take, and what the cut planner does with it.

**Whisper never transcribes um or uh.** That is why #26 survived so long: the
pipeline looked for fillers in a transcript that structurally cannot contain
them, and `plan.py::FILLERS` is four typed phrases for the same reason. A filler
is not a word problem. It is a region of the audio that has energy in it and no
words on top of it.

    python3 pipeline/energy.py media/take1/A.mov --out build/take1/A.energy.json

Two consumers, one artifact:

- the cut planner, here -- snapping boundaries and finding fillers
- music ducking, later, which needs the same envelope and must not measure it a
  second time and disagree

STDLIB AND FFMPEG ONLY
----------------------

Same constraint as the rest of the pipeline: minik has no pip packages on PATH.
The envelope comes from ffmpeg's `astats` with a 10ms frame, parsed out of its
metadata print, which is the one way to get per-frame RMS without numpy.

VALIDATED AGAINST REAL AUDIO
----------------------------

The unit tests use synthetic envelopes so the suite needs no ffmpeg, which
means they cannot catch a filter chain that measures nothing. Both halves were
checked against the committed reference clip instead:

    clean reference          floor -72.4 dBFS   0 filler regions
    same clip, "um" spliced  floor -70.0 dBFS   1 filler region, 2.10-2.37s,
    into the gap at 2.10s                       79% of the gap voiced

The clean run is the one that matters most. An earlier version of this reported
three fillers in that take -- a clip of synthesised speech with true digital
silence between the lines -- because the floor was anchored to the quietest
frame. See `_split`.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import write_json  # noqa: E402

#: 10ms. Fine enough to find the edge of a breath, coarse enough that a 60
#: second take is 6000 numbers rather than a megabyte of them.
FRAME_MS = 10

#: A boundary may move this far to find a quieter place to cut. Beyond it the
#: cut stops being the one the editor chose.
SNAP_WINDOW_MS = 120

#: A gap in the words shorter than this is the space between two words, not a
#: pause anybody put anything in.
MIN_GAP_MS = 180

_RMS = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(-?\d+(?:\.\d+)?|-inf)")


#: The filter chain has to say all three of these things, and the first version
#: of this said none of them:
#:
#:   asetnsamples  astats' `reset` counts FRAMES, not seconds, and an audio
#:                 frame is whatever the decoder felt like -- typically 1024
#:                 samples. Fixing the frame size is the only way to get a
#:                 known interval.
#:   metadata=1    computes the per-frame stats at all
#:   ametadata     PRINTS them. Without it astats sets metadata nobody reads
#:                 and the output is empty, which is exactly what happened:
#:                 zero frames measured, no error, from an 11-second clip.
#:
#: `file=-` sends them to stdout, so that is where they are parsed from.
SAMPLE_RATE = 48000


def measure(media: Path, frame_ms: int = FRAME_MS) -> List[float]:
    """Per-frame RMS in dBFS. Silence is -120, not -inf, so arithmetic works."""
    samples = max(1, int(SAMPLE_RATE * frame_ms / 1000))
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(media),
            "-ar", str(SAMPLE_RATE),
            "-af",
            f"asetnsamples=n={samples},astats=metadata=1:reset=1,"
            f"ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-",
            "-f", "null", "-",
        ],
        check=False, capture_output=True, text=True,
    )
    levels: List[float] = []
    for match in _RMS.finditer(proc.stdout):
        raw = match.group(1)
        levels.append(-120.0 if raw == "-inf" else float(raw))
    return levels


def _split(levels: Sequence[float]) -> float:
    """The dividing line between "silence" and "sound", found in the data.

    Two clusters, Lloyd's algorithm, k=2. Deliberately not a fixed offset below
    the speech level and deliberately not anchored to the quietest frame,
    because those two fail on opposite recordings:

    - **Anchored to the minimum**, digital silence wrecks it. An AAC-encoded
      gap reads -201 dBFS, and a floor ten percent up from there lands at -184,
      below every real sound in the file -- so every silent gap counts as
      voiced. That is not hypothetical: it is what the first version of this
      did to the reference clip, reporting three fillers in a take that has
      none.
    - **A fixed offset below speech** fails the other way. Speech at -25 with
      room tone at -55 needs a floor between them; subtract a constant 35 and
      the room counts as speech.

    Two clusters find the gap wherever it actually is.
    """
    ordered = sorted(levels)
    if len(ordered) < 4:
        return ordered[0] if ordered else -120.0

    low = ordered[len(ordered) // 10]
    high = ordered[-max(1, len(ordered) // 10)]
    for _ in range(12):
        middle = (low + high) / 2
        below = [level for level in ordered if level <= middle]
        above = [level for level in ordered if level > middle]
        if not below or not above:
            break
        new_low = sum(below) / len(below)
        new_high = sum(above) / len(above)
        if abs(new_low - low) < 0.01 and abs(new_high - high) < 0.01:
            low, high = new_low, new_high
            break
        low, high = new_low, new_high
    return (low + high) / 2


def envelope(levels: Sequence[float], frame_ms: int = FRAME_MS) -> Dict[str, Any]:
    """The document written to `<take>.energy.json`.

    `speech` is the median of the frames above the floor -- a median rather
    than a mean because one door slam should not redefine how loud somebody
    talks.
    """
    if not levels:
        return {"version": 1, "frame_ms": frame_ms, "levels": [], "speech": -120.0,
                "floor": -120.0}

    floor = _split(levels)
    voiced = sorted(level for level in levels if level >= floor)
    speech = voiced[len(voiced) // 2] if voiced else max(levels)

    return {
        "version": 1,
        "frame_ms": frame_ms,
        "levels": [round(level, 1) for level in levels],
        "speech": round(speech, 1),
        "floor": round(floor, 1),
    }


def _frame(seconds: float, frame_ms: int) -> int:
    return int(seconds * 1000 / frame_ms)


def snap(boundary: float, env: Dict[str, Any], window_ms: int = SNAP_WINDOW_MS) -> float:
    """Move a cut to the quietest moment near it.

    Cutting on a word boundary cuts mid-breath: whisper's timestamps mark where
    a WORD starts, and a speaker is already inhaling before that. Cutting at the
    local energy minimum sounds like an edit somebody made on purpose.

    Never moves further than the window, and returns the boundary unchanged when
    there is no envelope to consult -- a take with no measurement gets the cut
    the editor asked for, not a guess.
    """
    levels = env.get("levels") or []
    if not levels:
        return boundary

    frame_ms = env.get("frame_ms", FRAME_MS)
    centre = _frame(boundary, frame_ms)
    reach = max(1, window_ms // frame_ms)
    start, end = max(0, centre - reach), min(len(levels), centre + reach + 1)
    if start >= end:
        return boundary

    window = levels[start:end]
    quietest = min(range(len(window)), key=lambda i: (window[i], abs(start + i - centre)))
    return round((start + quietest) * frame_ms / 1000, 3)


def word_gaps(words: Sequence[Dict[str, Any]], min_gap_ms: int = MIN_GAP_MS) -> List[Tuple[float, float]]:
    """Spans between consecutive words long enough to hold something."""
    gaps: List[Tuple[float, float]] = []
    for earlier, later in zip(words, words[1:]):
        try:
            gap_start, gap_end = float(earlier["end"]), float(later["start"])
        except (KeyError, TypeError, ValueError):
            continue
        if (gap_end - gap_start) * 1000 >= min_gap_ms:
            gaps.append((gap_start, gap_end))
    return gaps


def fillers(
    words: Sequence[Dict[str, Any]],
    env: Dict[str, Any],
    min_gap_ms: int = MIN_GAP_MS,
) -> List[Dict[str, Any]]:
    """Voiced regions sitting in a gap the transcript says is empty.

    That is what an "um" is, mechanically: whisper heard no word, and there is
    audio energy there anyway. A gap with no energy in it is a pause, which is
    a different thing and is left alone -- pauses carry meaning and cutting them
    all is how an edit starts sounding like a machine made it.
    """
    levels = env.get("levels") or []
    if not levels:
        return []

    frame_ms = env.get("frame_ms", FRAME_MS)
    floor = env.get("floor", -120.0)
    found: List[Dict[str, Any]] = []

    for gap_start, gap_end in word_gaps(words, min_gap_ms):
        first, last = _frame(gap_start, frame_ms), _frame(gap_end, frame_ms)
        window = levels[first:last]
        if not window:
            continue

        voiced = [index for index, level in enumerate(window) if level >= floor]
        if not voiced:
            continue  # a genuine pause

        # The voiced run inside the gap, plus nothing either side of it: the
        # words themselves are outside this window by construction.
        run_start = (first + voiced[0]) * frame_ms / 1000
        run_end = (first + voiced[-1] + 1) * frame_ms / 1000
        if (run_end - run_start) * 1000 < 60:
            continue  # a click, a chair, a breath -- not a syllable

        found.append({
            "from": round(run_start, 3),
            "to": round(run_end, 3),
            "gap": [round(gap_start, 3), round(gap_end, 3)],
            # How much of the silent gap turned out not to be silent. A high
            # ratio is an "um"; a low one is a breath before a sentence.
            "voiced_ratio": round(len(voiced) / len(window), 3),
        })
    return found


#: A piece of a segment shorter than this is not worth keeping: it is a frame
#: or two of audio either side of a filler, and splicing it back in reads as a
#: stutter rather than as continuity.
MIN_PIECE_MS = 120


def remove(
    segments: Sequence[Dict[str, Any]], found: Sequence[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], int]:
    """Cut fillers out of a segment list. Returns `(segments, removed)`.

    A filler in a GAP between segments is already out of the cut and is not
    counted -- reporting it would claim work that was not done, which is worse
    than doing nothing, because it is the operator's only signal that the pass
    is working. That is exactly what the first version of this did: it narrowed
    boundaries the silence pass had already placed, announced "1 filler region
    cut", and left an "um" sitting in the middle of a segment untouched.

    A filler INSIDE a segment splits it in two. That is the case worth having:
    "so um yeah" has no pause around the um for the silence pass to find, which
    is why the um survives every other mechanical pass in this file.
    """
    out: List[Dict[str, Any]] = []
    removed = 0

    for segment in segments:
        pieces = [dict(segment)]
        for filler in found:
            start, end = float(filler["from"]), float(filler["to"])
            next_pieces: List[Dict[str, Any]] = []
            for piece in pieces:
                if end <= piece["start"] or start >= piece["end"]:
                    next_pieces.append(piece)
                    continue

                removed += 1
                head = dict(piece, end=round(min(start, piece["end"]), 3))
                tail = dict(piece, start=round(max(end, piece["start"]), 3))
                for candidate in (head, tail):
                    if (candidate["end"] - candidate["start"]) * 1000 >= MIN_PIECE_MS:
                        next_pieces.append(candidate)
            pieces = next_pieces
        out.extend(pieces)

    return out, removed


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--words", type=Path, help="whisper output, to list fillers")
    parser.add_argument("--frame-ms", type=int, default=FRAME_MS)
    args = parser.parse_args(argv)

    levels = measure(args.media, args.frame_ms)
    if not levels:
        print("no audio measured; is there an audio stream?", file=sys.stderr)
        return 1

    env = envelope(levels, args.frame_ms)
    seconds = len(levels) * args.frame_ms / 1000
    print(f"{len(levels)} frames ({seconds:.1f}s), "
          f"speech {env['speech']:.1f} dBFS, floor {env['floor']:.1f} dBFS")

    if args.words:
        data = json.loads(args.words.read_text(encoding="utf-8"))
        words = data.get("words", data) if isinstance(data, dict) else data
        found = fillers(words, env)
        print(f"{len(found)} filler region(s):")
        for item in found:
            print(f"  {item['from']:7.2f}-{item['to']:6.2f}s  "
                  f"{(item['to'] - item['from']) * 1000:4.0f}ms  "
                  f"voiced {item['voiced_ratio'] * 100:3.0f}% of the gap")

    if args.out:
        write_json(args.out, env)
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
