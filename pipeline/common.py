#!/usr/bin/env python3
"""Small standard-library helpers shared by the pipeline scripts."""

from __future__ import annotations

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
            output.append({
                "from": max(0.0, word_start + shift),
                "to": max(0.0, word_end + shift),
                "text": str(word.get("word", "")).strip(),
            })
    return output


def normalize_word(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9']+", "", value.lower())


def normalize_words(words: Iterable[str]) -> List[str]:
    return [normalized for normalized in (normalize_word(word) for word in words) if normalized]
