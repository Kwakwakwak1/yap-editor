# Yap → Edits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn an approved yap `cuts.json` into numbered, frame-accurate ProRes clips plus a `plan.json`, and give Claude a skill that builds an Instagram Edits project from them, one clip per beat, with captions corrected against yap's transcript.

**Architecture:** A new stdlib-only pipeline script, `pipeline/edits_export.py`, reuses `assemble.py`'s validation, padding and correction rules, and adds orientation, HDR and loudness handling for per-clip output. A new skill in the dotfiles repo, `yap-to-edits`, drives the Edits MCP tools. Its testable parts (folder check, caption alignment) live in a stdlib helper script. Both run on the Mac that runs Edits.

**Tech Stack:** Python 3.9-compatible stdlib (`from __future__ import annotations`), ffmpeg/ffprobe 8.x, `unittest`. The Edits MCP (`plugin:insta-edits:edits`) is used by the skill only.

**Spec:** `docs/superpowers/specs/2026-11-19-yap-to-edits-design.md`

## Global Constraints

- The pipeline is stdlib + ffmpeg. No third-party imports in `pipeline/` or the skill helper. It must run on Python 3.9 (minik's interpreter), so use `from __future__ import annotations`, `typing` generics, and no `match` statements.
- Tests use `unittest` and run with `python3 -m unittest discover -s tests` from the repo root. Test media is generated with ffmpeg at a tiny size.
- Clips are ProRes 422 (standard): `-c:v prores_ks -profile:v 2`, `-pix_fmt yuv422p10le`, PCM `pcm_s16le` 48 kHz. Frame rate is the plan's `fps`.
- Output size is 1080×1920 for a portrait source and 1920×1080 for a landscape source. Orientation comes from the display rotation, never from raw width and height.
- Padding is per segment, clamped only to the take's duration, the same as `assemble.py`: `max(0, start - pad[0])` and `min(duration, end + pad[1])`.
- File names are `NN-<beat>.mov`, where NN is the 1-based position in `segments` (two digits), and the beat is slugged to `[a-z0-9-]`, falling back to `segment`. Segments are never sorted.
- Loudness: one shared gain for every clip, from the integrated loudness of all kept windows concatenated. Target `plan.loudness.i` (default -14), true-peak ceiling `plan.loudness.tp` (default -1.5).
- HDR (`color_transfer` of `arib-std-b67` or `smpte2084`) must be converted to BT.709 and verified, or the export refuses. Never pass HDR through silently.
- Disk: refuse unless free space ≥ 3 × the estimate (seconds × 147 Mbit/s ÷ 8).
- Output is written to a temp directory beside `--out` and renamed into place only on success. A failure leaves no partial folder.
- Commit messages end with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01HNdA8AwzmwVChsPHLmmi5y`
- Repos: Tasks 1–3 are in `~/Developer/yap-editor-edits` (branch `spec/yap-to-edits`). Task 4 is in `~/dotfiles` on a new branch, `feature/yap-to-edits-skill`.

## File structure

| File | Responsibility |
|---|---|
| `pipeline/common.py` (modify) | `framing_from_probe`, `source_framing`, `video_transfer`, `is_hdr_transfer` |
| `pipeline/edits_export.py` (create) | Pure planning functions, the ffmpeg command builders, the CLI |
| `tests/test_source_probe.py` (create) | Orientation and HDR probes |
| `tests/test_edits_plan_math.py` (create) | Pure functions: names, windows, words, disk |
| `tests/test_edits_export.py` (create) | ffmpeg integration: clips, gain, HDR, failures |
| `~/dotfiles/claude/skills/yap-to-edits/SKILL.md` (create) | The build procedure |
| `~/dotfiles/claude/skills/yap-to-edits/scripts/edits_plan.py` (create) | `check` and `align` |
| `~/dotfiles/claude/skills/yap-to-edits/scripts/test_edits_plan.py` (create) | Tests for the helper |

---

### Task 1: Orientation and HDR probes in `common.py`

**Files:**
- Modify: `pipeline/common.py` (append after `video_pixel_format`)
- Test: `tests/test_source_probe.py`

**Interfaces:**
- Produces: `framing_from_probe(probe: dict) -> str` (`"portrait"` or `"landscape"`; raises `ValueError` if there's no video stream or no width/height)
- Produces: `source_framing(path: Path) -> str`
- Produces: `video_transfer(path: Path) -> str` (the first video stream's `color_transfer`, or `""`)
- Produces: `is_hdr_transfer(transfer: str) -> bool` (true for `arib-std-b67` and `smpte2084`)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_source_probe.py`:

```python
"""Orientation and dynamic range of a source take.

Phones store portrait video as 3840x2160 with rotation=-90 in the stream's side
data, so width and height alone report landscape for portrait footage. The
2026-11-19 take is exactly that. Getting it wrong frames the whole reel wrong.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from common import framing_from_probe, is_hdr_transfer, source_framing, video_transfer  # noqa: E402


def probe(width, height, rotation=None, codec_type="video"):
    stream = {"codec_type": codec_type, "width": width, "height": height}
    if rotation is not None:
        stream["side_data_list"] = [{"rotation": rotation}]
    return {"streams": [{"codec_type": "audio"}, stream]}


class FramingFromProbeTest(unittest.TestCase):
    def test_rotated_landscape_storage_is_portrait(self):
        self.assertEqual(framing_from_probe(probe(3840, 2160, -90)), "portrait")
        self.assertEqual(framing_from_probe(probe(3840, 2160, 90)), "portrait")
        self.assertEqual(framing_from_probe(probe(3840, 2160, 270)), "portrait")

    def test_unrotated_and_upside_down_keep_their_axes(self):
        self.assertEqual(framing_from_probe(probe(1920, 1080)), "landscape")
        self.assertEqual(framing_from_probe(probe(1920, 1080, 180)), "landscape")
        self.assertEqual(framing_from_probe(probe(1080, 1920)), "portrait")

    def test_no_video_stream_is_an_error(self):
        with self.assertRaises(ValueError):
            framing_from_probe({"streams": [{"codec_type": "audio"}]})


class HdrTransferTest(unittest.TestCase):
    def test_hlg_and_pq_are_hdr(self):
        self.assertTrue(is_hdr_transfer("arib-std-b67"))
        self.assertTrue(is_hdr_transfer("smpte2084"))

    def test_sdr_and_unknown_are_not(self):
        for value in ("bt709", "", "unknown", "smpte170m"):
            self.assertFalse(is_hdr_transfer(value), value)


class OnRealFilesTest(unittest.TestCase):
    """The ffprobe wiring, on files ffmpeg makes. The implementer must find the
    ffmpeg 8 flags that tag rotation and HLG; record them in a comment here."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, name, extra_args):
        out = self.dir / name
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=0.5:s=64x36:r=30",
             *extra_args, str(out)],
            check=True,
        )
        return out

    def test_a_rotated_file_reads_as_portrait(self):
        plain = self.make("plain.mp4", ["-c:v", "libx264"])
        rotated = self.dir / "rotated.mp4"
        # Tag a -90 display rotation without re-encoding. The flag spelling
        # changed across ffmpeg versions: use whichever this ffmpeg accepts,
        # e.g. `-display_rotation:v:0 90` as an input option before -i.
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-display_rotation:v:0", "90", "-i", str(plain),
             "-c", "copy", str(rotated)],
            check=True,
        )
        self.assertEqual(source_framing(plain), "landscape")
        self.assertEqual(source_framing(rotated), "portrait")

    def test_transfer_is_read_from_the_stream(self):
        sdr = self.make("sdr.mp4", ["-c:v", "libx264", "-color_trc", "bt709"])
        self.assertEqual(video_transfer(sdr), "bt709")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_source_probe -v`
Expected: FAIL with `ImportError: cannot import name 'framing_from_probe'`.

- [ ] **Step 3: Implement**

Append to `pipeline/common.py`:

```python
HDR_TRANSFERS = ("arib-std-b67", "smpte2084")


def framing_from_probe(probe: Dict[str, Any]) -> str:
    """The source footage's orientation, "portrait" or "landscape".

    Not from width and height alone: phone footage stores 3840x2160 with a
    rotation of +/-90 in the stream's side data. Ported from the yap-editor
    skill's render_worker.framing so pipeline scripts can use it.
    """
    for stream in probe.get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        try:
            width = int(stream["width"])
            height = int(stream["height"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("video stream missing width or height") from None
        rotation = 0
        for side_data in stream.get("side_data_list", []) or []:
            if "rotation" in side_data:
                rotation = int(side_data["rotation"])
                break
        if abs(rotation) % 180 == 90:
            width, height = height, width
        return "portrait" if height > width else "landscape"
    raise ValueError("probe contains no video stream")


def source_framing(path: Path) -> str:
    return framing_from_probe(
        ffprobe_json(path, "stream=codec_type,width,height:stream_side_data=rotation")
    )


def video_transfer(path: Path) -> str:
    data = ffprobe_json(path, "stream=codec_type,color_transfer")
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return str(stream.get("color_transfer", "") or "")
    return ""


def is_hdr_transfer(transfer: str) -> bool:
    return transfer in HDR_TRANSFERS
```

If `ffprobe_json` with that entries string doesn't return `side_data_list` on this ffprobe, adjust the entries string (for example `stream=codec_type,width,height:stream_side_data_list`), not the logic. Keep the probe's JSON shape as the test fixtures assume.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_source_probe -v`
Expected: all PASS. Then run the whole suite: `python3 -m unittest discover -s tests`. All tests must pass. Record the count.

- [ ] **Step 5: Mutation check**

Delete the line `width, height = height, width`. `test_rotated_landscape_storage_is_portrait` and `test_a_rotated_file_reads_as_portrait` must FAIL. Restore it.

- [ ] **Step 6: Commit**

```bash
git add pipeline/common.py tests/test_source_probe.py
git commit -m "Read a take's orientation and dynamic range in the pipeline"
```

---

### Task 2: Pure planning functions in `edits_export.py`

**Files:**
- Create: `pipeline/edits_export.py`
- Test: `tests/test_edits_plan_math.py`

**Interfaces:**
- Consumes: nothing from Task 1 yet.
- Produces (all in `pipeline/edits_export.py`):
  - `clip_name(index: int, beat: Any) -> str`. `index` is 1-based. Example: `clip_name(1, "Hook!")` gives `"01-hook.mov"`; `clip_name(12, "")` gives `"12-segment.mov"`.
  - `clip_windows(segments: list, pad: tuple, take_durations: dict) -> list[dict]`. Each window is `{"take", "source_start", "source_end", "clip_start", "clip_end", "duration"}`, where `duration` is `clip_end - clip_start`. Raises `ValueError` if a padded window is empty.
  - `clip_words(words: list, clip_start: float, clip_end: float) -> list[dict]`. It takes `{start, end, word}` items and returns `{from, to, text}`, shifted by `-clip_start`. It keeps a word if its midpoint falls in `[clip_start, clip_end)`, and rounds to 3 decimals.
  - `estimate_bytes(total_seconds: float) -> int`, which is `int(total_seconds * 147_000_000 / 8)`.
  - `check_disk(path: Path, needed_bytes: int, free_bytes: int | None = None) -> None`. It raises `RuntimeError` if `free < 3 * needed`. `free_bytes` lets tests inject a value; otherwise it uses `shutil.disk_usage(path).free`.
  - `MBIT_PER_SECOND = 147`, `DISK_FACTOR = 3`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_edits_plan_math.py`:

```python
"""The arithmetic of cutting an approved plan into Edits clips.

These are the decisions a reviewer can check without ffmpeg: which file a beat
becomes, where its padded window falls, which words belong to it, and whether
there is room on disk.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from edits_export import (  # noqa: E402
    DISK_FACTOR,
    check_disk,
    clip_name,
    clip_windows,
    clip_words,
    estimate_bytes,
)


def seg(take, start, end, beat="b"):
    return {"take": take, "start": start, "end": end, "beat": beat}


class ClipNameTest(unittest.TestCase):
    def test_position_and_slugged_beat(self):
        self.assertEqual(clip_name(1, "hook"), "01-hook.mov")
        self.assertEqual(clip_name(2, "Point 2: the price!"), "02-point-2-the-price.mov")
        self.assertEqual(clip_name(12, ""), "12-segment.mov")
        self.assertEqual(clip_name(3, None), "03-segment.mov")


class ClipWindowsTest(unittest.TestCase):
    def test_padding_is_per_segment_and_order_is_kept(self):
        windows = clip_windows(
            [seg("B", 2.10, 6.60, "hook"), seg("A", 1.00, 2.00)],
            (0.07, 0.07), {"A": 30.0, "B": 30.0},
        )
        self.assertEqual([w["take"] for w in windows], ["B", "A"])
        self.assertAlmostEqual(windows[0]["clip_start"], 2.03)
        self.assertAlmostEqual(windows[0]["clip_end"], 6.67)
        self.assertAlmostEqual(windows[0]["duration"], 4.64)
        self.assertEqual(windows[0]["source_start"], 2.10)

    def test_padding_is_clamped_to_the_take(self):
        windows = clip_windows([seg("A", 0.02, 9.98)], (0.07, 0.07), {"A": 10.0})
        self.assertEqual(windows[0]["clip_start"], 0.0)
        self.assertEqual(windows[0]["clip_end"], 10.0)

    def test_an_empty_window_is_an_error(self):
        with self.assertRaises(ValueError):
            clip_windows([seg("A", 12.0, 13.0)], (0.0, 0.0), {"A": 10.0})


class ClipWordsTest(unittest.TestCase):
    WORDS = [
        {"start": 1.00, "end": 1.20, "word": "before"},
        {"start": 2.05, "end": 2.40, "word": "Why"},
        {"start": 2.45, "end": 2.70, "word": "kwakwakwak?"},
        {"start": 6.60, "end": 6.90, "word": "straddles"},
        {"start": 7.00, "end": 7.30, "word": "after"},
    ]

    def test_words_whose_midpoint_is_inside_are_kept_and_shifted(self):
        out = clip_words(self.WORDS, 2.03, 6.67)
        self.assertEqual([w["text"] for w in out], ["Why", "kwakwakwak?"])
        self.assertEqual(out[0], {"from": 0.02, "to": 0.37, "text": "Why"})

    def test_a_word_straddling_the_end_goes_by_its_midpoint(self):
        out = clip_words(self.WORDS, 2.03, 6.80)
        self.assertEqual([w["text"] for w in out], ["Why", "kwakwakwak?", "straddles"])

    def test_a_word_starting_before_the_clip_is_kept_if_its_midpoint_is_inside(self):
        words = [{"start": 1.90, "end": 2.40, "word": "Why"}]   # midpoint 2.15, inside 2.03-6.67
        out = clip_words(words, 2.03, 6.67)
        self.assertEqual(out, [{"from": 0.0, "to": 0.37, "text": "Why"}])


class DiskTest(unittest.TestCase):
    def test_estimate_is_147_mbit_per_second(self):
        self.assertEqual(estimate_bytes(60), 1_102_500_000)

    def test_refuses_without_three_times_the_estimate(self):
        needed = estimate_bytes(60)
        check_disk(Path("."), needed, free_bytes=needed * DISK_FACTOR)
        with self.assertRaises(RuntimeError):
            check_disk(Path("."), needed, free_bytes=needed * DISK_FACTOR - 1)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_edits_plan_math -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'edits_export'`.

- [ ] **Step 3: Implement**

Create `pipeline/edits_export.py`:

```python
#!/usr/bin/env python3
"""Cut an approved cuts.json into numbered clips for Instagram Edits.

One clip per segment, in plan order, each padded the way assemble.py pads it,
plus plan.json describing them. See
docs/superpowers/specs/2026-11-19-yap-to-edits-design.md.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

MBIT_PER_SECOND = 147   # ProRes 422 at 1080p30, the estimate's basis
DISK_FACTOR = 3         # Edits may copy imports into its own library


def clip_name(index: int, beat: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(beat or "").lower()).strip("-") or "segment"
    return f"{index:02d}-{slug}.mov"


def clip_windows(
    segments: Sequence[Dict[str, Any]],
    pad: Tuple[float, float],
    take_durations: Dict[str, float],
) -> List[Dict[str, Any]]:
    """Padded windows in plan order, clamped only to each take's length, as
    assemble.py does."""
    before, after = float(pad[0]), float(pad[1])
    windows = []
    for index, segment in enumerate(segments):
        take = str(segment["take"])
        start, end = float(segment["start"]), float(segment["end"])
        clip_start = max(0.0, start - before)
        clip_end = min(float(take_durations[take]), end + after)
        if clip_end <= clip_start:
            raise ValueError(f"segment {index} has no duration after padding")
        windows.append({
            "take": take, "source_start": start, "source_end": end,
            "clip_start": round(clip_start, 6), "clip_end": round(clip_end, 6),
            "duration": round(clip_end - clip_start, 6),
        })
    return windows


def clip_words(words: Sequence[Dict[str, Any]], clip_start: float, clip_end: float) -> List[Dict[str, Any]]:
    out = []
    for word in words:
        start, end = float(word["start"]), float(word["end"])
        middle = (start + end) / 2
        if clip_start <= middle < clip_end:
            out.append({
                "from": round(max(0.0, start - clip_start), 3),
                "to": round(max(0.0, end - clip_start), 3),
                "text": str(word["word"]).strip(),
            })
    return out


def estimate_bytes(total_seconds: float) -> int:
    return int(total_seconds * MBIT_PER_SECOND * 1_000_000 / 8)


def check_disk(path: Path, needed_bytes: int, free_bytes: Optional[int] = None) -> None:
    free = shutil.disk_usage(path).free if free_bytes is None else free_bytes
    if free < DISK_FACTOR * needed_bytes:
        raise RuntimeError(
            f"not enough disk space: need {DISK_FACTOR} x {needed_bytes / 1e9:.2f} GB, "
            f"have {free / 1e9:.2f} GB free"
        )
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_edits_plan_math -v` (all PASS), then `python3 -m unittest discover -s tests` (all PASS).

- [ ] **Step 5: Mutation check**

(a) In `check_disk`, change `<` to `<=`. `test_refuses_without_three_times_the_estimate` must FAIL. Restore it.
(b) In `clip_words`, test `start` instead of `middle` in the `if`. `test_a_word_starting_before_the_clip_is_kept_if_its_midpoint_is_inside` must FAIL. Restore it.

- [ ] **Step 6: Commit**

```bash
git add pipeline/edits_export.py tests/test_edits_plan_math.py
git commit -m "Work out Edits clip names, windows, words and disk room from a plan"
```

---

### Task 3: Cutting the clips, loudness, HDR, `plan.json` and the CLI

**Files:**
- Modify: `pipeline/edits_export.py`
- Test: `tests/test_edits_export.py`

**Interfaces:**
- Consumes: Task 1 (`source_framing`, `video_transfer`, `is_hdr_transfer`), Task 2 (all of it), `assemble.validate_plan(plan) -> (slug, fps, takes, segments)` (takes carry `_path`), `assemble.apply_corrections(words, corrections, take_id) -> (words, warnings)`, `assemble.caption_words(path)`, `assemble.loudness_targets(plan) -> (i, tp, lra)`, `grade.filter_string(grade) -> str`, `common.media_duration`, `common.load_json`.
- Produces:
  - `measure_integrated(windows: list, take_paths: dict) -> float`: integrated LUFS of all windows' audio concatenated in order.
  - `clip_filters(framing: str, hdr: bool, grade: str) -> str`: the `-vf` chain, ending in a scale/pad to the target size and `format=yuv422p10le`.
  - `export(plan_path: Path, out_dir: Path) -> Dict[str, Any]`: writes the clips and `plan.json`, and returns the plan.json dict.
  - CLI: `python3 pipeline/edits_export.py <cuts.json> [--out DIR]`, default `build/<slug>/edits`. Exit 0 on success; on failure, a non-zero exit with an `error:` line on stderr.
  - `class HdrUnsupported(RuntimeError)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_edits_export.py`. It generates two tiny takes. Take A is landscape 320×180 with a quiet 300 Hz tone. Take B is the same pixels tagged with a 90° display rotation (portrait) and a 12 dB louder tone. Use the rotation flag that Task 1's test settled on. Its plan has three segments: B 0.5–1.5 (hook), A 0.2–1.0 (build), and B 1.6–2.4 (payoff). Write its `words.json` files and one caption correction.

```python
"""An approved plan, cut into Edits clips with ffmpeg, end to end.

Tiny generated takes keep this fast. They still exercise the real decisions:
plan order, padding, rotation, shared loudness gain, corrections and failure
atomicity.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import edits_export  # noqa: E402
from common import media_duration  # noqa: E402

FPS = 30
FRAME = 1 / FPS


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def probe(path, entries):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


class ExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.root = root
        a, b_plain, cls.b = root / "A.mp4", root / "B_plain.mp4", root / "B.mp4"
        ffmpeg("-f", "lavfi", "-i", "testsrc=d=3:s=320x180:r=30", "-f", "lavfi",
               "-i", "sine=f=300:d=3", "-af", "volume=-24dB", "-c:v", "libx264", "-c:a", "aac",
               "-shortest", str(a))
        ffmpeg("-f", "lavfi", "-i", "testsrc=d=3:s=320x180:r=30", "-f", "lavfi",
               "-i", "sine=f=300:d=3", "-af", "volume=-12dB", "-c:v", "libx264", "-c:a", "aac",
               "-shortest", str(b_plain))
        ffmpeg("-display_rotation:v:0", "90", "-i", str(b_plain), "-c", "copy", str(cls.b))
        words = lambda texts, t0: [{"start": t0 + i * 0.3, "end": t0 + i * 0.3 + 0.25, "word": w}
                                   for i, w in enumerate(texts)]
        (root / "A.words.json").write_text(json.dumps({"words": words(["so", "here", "is"], 0.2)}))
        (root / "B.words.json").write_text(json.dumps({"words":
            words(["why", "quackwackwack", "matters"], 0.5) + words(["and", "that", "is", "it"], 1.6)}))
        cls.plan = {
            "version": 1, "slug": "test-reel", "fps": FPS, "headline": "why it matters",
            "pad": [0.07, 0.07], "loudness": {"i": -14, "tp": -1.5, "lra": 11},
            "takes": {"A": {"path": str(a), "words": str(root / "A.words.json")},
                      "B": {"path": str(cls.b), "words": str(root / "B.words.json")}},
            "segments": [
                {"take": "B", "start": 0.5, "end": 1.5, "beat": "hook", "kind": "structural", "reason": "the question"},
                {"take": "A", "start": 0.2, "end": 1.0, "beat": "build"},
                {"take": "B", "start": 1.6, "end": 2.4, "beat": "payoff"},
            ],
            "caption_corrections": [{"take": "B", "word_index": 1, "from": "quackwackwack", "to": "kwakwakwak"}],
        }
        cls.plan_path = root / "cuts.json"
        cls.plan_path.write_text(json.dumps(cls.plan))
        cls.out = root / "edits"
        cls.result = edits_export.export(cls.plan_path, cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_clips_follow_plan_order_and_names(self):
        self.assertEqual([c["file"] for c in self.result["clips"]],
                         ["01-hook.mov", "02-build.mov", "03-payoff.mov"])
        for clip in self.result["clips"]:
            self.assertTrue((self.out / clip["file"]).exists())

    def test_each_clip_is_its_window_within_one_frame(self):
        for clip in self.result["clips"]:
            expected = clip["clip_end"] - clip["clip_start"]
            self.assertLessEqual(abs(media_duration(self.out / clip["file"]) - expected), FRAME + 1e-6)

    def test_rotated_take_gives_portrait_clips_and_prores(self):
        streams = probe(self.out / "01-hook.mov", "stream=codec_name,width,height,pix_fmt,codec_type")["streams"]
        video = next(s for s in streams if s["codec_type"] == "video")
        self.assertEqual((video["codec_name"], video["width"], video["height"]), ("prores", 1080, 1920))
        self.assertEqual(video["pix_fmt"], "yuv422p10le")
        land = next(s for s in probe(self.out / "02-build.mov", "stream=codec_type,width,height")["streams"]
                    if s["codec_type"] == "video")
        self.assertEqual((land["width"], land["height"]), (1920, 1080))
        self.assertEqual(self.result["orientation"], "mixed")

    def test_words_are_corrected_and_in_clip_time(self):
        hook = self.result["clips"][0]
        self.assertEqual([w["text"] for w in hook["words"]], ["why", "kwakwakwak", "matters"])
        self.assertAlmostEqual(hook["words"][0]["from"], 0.07, places=2)

    def test_one_shared_gain_keeps_the_level_difference(self):
        def mean_volume(path):
            err = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                                 capture_output=True, text=True).stderr
            return float(err.split("mean_volume:")[1].split("dB")[0])
        quiet, loud = mean_volume(self.out / "02-build.mov"), mean_volume(self.out / "01-hook.mov")
        self.assertAlmostEqual(loud - quiet, 12.0, delta=1.5)
        self.assertIn("gain_db", self.result["loudness"])

    def test_plan_json_is_written(self):
        self.assertEqual(json.loads((self.out / "plan.json").read_text()), self.result)


class FailureTest(unittest.TestCase):
    def test_an_invalid_plan_leaves_no_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "cuts.json"
            bad.write_text(json.dumps({"version": 1, "slug": "x", "takes": {}, "segments": []}))
            out = Path(tmp) / "edits"
            with self.assertRaises(ValueError):
                edits_export.export(bad, out)
            self.assertFalse(out.exists())
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["cuts.json"])

    def test_hdr_without_a_working_conversion_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "A.mp4"
            ffmpeg("-f", "lavfi", "-i", "testsrc=d=1:s=64x36:r=30", "-f", "lavfi", "-i", "sine=d=1",
                   "-c:v", "libx264", "-c:a", "aac", "-shortest", str(src))
            (Path(tmp) / "A.words.json").write_text(json.dumps({"words": []}))
            plan = {"version": 1, "slug": "hdr", "fps": 30, "takes": {"A": {"path": str(src), "words": str(Path(tmp) / "A.words.json")}},
                    "segments": [{"take": "A", "start": 0.1, "end": 0.8}]}
            (Path(tmp) / "cuts.json").write_text(json.dumps(plan))
            with mock.patch.object(edits_export, "video_transfer", return_value="arib-std-b67"), \
                 mock.patch.object(edits_export, "hdr_conversion_available", return_value=False):
                with self.assertRaises(edits_export.HdrUnsupported):
                    edits_export.export(Path(tmp) / "cuts.json", Path(tmp) / "edits")
            self.assertFalse((Path(tmp) / "edits").exists())

    def test_not_enough_disk_refuses_before_cutting(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "A.mp4"
            ffmpeg("-f", "lavfi", "-i", "testsrc=d=1:s=64x36:r=30", "-f", "lavfi", "-i", "sine=d=1",
                   "-c:v", "libx264", "-c:a", "aac", "-shortest", str(src))
            (Path(tmp) / "A.words.json").write_text(json.dumps({"words": []}))
            plan = {"version": 1, "slug": "disk", "fps": 30,
                    "takes": {"A": {"path": str(src), "words": str(Path(tmp) / "A.words.json")}},
                    "segments": [{"take": "A", "start": 0.1, "end": 0.8}]}
            (Path(tmp) / "cuts.json").write_text(json.dumps(plan))
            with mock.patch.object(edits_export.shutil, "disk_usage", return_value=mock.Mock(free=1)):
                with self.assertRaises(RuntimeError):
                    edits_export.export(Path(tmp) / "cuts.json", Path(tmp) / "edits")
            self.assertFalse((Path(tmp) / "edits").exists())
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_edits_export -v`
Expected: FAIL with `AttributeError: module 'edits_export' has no attribute 'export'`.

- [ ] **Step 3: Implement**

Add to `pipeline/edits_export.py` (and extend its imports):

```python
import argparse
import json
import subprocess
import sys
import tempfile

from assemble import apply_corrections, caption_words, loudness_targets, validate_plan
from common import is_hdr_transfer, load_json, media_duration, source_framing, video_transfer
from grade import filter_string

SIZES = {"portrait": (1080, 1920), "landscape": (1920, 1080)}


class HdrUnsupported(RuntimeError):
    pass


def hdr_conversion_available() -> bool:
    """True if this ffmpeg has VideoToolbox's scale_vt (macOS)."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return " scale_vt " in out


def clip_filters(framing: str, hdr: bool, grade: str) -> str:
    width, height = SIZES[framing]
    chain = []
    if hdr:
        # VideoToolbox colour conversion to BT.709. The implementer verifies
        # this on a real HLG clip and records the exact working chain here;
        # export() refuses if the output's tags are not bt709.
        chain.append("hwupload,scale_vt=color_matrix=bt709:color_primaries=bt709:color_transfer=bt709,hwdownload,format=p010le")
    if grade:
        chain.append(grade)
    chain.append(f"scale={width}:{height}:force_original_aspect_ratio=decrease")
    chain.append(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black")
    chain.append("format=yuv422p10le")
    return ",".join(chain)


def measure_integrated(windows: Sequence[Dict[str, Any]], take_paths: Dict[str, Path]) -> float:
    inputs, parts = [], []
    for index, window in enumerate(windows):
        inputs += ["-ss", f"{window['clip_start']:.3f}", "-t", f"{window['duration']:.3f}",
                   "-i", str(take_paths[window["take"]])]
        parts.append(f"[{index}:a:0]aresample=48000,aformat=channel_layouts=stereo[a{index}]")
    concat = "".join(f"[a{i}]" for i in range(len(windows))) + f"concat=n={len(windows)}:v=0:a=1[cut]"
    graph = ";".join(parts + [concat, "[cut]ebur128=framelog=quiet[out]"])
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *inputs, "-filter_complex", graph,
                             "-map", "[out]", "-f", "null", "-"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"loudness measurement failed: {result.stderr.strip()[-400:]}")
    summary = result.stderr.rsplit("Summary:", 1)[-1]
    try:
        return float(summary.split("I:")[1].split("LUFS")[0])
    except (IndexError, ValueError):
        raise RuntimeError("could not read integrated loudness from ffmpeg") from None


def cut_clip(source: Path, window: Dict[str, Any], vf: str, gain_db: float, tp: float, fps: int, out: Path) -> None:
    limit = 10 ** (tp / 20)
    command = [
        "ffmpeg", "-v", "error", "-y", "-ss", f"{window['clip_start']:.3f}", "-i", str(source),
        "-t", f"{window['duration']:.3f}", "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", vf, "-r", str(fps),
        "-af", f"volume={gain_db:.2f}dB,alimiter=limit={limit:.4f}:level=disabled,aresample=48000",
        "-c:v", "prores_ks", "-profile:v", "2", "-c:a", "pcm_s16le", str(out),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {out.name}: {result.stderr.strip()[-400:]}")


def export(plan_path: Path, out_dir: Path) -> Dict[str, Any]:
    plan = load_json(plan_path)
    slug, fps, takes, segments = validate_plan(plan)
    target_i, tp, _ = loudness_targets(plan)
    pad = plan.get("pad", [0.07, 0.07])
    take_paths = {tid: take["_path"] for tid, take in takes.items()}
    durations = {tid: media_duration(path) for tid, path in take_paths.items()}
    framings = {tid: source_framing(path) for tid, path in take_paths.items()}
    hdr = {tid: is_hdr_transfer(video_transfer(path)) for tid, path in take_paths.items()}
    if any(hdr.values()) and not hdr_conversion_available():
        raise HdrUnsupported("an HDR take needs VideoToolbox's scale_vt to convert to BT.709; refusing to pass HDR through")
    windows = clip_windows(segments, (pad[0], pad[1]), durations)
    out_dir = Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    check_disk(out_dir.parent, estimate_bytes(sum(w["duration"] for w in windows)))

    corrections = plan.get("caption_corrections") or []
    take_words = {}
    for tid, take in takes.items():
        words = caption_words(Path(take["words"])) if take.get("words") else []
        take_words[tid], _ = apply_corrections(words, corrections, tid)

    measured = measure_integrated(windows, take_paths)
    gain = target_i - measured
    grade = filter_string((plan.get("style") or {}).get("grade"))

    staging = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.", dir=str(out_dir.parent)))
    try:
        clips = []
        for index, (segment, window) in enumerate(zip(segments, windows), start=1):
            name = clip_name(index, segment.get("beat"))
            tid = window["take"]
            cut_clip(take_paths[tid], window, clip_filters(framings[tid], hdr[tid], grade), gain, tp, fps, staging / name)
            measured_duration = media_duration(staging / name)
            if abs(measured_duration - window["duration"]) > 1 / fps + 1e-6:
                raise RuntimeError(f"{name} is {measured_duration:.3f}s, expected {window['duration']:.3f}s")
            clips.append({
                "file": name, "beat": segment.get("beat", ""), "kind": segment.get("kind", "mechanical"),
                "reason": segment.get("reason", ""), **window, "duration": round(measured_duration, 3),
                "orientation": framings[tid],
                "words": clip_words(take_words[tid], window["clip_start"], window["clip_end"]),
            })
        kinds = {c["orientation"] for c in clips}
        result = {
            "version": 1, "slug": slug, "headline": plan.get("headline", ""), "fps": fps,
            "orientation": kinds.pop() if len(kinds) == 1 else "mixed",
            "loudness": {"target_i": target_i, "measured_i": round(measured, 2), "gain_db": round(gain, 2)},
            "clips": clips,
        }
        (staging / "plan.json").write_text(json.dumps(result, indent=2))
        if out_dir.exists():
            shutil.rmtree(out_dir)
        staging.rename(out_dir)
        return result
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path, help="approved cuts.json")
    parser.add_argument("--out", type=Path, help="output folder (default build/<slug>/edits)")
    args = parser.parse_args(argv)
    try:
        out = args.out or args.plan.parent / "edits"
        result = export(args.plan, out)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {len(result['clips'])} clip(s) to {out} (gain {result['loudness']['gain_db']:+.2f} dB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Notes for the implementer:
- `loudness_targets`, `caption_words`, `apply_corrections` and `validate_plan` exist in `assemble.py`. Read their docstrings and use them as they are. If one has a different signature from what's shown, adapt the call and note it in your report.
- If `validate_plan` raises for an empty or invalid plan before any folder is made, `test_an_invalid_plan_leaves_no_folder` holds: `check_disk` and the staging directory come after validation.
- **HDR chain:** produce a real HLG test clip if this ffmpeg can (for example x264 with `-x264-params "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc"`), and check what `clip_filters(..., hdr=True)` outputs:
  - If `color_transfer` comes out `bt709`, add a real test asserting it.
  - If the VideoToolbox chain can't work in ffmpeg 8.1 on this Mac, change `hdr_conversion_available` to return False and report DONE_WITH_CONCERNS. Refusing is the spec's required behaviour when conversion isn't available.
  - In both cases, `export` must also verify an HDR clip's output transfer and raise `HdrUnsupported` if it isn't `bt709`.
- Run the export tests with `python3 -m unittest tests.test_edits_export -v`. They take a few seconds.

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m unittest tests.test_edits_export -v` (all PASS), then `python3 -m unittest discover -s tests` (all PASS).

- [ ] **Step 5: Mutation checks** (each must FAIL its test; restore after each)

(a) Give each clip its own gain, by measuring per window in the loop: `test_one_shared_gain_keeps_the_level_difference`.
(b) Replace `framings[tid]` with `"landscape"`: `test_rotated_take_gives_portrait_clips_and_prores`.
(c) Apply corrections after `clip_words` instead of to the whole take: `test_words_are_corrected_and_in_clip_time`.
(d) Remove the `shutil.rmtree(staging ...)` cleanup: the failure tests must fail on a leftover `.edits.*` folder.

- [ ] **Step 6: Commit**

```bash
git add pipeline/edits_export.py tests/test_edits_export.py
git commit -m "Cut an approved plan into Edits clips with one shared gain"
```

---

### Task 4: The `yap-to-edits` skill and its helper

**Files (repo `~/dotfiles`; create the branch `feature/yap-to-edits-skill` from `main` first):**
- Create: `claude/skills/yap-to-edits/SKILL.md`
- Create: `claude/skills/yap-to-edits/scripts/edits_plan.py`
- Create: `claude/skills/yap-to-edits/scripts/test_edits_plan.py`

**Interfaces:**
- Consumes: `plan.json` from Task 3 (shape in the spec).
- Produces:
  - `edits_plan.py check <folder>` prints `ok` and exits 0, or lists problems and exits 1. Problems are a missing `plan.json`, a missing clip file, or a duration off by more than one frame (measured with ffprobe).
  - `edits_plan.py align <plan.json> <edits-captions.json>`. The captions file is `[{"id": str, "text": str}, …]` in timeline order, as read from the Edits `captions` tool. It prints JSON `{"edits": [{"id", "text"}], "flagged": [{"id", "text", "reason"}]}`.
  - Python functions `check(folder: Path) -> list[str]` and `align(plan_words: list[str], captions: list[dict], min_ratio: float = 0.6) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `claude/skills/yap-to-edits/scripts/test_edits_plan.py`:

```python
"""Matching Edits' auto captions to yap's transcript.

Edits transcribes the cut itself and mishears names ("quack wack wack" for
kwakwakwak). yap's words are the authority, but only where the two clearly line
up: a caption too different to place is reported, never rewritten.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from edits_plan import align, check  # noqa: E402

PLAN = "why kwakwakwak matters so much to me and that is it".split()


def caps(*texts):
    return [{"id": f"c{i}", "text": t} for i, t in enumerate(texts)]


class AlignTest(unittest.TestCase):
    def test_exact_match_needs_no_edits(self):
        result = align(PLAN, caps("Why kwakwakwak matters", "so much to me", "and that is it"))
        self.assertEqual(result, {"edits": [], "flagged": []})

    def test_a_misheard_name_is_respelled(self):
        result = align(PLAN, caps("Why quack wack wack matters", "so much to me", "and that is it"))
        self.assertEqual(result["edits"], [{"id": "c0", "text": "Why kwakwakwak matters"}])

    def test_a_dropped_word_is_restored(self):
        result = align(PLAN, caps("Why kwakwakwak matters", "so to me", "and that is it"))
        self.assertEqual(result["edits"], [{"id": "c1", "text": "so much to me"}])

    def test_an_inserted_word_is_removed(self):
        result = align(PLAN, caps("Why kwakwakwak matters", "so so much to me", "and that is it"))
        self.assertEqual(result["edits"], [{"id": "c1", "text": "so much to me"}])

    def test_a_caption_too_different_is_flagged_not_changed(self):
        result = align(PLAN, caps("Why kwakwakwak matters", "completely unrelated noise here", "and that is it"))
        self.assertEqual(result["edits"], [])
        self.assertEqual([f["id"] for f in result["flagged"]], ["c1"])


class CheckTest(unittest.TestCase):
    def test_missing_clip_and_wrong_duration_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=1:s=64x36:r=30",
                            "-c:v", "prores_ks", str(folder / "01-hook.mov")], check=True)
            plan = {"fps": 30, "clips": [{"file": "01-hook.mov", "duration": 2.0}, {"file": "02-build.mov", "duration": 1.0}]}
            (folder / "plan.json").write_text(json.dumps(plan))
            problems = check(folder)
            self.assertTrue(any("02-build.mov" in p and "missing" in p for p in problems))
            self.assertTrue(any("01-hook.mov" in p and "duration" in p for p in problems))

    def test_a_good_folder_has_no_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=1:s=64x36:r=30",
                            "-c:v", "prores_ks", str(folder / "01-hook.mov")], check=True)
            (folder / "plan.json").write_text(json.dumps({"fps": 30, "clips": [{"file": "01-hook.mov", "duration": 1.0}]}))
            self.assertEqual(check(folder), [])
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd ~/dotfiles/claude/skills/yap-to-edits/scripts && python3 -m unittest test_edits_plan -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'edits_plan'`.

- [ ] **Step 3: Implement `edits_plan.py`**

```python
#!/usr/bin/env python3
"""Helpers for building an Edits project from a yap plan.json.

  edits_plan.py check <folder>
  edits_plan.py align <plan.json> <edits-captions.json>
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def _norm(token: str) -> str:
    return re.sub(r"[^a-z0-9']", "", token.lower())


def _duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def check(folder: Path) -> List[str]:
    plan_path = folder / "plan.json"
    if not plan_path.exists():
        return [f"{plan_path} missing"]
    plan = json.loads(plan_path.read_text())
    frame = 1 / float(plan.get("fps", 30))
    problems = []
    for clip in plan.get("clips", []):
        path = folder / clip["file"]
        if not path.exists():
            problems.append(f"{clip['file']} missing")
            continue
        actual = _duration(path)
        if abs(actual - float(clip["duration"])) > frame + 1e-6:
            problems.append(f"{clip['file']} duration {actual:.3f}s, plan says {clip['duration']}s")
    return problems


def align(plan_words: List[str], captions: List[Dict[str, Any]], min_ratio: float = 0.6) -> Dict[str, list]:
    """Map each Edits caption onto yap's words and propose corrected text."""
    cap_tokens, owner = [], []
    for index, caption in enumerate(captions):
        for token in caption["text"].split():
            cap_tokens.append(_norm(token))
            owner.append(index)
    plan_norm = [_norm(w) for w in plan_words]
    matcher = difflib.SequenceMatcher(a=cap_tokens, b=plan_norm, autojunk=False)
    # For every caption token, the plan index it maps to (or None).
    spans: Dict[int, List[int]] = {i: [] for i in range(len(captions))}
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal" or tag == "replace":
            caption_ids = [owner[k] for k in range(a0, a1)]
            for k, b in zip(range(a0, a1), range(b0, b1)):
                spans[owner[k]].append(b)
            if tag == "replace" and (b1 - b0) > (a1 - a0) and caption_ids:
                spans[caption_ids[-1]].extend(range(b0 + (a1 - a0), b1))
        elif tag == "insert":
            anchor = owner[a0 - 1] if a0 > 0 else 0
            spans[anchor].extend(range(b0, b1))
    edits, flagged = [], []
    for index, caption in enumerate(captions):
        indexes = sorted(set(spans[index]))
        if not indexes:
            flagged.append({"id": caption["id"], "text": caption["text"], "reason": "no matching words"})
            continue
        proposed_words = plan_words[indexes[0]:indexes[-1] + 1]
        proposed = " ".join(proposed_words)
        ratio = difflib.SequenceMatcher(a=[_norm(t) for t in caption["text"].split()],
                                        b=[_norm(w) for w in proposed_words]).ratio()
        if ratio < min_ratio:
            flagged.append({"id": caption["id"], "text": caption["text"], "reason": f"match {ratio:.2f} below {min_ratio}"})
            continue
        if caption["text"][:1].isupper():
            proposed = proposed[:1].upper() + proposed[1:]
        if _norm_text(proposed) != _norm_text(caption["text"]):
            edits.append({"id": caption["id"], "text": proposed})
    return {"edits": edits, "flagged": flagged}


def _norm_text(text: str) -> List[str]:
    return [_norm(t) for t in text.split()]


def main(argv: List[str]) -> int:
    if len(argv) >= 2 and argv[0] == "check":
        problems = check(Path(argv[1]))
        print("ok" if not problems else "\n".join(problems))
        return 0 if not problems else 1
    if len(argv) >= 3 and argv[0] == "align":
        plan = json.loads(Path(argv[1]).read_text())
        words = [w["text"] for clip in plan["clips"] for w in clip["words"]]
        captions = json.loads(Path(argv[2]).read_text())
        print(json.dumps(align(words, captions), indent=2))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

The alignment above is a starting point; the tests are the contract. If a test fails, fix the algorithm, not the test, and keep the rule: a caption is only rewritten where the match ratio is at least `min_ratio`. A misheard multi-token name ("quack wack wack" → "kwakwakwak") is a `replace` with more caption tokens than plan tokens. Make sure that case maps onto the one plan word, and that the dropped and inserted cases behave.

- [ ] **Step 4: Write `SKILL.md`**

Write `claude/skills/yap-to-edits/SKILL.md` with front matter:

```yaml
---
name: yap-to-edits
description: Use when Kris wants a yap (talking-to-camera) take edited in Instagram Edits for Mac instead of, or as well as, the studio render. For example "edit this yap in Edits", "build it in Edits", "put the cut in Edits", or anything about turning an approved yap cut plan into an Edits project, one clip per beat. Not for workout footage (kwakfit-reel-edit).
---
```

The body follows the spec's "Part 2" steps exactly, in this order:
1. Prep on this Mac: yap's laptop path, the approval gate unchanged, done with the yap-editor skill.
2. `python3 pipeline/edits_export.py build/<slug>/cuts.json`.
3. Fetch to `~/Movies/yap/<slug>/`, then `scripts/edits_plan.py check`.
4. Preflight: `appState`. Read the editing tools' schemas once a project is open, and stop if one is missing.
5. Project: `newProject`, `setProjectDynamicRange SDR`, 9:16, black.
6. `addMedia` each clip in order, then check `elements`.
7. Framing for landscape clips, using `getTransform`/`setTransform`, then `captureFrame` at boundaries.
8. Captions: `generateCaptions`, `captions`, then `edits_plan.py align`. Apply edits with `editCaption`, and report flagged ones.
9. Caption preset (`Word Highlight Box`) and highlight colour from `GET /studio/brands/<slug>`, via the `smapi.sh` pattern in the kwakfit-reel-edit skill.
10. No extra decoration for standard, walking or car yaps.
11. Checks: frame 0, cuts, `previewVideo`.
12. Report.
13. Export only on request, with `setExportSettings` (HD, nineBySixteen, 30, high, SDR) right before `export`. Verify -14 ±1 LUFS, TP ≤ -1.0, duration, and 1080×1920.
14. Schedule through the studio under the existing trial and approval rules, with the batch title `yap→edits · <slug>`.
15. Cleanup offer.

Include these mistakes as a table:
- running the old studio path's assemble instead of `edits_export`;
- importing from outside `~/Movies`, which hits `Sandbox bookmark unavailable`;
- trusting Edits' caption spelling;
- skipping the approval gate;
- exporting without `setExportSettings`, since settings reset when a project is reopened;
- never posting without Kris's go-ahead for that post.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd ~/dotfiles/claude/skills/yap-to-edits/scripts && python3 -m unittest test_edits_plan -v`
Expected: all PASS.

- [ ] **Step 6: Mutation check**

Set `min_ratio` to 0.0 in `align`'s default. `test_a_caption_too_different_is_flagged_not_changed` must FAIL. Restore it.

- [ ] **Step 7: Commit (in `~/dotfiles`)**

```bash
cd ~/dotfiles && git add claude/skills/yap-to-edits && git commit -m "Add the yap-to-edits skill: build an Edits project from an approved yap plan"
```

---

### Task 5: End to end on the 2026-11-19 take (the controller runs this; it needs Kris)

This task needs Edits open on this Mac and Kris's approval at yap's gate, so the controller runs it rather than an implementer subagent.

- [ ] **Step 1: Environment.** In `~/Developer/yap-editor-edits`: `uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python mlx-whisper`. Check `ffmpeg` is 8.x.
- [ ] **Step 2: Fetch the take.** `mkdir -p media/<slug>` and rsync `kwakmini64:/Volumes/T9/creative/dropbox/2026-11-19-015108-b43073695b7b-take.mov` to `media/<slug>/A.mov`. The slug is `20261119-kwakwakwak-<6 random [a-z0-9]>`. Check free disk space first.
- [ ] **Step 3: Prep.** Run `transcribe.py` and then `plan.py --energy`, as the yap-editor skill documents. Report the transcript length and the draft's kept duration.
- [ ] **Step 4: Editorial pass and approval gate.** Follow yap's `agent/AGENT.md` rules. Present the beats, durations, reasons, total and headline to Kris, and **wait for his answer**. Then write the approved `build/<slug>/cuts.json`.
- [ ] **Step 5: Export.** Run `python3 pipeline/edits_export.py build/<slug>/cuts.json`, then `edits_plan.py check`, then copy to `~/Movies/yap/<slug>/`.
- [ ] **Step 6: Build in Edits** by following the skill. Capture frames at every cut and show them to Kris.
- [ ] **Step 7: Report** each beat, the total, flagged captions, and what Kris can adjust. Export and schedule only if Kris asks.
- [ ] **Step 8: PRs.** Push the yap-editor branch and update PR #1 from spec to implementation. Push the dotfiles branch and open a draft PR. State the test counts, mutation checks, and what the end-to-end run showed.
