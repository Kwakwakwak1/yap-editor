#!/usr/bin/env python3
"""Composite 1-indexed masks over a flat background and re-mux source audio."""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple


def require_dependencies() -> Tuple[Any, Any]:
    try:
        cv2 = importlib.import_module("cv2")
        numpy = importlib.import_module("numpy")
    except ImportError as exc:
        raise RuntimeError("missing composite dependency: opencv-python and numpy. Install the optional cutout lines in pipeline/requirements.txt") from exc
    return cv2, numpy


def background_colour(value: str) -> Tuple[int, int, int]:
    named = {"green": (0, 177, 64), "black": (0, 0, 0)}
    if value in named:
        return named[value]
    if value.startswith("#") and len(value) == 7:
        try:
            return int(value[5:7], 16), int(value[3:5], 16), int(value[1:3], 16)
        except ValueError:
            pass
    raise ValueError("background must be green, black, or #RRGGBB")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clip", type=Path)
    parser.add_argument("masks_dir", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--background", default="green")
    parser.add_argument("--erode", type=float, default=3)
    parser.add_argument("--feather", type=float, default=1.6)
    args = parser.parse_args()
    try:
        if not args.clip.exists():
            raise RuntimeError(f"clip not found: {args.clip}")
        if not args.masks_dir.exists():
            raise RuntimeError(f"masks directory not found: {args.masks_dir}")
        if args.erode < 0 or args.feather < 0:
            raise ValueError("erode and feather cannot be negative")
        cv2, numpy = require_dependencies()
        background = background_colour(args.background)
        capture = cv2.VideoCapture(str(args.clip))
        if not capture.isOpened():
            raise RuntimeError("opencv could not open the clip")
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
        qa_jumps: List[Dict[str, Any]] = []
        previous_area = None
        with tempfile.TemporaryDirectory(prefix="composite-") as temp_dir:
            silent = Path(temp_dir) / "silent.mp4"
            writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
            if not writer.isOpened():
                raise RuntimeError("opencv could not create the temporary video")
            frame_index = 0
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                frame_index += 1
                mask_path = args.masks_dir / f"f{frame_index:05d}.png"
                mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE) if mask_path.exists() else None
                if mask is None:
                    mask = numpy.zeros((height, width), dtype=numpy.uint8)
                    print(f"WARNING: missing mask for frame {frame_index}, rendering background only")
                elif mask.shape[:2] != (height, width):
                    mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
                area = float(numpy.count_nonzero(mask)) / float(width * height)
                if previous_area is not None:
                    jump = abs(area - previous_area) / max(previous_area, 1e-6)
                    if jump > 0.12:
                        qa_jumps.append({"frame": frame_index, "previous_area": round(previous_area, 6), "area": round(area, 6), "relative_jump": round(jump, 6)})
                previous_area = area
                if args.erode:
                    radius = max(1, int(round(args.erode)))
                    kernel = numpy.ones((radius * 2 + 1, radius * 2 + 1), dtype=numpy.uint8)
                    mask = cv2.erode(mask, kernel, iterations=1)
                if args.feather:
                    kernel_size = max(3, int(round(args.feather * 6)) | 1)
                    mask = cv2.GaussianBlur(mask, (kernel_size, kernel_size), args.feather)
                alpha = mask.astype(numpy.float32)[:, :, None] / 255.0
                background_frame = numpy.zeros_like(frame)
                background_frame[:, :] = background
                composite = (frame.astype(numpy.float32) * alpha + background_frame.astype(numpy.float32) * (1 - alpha)).astype(numpy.uint8)
                writer.write(composite)
            writer.release()
            capture.release()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(silent), "-i", str(args.clip),
                    "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                    "-shortest", str(args.output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg could not mux composite: {result.stderr.strip()}")
        qa_path = Path(str(args.output) + ".qa.json")
        qa_payload = {"output": args.output.name, "threshold": 0.12, "flagged_frames": qa_jumps}
        qa_path.write_text(json.dumps(qa_payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.output} with yuv420p video and original audio")
        print(f"QA flagged {len(qa_jumps)} adjacent-frame mask-area jump(s) over 12%; inspect those frames before shipping")
        print(f"Wrote {qa_path}")
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
