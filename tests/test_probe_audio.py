#!/usr/bin/env python3
"""Whether a take has an audio track, as a THREE-valued answer.

Run with:  python3 -m unittest discover -s tests

The third value is the whole point, and the API's own probe says why: "a probe
that did not run is not evidence of silence". A take ffprobe could not read must
not be refused as silent -- it must be let through, because the cost of refusing
a good take is worse than the cost of a legible failure two steps later.

This exists because a real job failed for want of it. A three-minute clip from a
pair of Meta glasses carried one video stream and no audio, mlx-whisper handed
it to ffmpeg, and the job died with two kilobytes of ffmpeg banner whose actual
sentence -- "Output file does not contain any stream" -- was the last line.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from probe_audio import SILENT, UNKNOWN, VOICED, audio_state, exit_code  # noqa: E402


class AudioState(unittest.TestCase):
    def test_a_take_with_an_audio_stream_is_voiced(self):
        self.assertIs(audio_state([{"codec_type": "video"}, {"codec_type": "audio"}]), VOICED)

    def test_a_take_with_streams_but_no_audio_is_silent(self):
        # The Meta-glasses case: video, and nothing else.
        self.assertIs(audio_state([{"codec_type": "video"}]), SILENT)

    def test_no_streams_at_all_is_unknown_rather_than_silent(self):
        # ffprobe missing, a file it could not open, a format it does not know.
        # "A probe that did not run is not evidence of silence" -- the same rule
        # the API's indexer states, and for the same reason.
        self.assertIs(audio_state([]), UNKNOWN)
        self.assertIs(audio_state(None), UNKNOWN)

    def test_an_audio_only_take_is_voiced(self):
        # Not a video, but not silent either, and nothing here needs pictures.
        self.assertIs(audio_state([{"codec_type": "audio"}]), VOICED)

    def test_a_stream_with_no_codec_type_does_not_count_as_audio(self):
        self.assertIs(audio_state([{"index": 0}]), SILENT)


class ExitCode(unittest.TestCase):
    """The contract claim.py reads. Only 1 may ever stop a job."""

    def test_voiced_is_zero(self):
        self.assertEqual(exit_code(VOICED), 0)

    def test_silent_is_one(self):
        self.assertEqual(exit_code(SILENT), 1)

    def test_unknown_is_two_so_the_caller_can_carry_on(self):
        # Distinct from both, deliberately: a caller that treated "could not
        # tell" as "silent" would refuse takes for the sin of being unreadable
        # by ffprobe, which is the failure the tri-state exists to prevent.
        self.assertEqual(exit_code(UNKNOWN), 2)


if __name__ == "__main__":
    unittest.main()
