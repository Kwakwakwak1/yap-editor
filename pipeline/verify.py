#!/usr/bin/env python3
"""Verify an assembled cut against its resolved plan and media invariants."""

from __future__ import annotations

import argparse
import difflib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from common import (
    REPO_ROOT,
    display_path,
    ffprobe_json,
    load_json,
    map_words_to_timeline,
    measure_loudness,
    media_duration,
    normalize_word,
    repo_path,
    run_command,
    video_pixel_format,
)


def print_result(name: str, status: str, detail: str) -> None:
    print(f"{name}: {status}{f' ({detail})' if detail else ''}")


def planned_words(resolved: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The words the plan says the cut should contain, on the cut's own timeline.

    The projection itself lives in common.map_words_to_timeline, shared with
    assemble.py's caption builder -- the two copies had already drifted.
    """
    words_by_take: Dict[str, List[Dict[str, Any]]] = {}
    for take_id, take in resolved.get("takes", {}).items():
        path_value = take.get("words")
        if path_value and repo_path(path_value).exists():
            data = load_json(repo_path(path_value))
            words_by_take[str(take_id)] = data.get("words", [])
    return map_words_to_timeline(words_by_take, resolved.get("segments", []))


def find_backend() -> Optional[str]:
    for module_name, backend in (("mlx_whisper", "mlx"), ("faster_whisper", "faster"), ("whisper", "openai")):
        try:
            __import__(module_name)
            return backend
        except ImportError:
            continue
    return None


def run_join_check(cut: Path, resolved: Dict[str, Any], backend: str) -> Tuple[str, str]:
    if not find_backend():
        return "SKIPPED", "no transcription backend is installed"
    planned = planned_words(resolved)
    if not planned:
        return "SKIPPED", "resolved plan has no words files"
    with tempfile.TemporaryDirectory(prefix="verify-") as temp_dir:
        output_words = Path(temp_dir) / "output.words.json"
        command = [sys.executable, str(REPO_ROOT / "pipeline" / "transcribe.py"), str(cut), "-o", str(output_words)]
        if backend != "auto":
            command += ["--backend", backend]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            message = detail[-1] if detail else "unknown error"
            lowered = message.lower()
            if any(marker in lowered for marker in ("no transcription backend", "model", "cache", "operation not permitted", "could not download")):
                return "SKIPPED", "transcription backend is installed but its model is unavailable in this environment"
            return "FAIL", f"transcription failed: {message}"
        try:
            actual_data = load_json(output_words)
        except (OSError, ValueError) as exc:
            return "FAIL", f"transcription output unreadable: {exc}"
    expected_tokens = [normalize_word(item["text"]) for item in planned if normalize_word(item["text"])]
    actual_items = actual_data.get("words", [])
    actual_tokens = [normalize_word(str(item.get("word", ""))) for item in actual_items if normalize_word(str(item.get("word", "")))]
    matcher = difflib.SequenceMatcher(a=expected_tokens, b=actual_tokens)
    dropped: List[str] = []
    doubled: List[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            dropped.extend(f"{planned[i]['text']}@{planned[i]['from']:.3f}s" for i in range(i1, i2))
        if tag in ("insert", "replace"):
            doubled.extend(f"{actual_items[j].get('word', '')}@{float(actual_items[j].get('start', 0.0)):.3f}s" for j in range(j1, j2))
    if dropped or doubled:
        detail_parts = []
        if dropped:
            detail_parts.append("dropped=" + ", ".join(dropped[:8]))
        if doubled:
            detail_parts.append("doubled=" + ", ".join(doubled[:8]))
        return "FAIL", "; ".join(detail_parts)
    return "PASS", f"{len(actual_tokens)} words match planned keep-text"


def loudness_check(cut: Path, resolved: Dict[str, Any]) -> Tuple[str, str]:
    loudness = resolved.get("loudness", {})
    target = float(loudness.get("i", -14))
    try:
        measurement = measure_loudness(
            cut, target, float(loudness.get("tp", -1.5)), float(loudness.get("lra", 11))
        )
        measured = float(measurement["input_i"])
    except (KeyError, RuntimeError) as exc:
        return "FAIL", str(exc)
    if abs(measured - target) > 1.0:
        return "FAIL", f"input_i={measured:.2f} LUFS, target={target:.2f} ±1"
    return "PASS", f"input_i={measured:.2f} LUFS, target={target:.2f} ±1"


def frame_check(cut: Path, resolved_path: Optional[Path], frames: bool) -> None:
    if not frames or not resolved_path:
        return
    resolved = load_json(resolved_path)
    frame_dir = resolved_path.parent / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for index, segment in enumerate(resolved.get("segments", []), start=1):
        midpoint = float(segment.get("offset", 0.0)) + float(segment.get("duration", 0.0)) / 2
        output = frame_dir / f"segment-{index:03d}.jpg"
        run_command([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{midpoint:.3f}",
            "-i", str(cut), "-frames:v", "1", str(output),
        ])
    print(f"Extracted {len(resolved.get('segments', []))} midpoint frame(s) to {display_path(frame_dir)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cut", type=Path)
    parser.add_argument("--resolved", type=Path)
    parser.add_argument("--frames", action="store_true")
    parser.add_argument("--backend", default="auto", help="accepted for CLI compatibility; backend selection is automatic")
    args = parser.parse_args()
    cut = repo_path(str(args.cut))
    if not cut.exists():
        print(f"ERROR: cut not found: {args.cut}", file=sys.stderr)
        return 1
    resolved_path = repo_path(str(args.resolved)) if args.resolved else cut.parent / "cuts.resolved.json"
    try:
        resolved = load_json(resolved_path) if resolved_path.exists() else {}
    except (OSError, ValueError) as exc:
        print(f"ERROR: could not read resolved plan: {exc}", file=sys.stderr)
        return 1

    failures = 0
    skipped: List[str] = []
    try:
        duration = media_duration(cut)
        planned = float(resolved.get("planned_duration", 0.0))
        if not planned:
            print_result("Duration", "SKIPPED", "resolved plan has no planned_duration")
            skipped.append("duration")
        elif abs(duration - planned) <= 0.5:
            print_result("Duration", "PASS", f"actual={duration:.3f}s planned={planned:.3f}s")
        else:
            print_result("Duration", "FAIL", f"actual={duration:.3f}s planned={planned:.3f}s")
            failures += 1
        loud_status, loud_detail = loudness_check(cut, resolved)
        print_result("Loudness", loud_status, loud_detail)
        if loud_status == "FAIL":
            failures += 1
        join_status, join_detail = run_join_check(cut, resolved, args.backend)
        print_result("Join integrity", join_status, join_detail)
        if join_status == "FAIL":
            failures += 1
        elif join_status == "SKIPPED":
            skipped.append("join integrity")
        pixel = video_pixel_format(cut)
        if pixel == "yuv420p":
            print_result("Pixel format", "PASS", pixel)
        else:
            print_result("Pixel format", "FAIL", pixel or "no video stream")
            failures += 1
        frame_check(cut, resolved_path if resolved_path.exists() else None, args.frames)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: verification command failed: {exc}", file=sys.stderr)
        return 1
    summary = "PASS" if failures == 0 else "FAIL"
    if skipped:
        print(f"Summary: {summary}; SKIPPED: {', '.join(skipped)}")
    else:
        print(f"Summary: {summary}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
