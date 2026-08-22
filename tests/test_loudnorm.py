"""The loudnorm filter assemble.py hands ffmpeg.

A reel is normalised once, at assembly, and verify.py holds the result to
+/-1.0 LUFS of target. A single loudnorm pass does not meet that: with no
statistics for the file up front it normalises the opening seconds blind, which
on a short reel is most of the file. Measured on job 20260822-kwakwakwak-g2fjbejd,
a 12s cut: -15.86 LUFS against -14, a blocking verify failure, with a true peak
of -1.30 past the -1.5 ceiling the same pass was told to hold. The identical
file, normalised with the analysis pass's numbers fed back in, came out at
-14.17.

These cover the filter string rather than the audio: the pipeline is stdlib +
ffmpeg and these tests have to run on minik's bare interpreter, so what is
testable here is the contract with ffmpeg -- that a measurement is used when
there is one, and that a partial or missing one degrades to a pass that works
rather than to a filter ffmpeg rejects.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from assemble import loudnorm_filter  # noqa: E402


MEASURED = {
    "input_i": -15.86,
    "input_tp": -1.30,
    "input_lra": 2.90,
    "input_thresh": -25.97,
    "target_offset": 0.80,
}


class LoudnormFilterTest(unittest.TestCase):
    def test_single_pass_when_nothing_was_measured(self):
        self.assertEqual(
            loudnorm_filter(-14, -1.5, 11),
            "loudnorm=I=-14:TP=-1.5:LRA=11",
        )

    def test_feeds_every_measured_value_back_to_ffmpeg(self):
        built = loudnorm_filter(-14, -1.5, 11, MEASURED)
        for expected in (
            "measured_I=-15.86",
            "measured_TP=-1.3",
            "measured_LRA=2.9",
            "measured_thresh=-25.97",
            "offset=0.8",
        ):
            self.assertIn(expected, built)

    def test_asks_for_linear_normalisation(self):
        # One constant gain over the whole file, which is what leaves speech
        # dynamics alone. ffmpeg drops to dynamic by itself if that gain would
        # breach the true-peak ceiling, so this is a preference it may override
        # -- but dynamic *with* the measurements still beats dynamic without.
        self.assertIn("linear=true", loudnorm_filter(-14, -1.5, 11, MEASURED))

    def test_keeps_the_targets_alongside_the_measurements(self):
        built = loudnorm_filter(-14, -1.5, 11, MEASURED)
        self.assertTrue(built.startswith("loudnorm=I=-14:TP=-1.5:LRA=11"))

    def test_honours_a_plan_that_targets_something_other_than_minus_14(self):
        built = loudnorm_filter(-16, -2.0, 7, MEASURED)
        self.assertTrue(built.startswith("loudnorm=I=-16:TP=-2.0:LRA=7"))
        self.assertIn("measured_I=-15.86", built)

    def test_falls_back_rather_than_building_a_filter_ffmpeg_rejects(self):
        # ffmpeg needs all four measured_* values together; three of them is not
        # three-quarters of a second pass, it is a filter that errors out. A
        # partial measurement has to degrade to the single pass instead.
        for missing in ("input_i", "input_tp", "input_lra", "input_thresh"):
            partial = {k: v for k, v in MEASURED.items() if k != missing}
            with self.subTest(missing=missing):
                self.assertEqual(
                    loudnorm_filter(-14, -1.5, 11, partial),
                    "loudnorm=I=-14:TP=-1.5:LRA=11",
                )

    def test_uses_a_measurement_that_lacks_only_the_offset(self):
        # target_offset is ffmpeg's own correction for the gap between what it
        # predicts and what it measures. Missing it costs a little accuracy;
        # the second pass is still worth running.
        without = {k: v for k, v in MEASURED.items() if k != "target_offset"}
        built = loudnorm_filter(-14, -1.5, 11, without)
        self.assertIn("measured_I=-15.86", built)
        self.assertNotIn("offset=", built)

    def test_empty_measurement_is_not_treated_as_a_measurement(self):
        self.assertEqual(
            loudnorm_filter(-14, -1.5, 11, {}),
            "loudnorm=I=-14:TP=-1.5:LRA=11",
        )


if __name__ == "__main__":
    unittest.main()
