#!/usr/bin/env python3
"""Verify a rendered reel -- the artifact that actually gets published.

pipeline/verify.py checks `build/<slug>/cut.mp4`, the *pre-render* cut. Duration,
loudness and pixel format are all measured before Remotion runs, so nothing has
ever checked the file that reaches the bucket. Every defect the renderer can
introduce -- captions that failed to draw, the wrong brand accent, a music bed
that moved integrated loudness, an endcard that changed the duration -- shipped
unverified.

This script closes that gap. It is deliberately separate from verify.py rather
than a flag on it: the two run at different stages, on different files, and with
different tolerances, and collapsing them would mean one script that silently
skips half its checks depending on which file it was handed.

Output format matches verify.py exactly (`Name: STATUS (detail)` plus a
`Summary:` line) because render_worker.py parses those lines, and treats any
check name it does not recognise as blocking. That default is what makes adding
checks here safe.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from common import ffprobe_json, load_json, measure_loudness, media_duration, repo_path, video_pixel_format

# A music bed legitimately shifts integrated loudness, so the reel is judged more
# loosely than the cut (verify.py uses +/-1.0 on a speech-only file).
LOUDNESS_TOLERANCE = 1.5
TRUE_PEAK_CEILING = -1.0
DURATION_TOLERANCE = 0.5

# Fraction of frame height the caption band occupies. PortraitFull anchors
# captions SAFE_BOTTOM=430px above a 1920px frame, i.e. a baseline at ~0.78H,
# with the text rising above it. This band brackets that generously; a style
# that moves its captions should pass its own band via --caption-band.
CAPTION_BAND = (0.62, 0.88)

# Luma at or above this in the caption band counts as "something bright is drawn
# here". White caption text is 255; a scrim over dark footage is far below.
BRIGHT_LUMA = 200.0


def print_result(name: str, status: str, detail: str) -> None:
    print(f"{name}: {status}{f' ({detail})' if detail else ''}")


def video_dimensions(path: Path) -> Tuple[int, int]:
    data = ffprobe_json(path, "stream=width,height,codec_type")
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return int(stream.get("width", 0)), int(stream.get("height", 0))
    return 0, 0


def expected_reel_duration(resolved: Dict[str, Any], style: Dict[str, Any]) -> float:
    """How long the reel should be, given the cut and whatever the style adds.

    Today that is just the cut: no style pack ships an endcard or an overlapping
    transition yet. Both are already accounted for so that when they land, the
    duration check does not start failing for a legitimate reason -- which is
    exactly how a check gets marked non-blocking and then ignored forever.
    """
    base = float(resolved.get("actual_duration") or resolved.get("planned_duration") or 0.0)
    if not base:
        return 0.0
    endcard = style.get("furniture", {}).get("endcard") or {}
    added = float(endcard.get("durationSeconds", 0.0) or 0.0)
    overlap = float(style.get("transitions", {}).get("totalOverlapSeconds", 0.0) or 0.0)
    return base + added - overlap


def cue_windows(cues: Sequence[Dict[str, Any]]) -> List[Tuple[float, float]]:
    windows = []
    for cue in cues:
        try:
            start, end = float(cue["from"]), float(cue["to"])
        except (KeyError, TypeError, ValueError):
            continue
        if end > start:
            windows.append((start, end))
    return sorted(windows)


def sample_times(windows: Sequence[Tuple[float, float]], count: int = 3) -> List[float]:
    """Midpoints of cues spread across the reel, not the first N in a row.

    Sampling the first three cues would only ever prove the opening rendered.
    """
    if not windows:
        return []
    if len(windows) <= count:
        chosen = list(windows)
    else:
        step = (len(windows) - 1) / (count - 1) if count > 1 else 0
        chosen = [windows[round(i * step)] for i in range(count)]
    return [round((start + end) / 2, 3) for start, end in chosen]


def control_time(windows: Sequence[Tuple[float, float]], duration: float, minimum_gap: float = 0.4) -> Optional[float]:
    """A moment with no caption on screen, to compare the caption band against.

    Without it a bright shot reads the same as drawn text. Returns None when the
    reel is captioned wall to wall, and the caller falls back to an absolute
    brightness threshold.
    """
    gaps: List[Tuple[float, float]] = []
    cursor = 0.0
    for start, end in windows:
        if start - cursor >= minimum_gap:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if duration - cursor >= minimum_gap:
        gaps.append((cursor, duration))
    if not gaps:
        return None
    widest = max(gaps, key=lambda gap: gap[1] - gap[0])
    return round((widest[0] + widest[1]) / 2, 3)


_STAT_LINE = re.compile(r"lavfi\.signalstats\.(\w+)=([-\d.]+)")


def band_stats(path: Path, at: float, band: Tuple[float, float]) -> Dict[str, float]:
    """Luma statistics for the caption band of a single frame."""
    low, high = band
    height_expr = f"ih*{high - low:.4f}"
    y_expr = f"ih*{low:.4f}"
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1",
            "-vf", f"crop=iw:{height_expr}:0:{y_expr},signalstats,metadata=print:file=-",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    stats = {key: float(value) for key, value in _STAT_LINE.findall(result.stdout)}
    if not stats:
        raise RuntimeError(f"signalstats produced no measurement at {at:.3f}s")
    return stats


def caption_presence_check(
    reel: Path, cues: Sequence[Dict[str, Any]], duration: float, band: Tuple[float, float]
) -> Tuple[str, str]:
    """Assert something is actually drawn in the caption band.

    This is the cheap insurance against the failure class that patch_accent's
    read-back was invented to catch: a render that succeeds, exits zero, and
    produces a file with no captions in it.
    """
    windows = cue_windows(cues)
    if not windows:
        return "SKIPPED", "no caption cues to sample"
    times = sample_times(windows)
    try:
        samples = {at: band_stats(reel, at, band) for at in times}
        control_at = control_time(windows, duration)
        control = band_stats(reel, control_at, band) if control_at is not None else None
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        return "SKIPPED", f"could not sample frames: {exc}"

    bright = [at for at, stat in samples.items() if stat.get("YMAX", 0.0) >= BRIGHT_LUMA]
    detail_times = ", ".join(f"{at:.2f}s" for at in times)

    if control is not None:
        # Text raises the band's average luma above the same band with no cue.
        lifted = [
            at for at, stat in samples.items()
            if stat.get("YAVG", 0.0) - control.get("YAVG", 0.0) > 1.0
        ]
        if lifted:
            return "PASS", f"{len(lifted)}/{len(times)} sampled cues brighten the caption band vs {control_at:.2f}s"
        if bright:
            return "PASS", f"{len(bright)}/{len(times)} sampled cues reach luma {BRIGHT_LUMA:.0f}+ (no lift vs control)"
        return "FAIL", f"caption band at {detail_times} matches the uncaptioned frame at {control_at:.2f}s"

    if bright:
        return "PASS", f"{len(bright)}/{len(times)} sampled cues reach luma {BRIGHT_LUMA:.0f}+ (no uncaptioned frame to compare)"
    return "FAIL", f"caption band never reaches luma {BRIGHT_LUMA:.0f} at {detail_times}"


def parse_band(value: str) -> Tuple[float, float]:
    try:
        low, high = (float(part) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected two comma-separated fractions, e.g. 0.62,0.88") from exc
    if not 0.0 <= low < high <= 1.0:
        raise argparse.ArgumentTypeError("band must satisfy 0 <= low < high <= 1")
    return low, high


def parse_canvas(value: str) -> Tuple[int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", value.strip())
    if not match:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT, e.g. 1080x1920")
    return int(match.group(1)), int(match.group(2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reel", type=Path, help="the rendered reel, e.g. out/<slug>-reel.mp4")
    parser.add_argument("--resolved", type=Path, help="cuts.resolved.json (defaults beside the cut)")
    parser.add_argument("--props", type=Path, help="staged props.json, for caption cues and the style spec")
    parser.add_argument("--expect-duration", type=float, help="override the expected duration in seconds")
    parser.add_argument("--canvas", type=parse_canvas, help="expected WIDTHxHEIGHT, e.g. 1080x1920")
    parser.add_argument("--caption-band", type=parse_band, default=CAPTION_BAND)
    args = parser.parse_args()

    reel = repo_path(str(args.reel))
    if not reel.exists():
        print(f"ERROR: reel not found: {args.reel}", file=sys.stderr)
        return 1

    resolved: Dict[str, Any] = {}
    if args.resolved:
        try:
            resolved = load_json(repo_path(str(args.resolved)))
        except (OSError, ValueError) as exc:
            print(f"ERROR: could not read resolved plan: {exc}", file=sys.stderr)
            return 1

    props: Dict[str, Any] = {}
    if args.props:
        try:
            props = load_json(repo_path(str(args.props)))
        except (OSError, ValueError) as exc:
            print(f"ERROR: could not read props: {exc}", file=sys.stderr)
            return 1

    style = props.get("style", {}) if isinstance(props.get("style"), dict) else {}
    cues = props.get("captions", []) if isinstance(props.get("captions"), list) else []

    failures = 0
    skipped: List[str] = []
    try:
        duration = media_duration(reel)

        expected = args.expect_duration if args.expect_duration is not None else expected_reel_duration(resolved, style)
        if not expected:
            print_result("Reel duration", "SKIPPED", "no expected duration (pass --resolved or --expect-duration)")
            skipped.append("reel duration")
        elif abs(duration - expected) <= DURATION_TOLERANCE:
            print_result("Reel duration", "PASS", f"actual={duration:.3f}s expected={expected:.3f}s")
        else:
            print_result("Reel duration", "FAIL", f"actual={duration:.3f}s expected={expected:.3f}s ±{DURATION_TOLERANCE}")
            failures += 1

        loudness = resolved.get("loudness", {})
        target_i = float(loudness.get("i", -14))
        try:
            measurement = measure_loudness(
                reel, target_i, float(loudness.get("tp", -1.5)), float(loudness.get("lra", 11))
            )
        except RuntimeError as exc:
            print_result("Reel loudness", "FAIL", str(exc))
            failures += 1
        else:
            measured_i = measurement.get("input_i")
            measured_tp = measurement.get("input_tp")
            if measured_i is None:
                print_result("Reel loudness", "FAIL", "loudnorm returned no input_i")
                failures += 1
            elif abs(measured_i - target_i) <= LOUDNESS_TOLERANCE:
                print_result("Reel loudness", "PASS", f"input_i={measured_i:.2f} LUFS, target={target_i:.2f} ±{LOUDNESS_TOLERANCE}")
            else:
                print_result("Reel loudness", "FAIL", f"input_i={measured_i:.2f} LUFS, target={target_i:.2f} ±{LOUDNESS_TOLERANCE}")
                failures += 1
            if measured_tp is None:
                print_result("Reel true peak", "SKIPPED", "loudnorm returned no input_tp")
                skipped.append("reel true peak")
            elif measured_tp <= TRUE_PEAK_CEILING:
                print_result("Reel true peak", "PASS", f"input_tp={measured_tp:.2f} dBTP, ceiling={TRUE_PEAK_CEILING:.1f}")
            else:
                print_result("Reel true peak", "FAIL", f"input_tp={measured_tp:.2f} dBTP exceeds {TRUE_PEAK_CEILING:.1f}")
                failures += 1

        pixel = video_pixel_format(reel)
        if pixel == "yuv420p":
            print_result("Reel pixel format", "PASS", pixel)
        else:
            print_result("Reel pixel format", "FAIL", pixel or "no video stream")
            failures += 1

        width, height = video_dimensions(reel)
        expected_canvas = args.canvas
        if expected_canvas is None and style.get("render"):
            render_spec = style["render"]
            if render_spec.get("width") and render_spec.get("height"):
                expected_canvas = (int(render_spec["width"]), int(render_spec["height"]))
        if expected_canvas is None:
            print_result("Reel resolution", "SKIPPED", f"{width}x{height}, nothing to compare against")
            skipped.append("reel resolution")
        elif (width, height) == expected_canvas:
            print_result("Reel resolution", "PASS", f"{width}x{height}")
        else:
            print_result("Reel resolution", "FAIL", f"{width}x{height}, expected {expected_canvas[0]}x{expected_canvas[1]}")
            failures += 1

        caption_status, caption_detail = caption_presence_check(reel, cues, duration, args.caption_band)
        print_result("Caption presence", caption_status, caption_detail)
        if caption_status == "FAIL":
            failures += 1
        elif caption_status == "SKIPPED":
            skipped.append("caption presence")

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
