#!/usr/bin/env python3
"""Build the portrait reference clip the style catalog renders its samples from.

The committed `reference-portrait.mp4`, `reference-portrait.words.json` and
`reference-portrait.cuts.json` were produced by this script. You do not need to
run it -- it exists so the reference is reproducible, and so you can see that
nothing in this repo is real footage of a real person.

    python3 sample/make_reference.py

Requires ffmpeg and a text-to-speech binary (`say` on macOS). Nothing else: the
backdrop is drawn here in pure Python rather than with Pillow, because this repo
runs on machines with no pip packages on PATH.

WHY IT LOOKS LIKE THIS
----------------------

A style sample exists to answer "what does this style do to my video", and the
three axes a pack is described on are grade, motion and type. A flat slate --
which is what sample-16x9.mp4 is -- answers none of them: a colour grade applied
to two flat greys is invisible, and a punch-in on a static card reads as a
glitch. So the backdrop carries what a grade needs to show itself:

  * a full tonal range, from near-black to near-clipping, so contrast, lift and
    gain have something to move
  * a warm midtone in the upper third where a face would sit, because skin is
    what temperature and saturation are actually judged on
  * specular highlights, which is where a lifted black point becomes obvious
  * gentle grain, so `grade.grain` composites onto something rather than into
    a vacuum

and it is drawn oversized so the clip can pan, giving zoom and punch-in
somewhere to move.

WHY THE WORD TIMINGS ARE EXACT
------------------------------

Every word is synthesised as its own audio file and measured, so the timeline is
known rather than estimated. Whisper never runs; nothing has to be transcribed;
the timings are exact by construction. That matters more here than anywhere else
in the pipeline -- a style is judged on how its caption highlight lands on the
beat, and the character-length estimate this replaces is wrong by up to 11
frames.
"""
from __future__ import annotations

import json
import pathlib
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = pathlib.Path(__file__).resolve().parent

# Oversized on purpose: the clip pans a 1080x1920 window across this, which is
# what gives a punch-in something to punch into.
BACKDROP_W, BACKDROP_H = 1560, 2280
CANVAS_W, CANVAS_H = 1080, 1920
FPS = 30

# Deliberately structured like a real reel: a hook, an answer, a point and a
# payoff, so the cut plan below has genuine structural joins for a style's
# transitions to punctuate.
SCRIPT = [
    ("hook", "Every edit takes hours."),
    ("answer", "The talking part took ninety seconds."),
    ("point", "The machine should do the rest."),
    ("payoff", "That is the whole idea."),
]

# A short gap between words reads as speech rather than a list, and a longer one
# between lines gives the mechanical pass a silence to find.
WORD_GAP = 0.06
LINE_GAP = 0.34


def clamp(value: float) -> int:
    return 0 if value < 0 else (255 if value > 255 else int(value))


def backdrop() -> bytes:
    """A PNG with a full tonal range and a warm subject where a face would be."""
    w, h = BACKDROP_W, BACKDROP_H
    rows = bytearray()
    # A cheap deterministic noise source. Grain has to be in the SOURCE, not
    # added later, or `grade.grain` has nothing to sit on and every style's
    # texture looks identical.
    seed = 0x2F6E2B1
    for y in range(h):
        rows.append(0)
        v = y / h
        # Sky: cool and bright at the top, falling to a deep shadow at the
        # bottom. Near-black at the base is what makes crushed blacks visible.
        sky_r = 116 - 96 * v
        sky_g = 138 - 116 * v
        sky_b = 162 - 132 * v
        row = bytearray()
        for x in range(w):
            u = x / w
            r, g, b = sky_r, sky_g, sky_b
            # A soft horizontal warm wash, so temperature has a gradient to
            # shift rather than a single flat field.
            warm = max(0.0, 1.0 - abs(u - 0.62) * 2.4)
            r += 46 * warm * (1.0 - v)
            g += 22 * warm * (1.0 - v)

            # The subject: head and shoulders, upper third, skin midtone. The
            # shading is a single soft key from the left, which is enough for a
            # grade's temperature and saturation to read on a face.
            dx = (x - w * 0.48) / (w * 0.135)
            dy = (y - h * 0.34) / (h * 0.082)
            head = dx * dx + dy * dy
            sx = (x - w * 0.48) / (w * 0.36)
            sy = (y - h * 0.74) / (h * 0.28)
            shoulders = sx * sx + sy * sy
            if head < 1.0 or (shoulders < 1.0 and y > h * 0.42):
                key = 0.62 + 0.38 * max(0.0, 1.0 - ((x - w * 0.42) / (w * 0.34)) ** 2)
                depth = 1.0 - 0.35 * min(1.0, head if head < 1.0 else shoulders)
                r = 206 * key * depth
                g = 158 * key * depth
                b = 132 * key * depth

            # Two speculars. A lifted black point is hard to see; a blown
            # highlight rolling off is not.
            for hx, hy, hr, power in ((0.24, 0.14, 0.10, 210.0), (0.80, 0.47, 0.055, 160.0)):
                d = ((x - w * hx) / (w * hr)) ** 2 + ((y - h * hy) / (h * hr * 0.58)) ** 2
                if d < 1.0:
                    fall = (1.0 - d) ** 2
                    r += power * fall
                    g += power * fall
                    b += power * fall * 0.94

            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            grain = ((seed >> 16) & 0xFF) / 255.0 * 9.0 - 4.5
            row += bytes((clamp(r + grain), clamp(g + grain), clamp(b + grain)))
        rows += row

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + chunk(b"IEND", b""))


def speak(text: str, out: pathlib.Path) -> float:
    """One word, synthesised and measured. Returns its duration in seconds."""
    aiff = out.with_suffix(".aiff")
    # No --data-format: this macOS build rejects it ("Opening output file
    # failed: fmt?") and writes a zero-byte file while still exiting 0, so the
    # failure would surface later as an unreadable clip rather than here.
    subprocess.run(["say", "-o", str(aiff), text], check=True)
    if aiff.stat().st_size == 0:
        raise RuntimeError(f"say produced an empty file for {text!r}")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(aiff),
                    "-ar", "48000", "-ac", "1", str(out)], check=True)
    probed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(out)],
        check=True, capture_output=True, text=True)
    return float(probed.stdout.strip())


def main() -> int:
    if not HERE.exists():
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)

        print("drawing the backdrop...")
        (tmpdir / "backdrop.png").write_bytes(backdrop())

        print("synthesising, one word at a time...")
        words: list[dict] = []
        lines: list[dict] = []
        # (file, silence after it). The gap is carried alongside the piece so the
        # concatenated audio and the word timings are built from one list rather
        # than two that have to agree -- they did not, the first time, and every
        # caption drifted a third of a second late per line.
        pieces: list[tuple[pathlib.Path, float]] = []
        cursor = 0.0
        for beat, sentence in SCRIPT:
            line_start = cursor
            spoken = sentence.split()
            for index, word in enumerate(spoken):
                piece = tmpdir / f"w{len(words):03d}.wav"
                duration = speak(word, piece)
                gap = WORD_GAP if index < len(spoken) - 1 else LINE_GAP
                pieces.append((piece, gap))
                words.append({"word": word,
                              "start": round(cursor, 3),
                              "end": round(cursor + duration, 3)})
                cursor += duration + gap
            lines.append({"beat": beat,
                          "start": round(line_start, 3),
                          "end": round(words[-1]["end"], 3)})

        total = round(cursor, 3)
        print(f"  {len(words)} words, {total:.2f}s")

        # Concatenate with silence between, so the measured word times above are
        # the times in the finished file rather than an approximation of them.
        parts, filters = [], []
        for index, (piece, gap) in enumerate(pieces):
            parts += ["-i", str(piece)]
            # The last word keeps its gap too: the reel ends on a beat rather
            # than cutting on the final consonant.
            filters.append(f"[{index}:a]apad=pad_dur={gap}[a{index}]")
        concat = "".join(f"[a{i}]" for i in range(len(pieces)))
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *parts, "-filter_complex",
             ";".join(filters) + f";{concat}concat=n={len(pieces)}:v=0:a=1[out]",
             "-map", "[out]", str(tmpdir / "voice.wav")], check=True)

        print("panning the backdrop...")
        # A slow diagonal drift. Motion is what makes a punch-in read as an edit
        # rather than as a jump, and it costs nothing here.
        travel_x = BACKDROP_W - CANVAS_W
        travel_y = BACKDROP_H - CANVAS_H
        crop = (f"crop={CANVAS_W}:{CANVAS_H}:"
                f"'{travel_x}*(0.18+0.64*t/{total})':'{travel_y}*(0.30+0.44*t/{total})'")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-loop", "1", "-framerate", str(FPS), "-t", f"{total}",
             "-i", str(tmpdir / "backdrop.png"),
             "-i", str(tmpdir / "voice.wav"),
             "-vf", f"{crop},format=yuv420p",
             "-c:v", "libx264", "-preset", "slow", "-crf", "20",
             "-c:a", "aac", "-b:a", "128k", "-shortest",
             str(HERE / "reference-portrait.mp4")], check=True)

    (HERE / "reference-portrait.words.json").write_text(
        json.dumps({"words": words}, indent=2) + "\n")

    # A pre-baked cut plan, so a sample render skips whisper and the editorial
    # pass entirely. Every segment is structural: the reference has no silence
    # worth trimming, and a mechanical join would leave a style's transitions
    # with nothing to punctuate.
    (HERE / "reference-portrait.cuts.json").write_text(json.dumps({
        "version": 2,
        "slug": "__style_sample__",
        "fps": FPS,
        "headline": "the edit is not the hard part",
        "pad": [0.05, 0.05],
        "loudness": {"i": -14, "tp": -1.5, "lra": 11},
        "takes": {"A": {"path": "sample/reference-portrait.mp4",
                        "words": "sample/reference-portrait.words.json"}},
        "segments": [
            {"take": "A", "start": line["start"], "end": line["end"],
             "beat": line["beat"], "kind": "structural",
             "reason": "the reference is one line per beat, by construction"}
            for line in lines
        ],
    }, indent=2) + "\n")

    size = (HERE / "reference-portrait.mp4").stat().st_size
    print(f"\nreference-portrait.mp4  {size / 1024:.0f} KB  {total:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
