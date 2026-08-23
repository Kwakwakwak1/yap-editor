#!/usr/bin/env python3
"""Small standard-library helpers shared by the pipeline scripts."""

from __future__ import annotations

import math

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent


def run_command(
    command: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a command with text output and useful error propagation."""
    return subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        check=check,
        capture_output=capture,
        text=True,
    )


def repo_path(value: str) -> Path:
    """Resolve a plan path relative to the repository root."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def display_path(path: Path) -> str:
    """Print paths relative to the repo whenever possible."""
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def safe_record_path(path: Path) -> str:
    """Return a non-machine-specific path for JSON metadata."""
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def ffprobe_json(path: Path, entries: str) -> Dict[str, Any]:
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            entries,
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    return json.loads(result.stdout or "{}")


def media_duration(path: Path) -> float:
    data = ffprobe_json(path, "format=duration")
    try:
        return float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("ffprobe did not return a duration") from exc


def has_audio(path: Path) -> bool:
    data = ffprobe_json(path, "stream=codec_type")
    return any(stream.get("codec_type") == "audio" for stream in data.get("streams", []))


def video_pixel_format(path: Path) -> str:
    data = ffprobe_json(path, "stream=pix_fmt,codec_type")
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return str(stream.get("pix_fmt", ""))
    return ""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def measure_loudness(path: Path, target_i: float, target_tp: float, target_lra: float) -> Dict[str, float]:
    """Measure a file's loudness with ffmpeg's loudnorm analysis pass.

    Returns the parsed measurement (`input_i`, `input_tp`, `input_lra`, ...).
    Raises RuntimeError when loudnorm produced nothing parseable, so callers can
    report that distinctly from a file that simply missed its target.

    Shared by verify.py (the cut, tight tolerance) and verify_reel.py (the reel,
    wider tolerance because a music bed legitimately shifts integrated loudness).
    """
    import json as _json
    import re as _re
    import subprocess as _subprocess

    result = _subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path), "-af",
            f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    matches = _re.findall(r"\{\s*\"input_i\".*?\}", result.stderr, _re.DOTALL)
    if not matches:
        raise RuntimeError("loudnorm did not return measurement JSON")
    try:
        # The last block is the summary; earlier ones can appear per-stream.
        return {key: float(value) for key, value in _json.loads(matches[-1]).items() if _is_number(value)}
    except (TypeError, ValueError, _json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not parse loudnorm measurement: {exc}") from exc


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def map_words_to_timeline(
    words_by_take: Dict[str, Sequence[Dict[str, Any]]],
    segments: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Project each take's word timings onto the assembled cut's timeline.

    A segment keeps `[start, end)` of one take and lands at `offset` in the cut,
    while `padded_start` marks where the extracted clip actually begins -- pad
    is applied before the kept range, so a word moves by `offset - padded_start`.

    Both assemble.py (building captions) and verify.py (diffing the rendered cut
    against what was planned) need exactly this projection, and both carried
    their own copy. They had already drifted: one clamped negative timestamps and
    stripped whitespace, the other did neither. This is the single implementation.

    Words are returned as `{from, to, text}` to match the caption cue shape the
    renderer consumes.
    """
    output: List[Dict[str, Any]] = []
    for segment in segments:
        try:
            start = float(segment["start"])
            end = float(segment["end"])
        except (KeyError, TypeError, ValueError):
            continue
        # `.get` with defaults rather than direct indexing: verify.py tolerated a
        # segment without offset/padded_start and assemble.py did not, so the
        # permissive reading is the superset that keeps both callers working.
        offset = float(segment.get("offset", 0.0))
        padded_start = float(segment.get("padded_start", start))
        shift = offset - padded_start
        for word in words_by_take.get(str(segment["take"]), []):
            try:
                word_start = float(word["start"])
                word_end = float(word["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if word_end <= start or word_start >= end:
                continue
            projected = {
                "from": max(0.0, word_start + shift),
                "to": max(0.0, word_end + shift),
                "text": str(word.get("word", "")).strip(),
            }
            if word.get("manual"):
                # Additive and optional: a word a person respelled, so the
                # script pass can be kept off the cue that holds it. verify.py
                # reads `text` and nothing else, so this reaches assemble.py's
                # grouping without changing what the other caller sees.
                projected["manual"] = True
            output.append(projected)
    return output


def project_rows_to_timeline(
    rows_by_take: Dict[str, Sequence[Dict[str, Any]]],
    segments: Iterable[Dict[str, Any]],
    words_by_take: Optional[Dict[str, Sequence[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Project aligned script lines onto the assembled cut's timeline.

    `align_take` reports each script line's span in TAKE time. `build_captions`
    builds its cues in CUT time, via map_words_to_timeline. `correct_cues`
    overlaps the two to decide which script words are context for which cue --
    so handing it one of each compares numbers from different clocks. It does
    not raise: the overlap simply never matches, every cue comes back unchanged,
    and the respelling pass reports success having done nothing at all.

    The shift is `offset - padded_start`, the same rule map_words_to_timeline
    applies, and it lives here beside it deliberately. That function's docstring
    records what happened when this rule had two implementations: "they had
    already drifted: one clamped negative timestamps and stripped whitespace,
    the other did neither."

    A row is clipped to the kept range of each segment it survives in, and a row
    spanning a cut appears once per segment -- both halves are on screen, so both
    need their spelling. A row cut out entirely yields nothing, which is correct:
    those words never reach the viewer.
    """
    output: List[Dict[str, Any]] = []
    for segment in segments:
        try:
            start = float(segment["start"])
            end = float(segment["end"])
        except (KeyError, TypeError, ValueError):
            continue
        rows = rows_by_take.get(str(segment.get("take", ""))) or []
        # Same permissive `.get` defaults as map_words_to_timeline: it is called
        # on this very data by verify.py with segments that carry neither key.
        shift = float(segment.get("offset", 0.0)) - float(
            segment.get("padded_start", start))
        for row in rows:
            row_from, row_to = row.get("from"), row.get("to")
            if row_from is None or row_to is None:
                # A line align_take could not find in this take. Recorded rather
                # than omitted upstream, so it arrives here and is skipped.
                continue
            visible_from = max(float(row_from), start)
            visible_to = min(float(row_to), end)
            if visible_to <= visible_from:
                continue
            output.append(_clip_row(
                row, float(row_from), float(row_to), visible_from, visible_to,
                shift, (words_by_take or {}).get(str(segment.get("take", ""))),
            ))
    return output


def _clip_row(
    row: Dict[str, Any],
    row_from: float,
    row_to: float,
    visible_from: float,
    visible_to: float,
    shift: float,
    take_words: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """One row, narrowed to the part of it the cut kept.

    THE WORDS ARE NARROWED TOO, and that is the whole point of this function.
    A row whose span is clipped but whose text is not claims all eighteen words
    of its line across the three quarters of a second that survived -- and
    script_spelling's `_overlapping_words` reads the span to decide how many
    words to offer a cue, so it hands a two-word cue the entire line. The
    resulting replace block is uneven, `corrections_for` refuses it, and every
    correction silently does not happen.

    Measured on a real job before this existed: six segments, six projected
    rows, eighteen words offered to a cue reading "Oh, hey.", zero corrections
    applied, and no error anywhere.

    The words are assumed evenly spread across the row's span, which is not a
    new assumption -- it is the one `_overlapping_words` already makes, and
    shotlist.py with it. It only has to be good enough to bring the right
    handful of words into the comparison; the similarity threshold decides the
    rest.
    """
    span = row_to - row_from
    clipped = dict(row, **{"from": visible_from + shift, "to": visible_to + shift})
    if span <= 0:
        return clipped

    fractions = _kept_fraction(row_from, row_to, visible_from, visible_to, take_words)
    for key, value in (("line", str(row.get("line", "")).split()),
                       ("words", list(row.get("words") or []))):
        if not value:
            continue
        first = int(len(value) * fractions[0])
        last = math.ceil(len(value) * fractions[1])
        kept = value[first:max(last, first + 1)]
        clipped[key] = " ".join(kept) if key == "line" else kept
    return clipped


def _kept_fraction(
    row_from: float,
    row_to: float,
    visible_from: float,
    visible_to: float,
    take_words: Optional[Sequence[Dict[str, Any]]],
) -> Tuple[float, float]:
    """Where the kept range begins and ends, as a fraction of the row's WORDS.

    By counting words when the transcript is available, and by elapsed time when
    it is not.

    The difference is not academic, and a real job is what showed it. Words are
    not evenly spread across a take -- the gaps between them are most of it, and
    cutting is precisely the act of removing those gaps. On a twelve-second cut
    of a thirty-second take, timing the clip by elapsed time offered a one-word
    cue two script words: the block came out uneven, and the correction was
    refused for a reason that had nothing to do with the words.

    Counting words is exact wherever a transcript exists, which is every path
    that reaches this today. The time fallback keeps the function honest for a
    caller that has rows but no words.
    """
    if take_words:
        spoken = [
            index for index, word in enumerate(take_words)
            if row_from <= float(word.get("start", -1)) <= row_to
        ]
        if spoken:
            inside = [
                position for position, index in enumerate(spoken)
                if visible_from <= float(take_words[index].get("start", -1)) <= visible_to
            ]
            if inside:
                return inside[0] / len(spoken), (inside[-1] + 1) / len(spoken)
    span = row_to - row_from
    if span <= 0:
        return 0.0, 1.0
    return (visible_from - row_from) / span, (visible_to - row_from) / span


def normalize_word(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9']+", "", value.lower())


def normalize_words(words: Iterable[str]) -> List[str]:
    return [normalized for normalized in (normalize_word(word) for word in words) if normalized]
