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
