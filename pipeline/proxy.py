#!/usr/bin/env python3
"""A small, seek-friendly stand-in for a take, for editing against in a browser.

    python3 pipeline/proxy.py media/<slug>/A.mov -o build/<slug>/A.proxy.mp4

The footage lives on the T9 drive and its bytes never leave it -- `LibraryItem`
in the API says so outright -- so an editor running in a browser has no frames
of it to show. This makes some.

THE PROPERTY THAT MATTERS IS NOT THE FILE SIZE.

It is that proxy time equals source time. A boundary set at 11.88s against the
proxy has to mean 11.88s in the source, or every cut made in the editor is
quietly wrong by however far the two drift -- and nothing downstream can detect
it, because the cut plan is just numbers and they will all look reasonable. So
the duration is checked against the source, and a proxy that fails is deleted
rather than returned. No proxy is a worse editor. A lying proxy is a worse reel.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import media_duration, repo_path, run_command  # noqa: E402

#: Encoders round the final frame. This is slack for that arithmetic, not for
#: drift: 0.05s is under two frames at 30fps, and far below anything a person
#: could set as a boundary by hand.
DURATION_TOLERANCE_S = 0.05


class ProxyDrift(RuntimeError):
    """The proxy does not represent the source, so there is no usable proxy.

    One type for every way that can happen -- a length mismatch, a file ffmpeg
    never wrote, a source whose duration cannot be read. The caller's response
    is the same in all three cases: carry on without one.
    """


def proxy_argv(
    source: Path,
    out: Path,
    height: int = 480,
    keyframe_seconds: float = 1.0,
) -> List[str]:
    """The ffmpeg call, as its own function so a test can read it.

    `-2` in the scale filter rather than `-1`: h264 requires even dimensions,
    and `-1` will happily produce an odd one on some source aspects and fail.

    The forced keyframes are not an optimisation. Phone footage is long-GOP, and
    seeking it in a browser without dense keyframes is a slideshow -- scrubbing
    is the entire point of the file.

    There is deliberately no `-r`, no `-t` and no `-ss`. Each of those moves the
    timeline, and the timeline is what this file exists to preserve.
    """
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"scale=-2:{height}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-force_key_frames", f"expr:gte(t,n_forced*{keyframe_seconds})",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        str(out),
    ]


def make_proxy(
    source: Path,
    out: Path,
    run: Optional[Callable[[List[str]], Any]] = None,
    duration: Optional[Callable[[Path], float]] = None,
) -> Path:
    """Write a proxy for `source` at `out`, or raise `ProxyDrift`.

    `run` and `duration` are injectable so the tests touch neither ffmpeg nor
    the filesystem's video decoder -- the same reason render_worker.py injects
    its readers and writers.
    """
    run = run or run_command
    duration = duration or media_duration

    try:
        source_seconds = float(duration(source))
    except RuntimeError as exc:
        raise ProxyDrift(f"could not read the duration of {source}: {exc}") from None

    out.parent.mkdir(parents=True, exist_ok=True)
    run(proxy_argv(source, out))

    if not out.exists():
        raise ProxyDrift(f"ffmpeg reported success but wrote no file at {out}")

    try:
        proxy_seconds = float(duration(out))
    except RuntimeError as exc:
        out.unlink(missing_ok=True)
        raise ProxyDrift(f"could not read the duration of the proxy: {exc}") from None

    if abs(proxy_seconds - source_seconds) > DURATION_TOLERANCE_S:
        out.unlink(missing_ok=True)
        raise ProxyDrift(
            f"proxy is {proxy_seconds:.2f}s against a source of "
            f"{source_seconds:.2f}s, past the {DURATION_TOLERANCE_S}s "
            f"tolerance - a boundary set on it would not mean what it says"
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--height", type=int, default=480)
    args = parser.parse_args()

    try:
        out = make_proxy(repo_path(str(args.source)), repo_path(str(args.output)))
    except ProxyDrift as exc:
        # stderr, and a non-zero exit: the caller carries on without a proxy,
        # and this is the only record of why there is not one.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
