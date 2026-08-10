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


def normalize_word(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9']+", "", value.lower())


def normalize_words(words: Iterable[str]) -> List[str]:
    return [normalized for normalized in (normalize_word(word) for word in words) if normalized]
