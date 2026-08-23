#!/usr/bin/env python3
"""A small, seek-friendly stand-in for a take, for editing against in a browser.

Run with:  python3 -m unittest discover -s tests

The source footage lives on the T9 drive and its bytes never leave it, so an
editor in a browser has no frames to show. A proxy is how it gets some.

The property that matters is not the file size. It is that PROXY TIME EQUALS
SOURCE TIME: a boundary set at 11.88s against the proxy has to mean 11.88s in
the source, or every cut the editor produces is quietly wrong by however much
the two drift. Nothing downstream can detect that, which is why it is checked
here and why a proxy that fails the check is deleted rather than returned.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from proxy import (  # noqa: E402
    DURATION_TOLERANCE_S,
    ProxyDrift,
    make_proxy,
    proxy_argv,
)


class FakeRun:
    """Stands in for the ffmpeg call, and records what it was asked to do."""

    def __init__(self, touch=True):
        self.calls = []
        self.touch = touch

    def __call__(self, argv):
        self.calls.append(argv)
        if self.touch:
            Path(argv[-1]).write_bytes(b"not really an mp4")


class ProxyArgv(unittest.TestCase):
    def test_never_changes_the_frame_rate_or_the_length(self):
        # The one property the whole feature rests on. -r would resample the
        # timeline, -t and -ss would move it. None may appear, ever.
        argv = proxy_argv(Path("media/s/A.mov"), Path("build/s/A.proxy.mp4"))

        for forbidden in ("-r", "-t", "-ss"):
            self.assertNotIn(forbidden, argv)
        self.assertNotIn("setpts", " ".join(argv))

    def test_scales_to_480_keeping_aspect_and_even_dimensions(self):
        # -2 rather than -1: h264 needs even dimensions, and a filter that
        # refuses an odd number is the difference between a proxy and an ffmpeg
        # error on some source aspects.
        argv = proxy_argv(Path("a.mov"), Path("b.mp4"))

        self.assertIn("scale=-2:480", " ".join(argv))

    def test_forces_a_keyframe_every_second(self):
        # Phone footage is long-GOP. Seeking it in a browser without dense
        # keyframes is a slideshow, and scrubbing is the entire point.
        argv = proxy_argv(Path("a.mov"), Path("b.mp4"), keyframe_seconds=1.0)

        self.assertIn("expr:gte(t,n_forced*1.0)", " ".join(argv))

    def test_takes_audio_when_there_is_some_and_tolerates_none(self):
        # `0:a:0?` -- the trailing question mark. A screen recording with no
        # audio track is a take like any other and must not fail here.
        argv = proxy_argv(Path("a.mov"), Path("b.mp4"))

        self.assertIn("0:a:0?", argv)

    def test_starts_fast_so_a_browser_can_play_before_it_finishes(self):
        argv = proxy_argv(Path("a.mov"), Path("b.mp4"))

        self.assertIn("+faststart", argv)


class MakeProxy(unittest.TestCase):
    def test_returns_the_proxy_when_its_duration_matches_the_source(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            run = FakeRun()
            out = make_proxy(tmp / "A.mov", tmp / "A.proxy.mp4", run=run,
                             duration=lambda path: 30.72)

            self.assertTrue(out.exists())
            self.assertEqual(len(run.calls), 1)

    def test_tolerates_a_rounding_difference_in_the_last_frame(self):
        # Encoders round the final frame. 0.05s is under two frames at 30fps and
        # far below anything a person could set as a boundary by hand, so this
        # is slack for arithmetic rather than for drift.
        durations = iter([30.72, 30.72 + (DURATION_TOLERANCE_S / 2)])
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            out = make_proxy(tmp / "A.mov", tmp / "A.proxy.mp4", run=FakeRun(),
                             duration=lambda path: next(durations))

            self.assertTrue(out.exists())

    def test_raises_and_deletes_the_file_when_the_proxy_drifted(self):
        # Deleted, not just refused. A drifting proxy left on disk is one an
        # upload or a later run could still pick up, and its whole problem is
        # that nothing downstream can tell it is wrong.
        durations = iter([30.72, 30.20])
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            target = tmp / "A.proxy.mp4"

            with self.assertRaises(ProxyDrift) as caught:
                make_proxy(tmp / "A.mov", target, run=FakeRun(),
                           duration=lambda path: next(durations))

            self.assertFalse(target.exists())
            self.assertIn("30.72", str(caught.exception))
            self.assertIn("30.20", str(caught.exception))

    def test_raises_when_ffmpeg_produced_no_file_at_all(self):
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            with self.assertRaises(ProxyDrift):
                make_proxy(tmp / "A.mov", tmp / "A.proxy.mp4",
                           run=FakeRun(touch=False), duration=lambda path: 30.72)

    def test_raises_when_the_source_duration_cannot_be_read(self):
        # common.media_duration raises RuntimeError here. Letting it escape as
        # itself would give claim.py a different exception type to handle for
        # the same outcome: no usable proxy.
        def unreadable(path):
            raise RuntimeError("ffprobe did not return a duration")

        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            with self.assertRaises(ProxyDrift):
                make_proxy(tmp / "A.mov", tmp / "A.proxy.mp4", run=FakeRun(),
                           duration=unreadable)


if __name__ == "__main__":
    unittest.main()
