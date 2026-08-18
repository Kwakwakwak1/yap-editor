#!/usr/bin/env python3
"""Pure logic behind reel verification.

The ffmpeg-facing parts (band_stats, measure_loudness) are exercised by running
verify_reel.py against a real render; these cover the decisions it makes.
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from verify_reel import (  # noqa: E402
    control_time,
    cue_windows,
    expected_reel_duration,
    parse_band,
    parse_canvas,
    sample_times,
)


class CueWindows(unittest.TestCase):
    def test_sorts_and_keeps_positive_spans(self):
        cues = [
            {"from": 5.0, "to": 6.0, "text": "b"},
            {"from": 1.0, "to": 2.0, "text": "a"},
        ]
        self.assertEqual(cue_windows(cues), [(1.0, 2.0), (5.0, 6.0)])

    def test_drops_zero_and_negative_spans(self):
        cues = [{"from": 1.0, "to": 1.0}, {"from": 3.0, "to": 2.0}, {"from": 4.0, "to": 5.0}]
        self.assertEqual(cue_windows(cues), [(4.0, 5.0)])

    def test_malformed_cue_is_skipped(self):
        cues = [{"from": "x", "to": 2.0}, {"to": 3.0}, {"from": 4.0, "to": 5.0}]
        self.assertEqual(cue_windows(cues), [(4.0, 5.0)])


class SampleTimes(unittest.TestCase):
    def test_spreads_across_the_reel_rather_than_taking_the_first_n(self):
        # Ten cues; sampling the first three would only prove the opening rendered.
        windows = [(float(i), float(i) + 0.5) for i in range(10)]
        times = sample_times(windows, count=3)
        self.assertEqual(len(times), 3)
        self.assertAlmostEqual(times[0], 0.25)
        self.assertAlmostEqual(times[-1], 9.25)
        self.assertGreater(times[1], times[0])
        self.assertGreater(times[2], times[1])

    def test_uses_every_cue_when_there_are_fewer_than_requested(self):
        windows = [(0.0, 1.0), (2.0, 3.0)]
        self.assertEqual(sample_times(windows, count=3), [0.5, 2.5])

    def test_no_cues_yields_no_samples(self):
        self.assertEqual(sample_times([]), [])

    def test_samples_are_inside_their_cue(self):
        windows = [(0.0, 0.4), (5.0, 5.2), (11.0, 12.0)]
        for at in sample_times(windows):
            self.assertTrue(
                any(start <= at <= end for start, end in windows),
                f"{at} fell outside every cue",
            )


class ControlTime(unittest.TestCase):
    def test_finds_the_widest_uncaptioned_gap(self):
        windows = [(0.0, 1.0), (1.2, 2.0), (6.0, 7.0)]
        # Gaps: 1.0-1.2 (too small), 2.0-6.0 (widest).
        self.assertAlmostEqual(control_time(windows, 8.0), 4.0)

    def test_uses_the_tail_after_the_last_cue(self):
        windows = [(0.0, 1.0)]
        self.assertAlmostEqual(control_time(windows, 5.0), 3.0)

    def test_returns_none_when_captioned_wall_to_wall(self):
        windows = [(0.0, 5.0), (5.0, 10.0)]
        self.assertIsNone(control_time(windows, 10.0))

    def test_ignores_gaps_below_the_minimum(self):
        windows = [(0.0, 1.0), (1.1, 2.0)]
        self.assertIsNone(control_time(windows, 2.0, minimum_gap=0.4))

    def test_overlapping_cues_do_not_invent_a_gap(self):
        # A cue fully inside another must not leave `cursor` behind it.
        windows = [(0.0, 5.0), (1.0, 2.0)]
        self.assertIsNone(control_time(windows, 5.0))


class ExpectedReelDuration(unittest.TestCase):
    def test_defaults_to_the_cut_duration(self):
        self.assertAlmostEqual(expected_reel_duration({"actual_duration": 17.61}, {}), 17.61)

    def test_falls_back_to_planned_duration(self):
        self.assertAlmostEqual(expected_reel_duration({"planned_duration": 12.5}, {}), 12.5)

    def test_adds_an_endcard(self):
        style = {"furniture": {"endcard": {"durationSeconds": 1.6}}}
        self.assertAlmostEqual(expected_reel_duration({"actual_duration": 10.0}, style), 11.6)

    def test_subtracts_transition_overlap(self):
        style = {"transitions": {"totalOverlapSeconds": 0.5}}
        self.assertAlmostEqual(expected_reel_duration({"actual_duration": 10.0}, style), 9.5)

    def test_endcard_present_but_omitted_adds_nothing(self):
        # resolve_style sets the block to null when the brand has no endcard asset.
        style = {"furniture": {"endcard": None}}
        self.assertAlmostEqual(expected_reel_duration({"actual_duration": 10.0}, style), 10.0)

    def test_no_duration_anywhere_yields_zero_so_the_check_skips(self):
        self.assertEqual(expected_reel_duration({}, {}), 0.0)


class ArgumentParsing(unittest.TestCase):
    def test_band_round_trip(self):
        self.assertEqual(parse_band("0.62,0.88"), (0.62, 0.88))

    def test_band_rejects_inverted_range(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_band("0.9,0.1")

    def test_band_rejects_out_of_range(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_band("-0.1,0.5")

    def test_band_rejects_nonsense(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_band("bottom")

    def test_canvas_round_trip(self):
        self.assertEqual(parse_canvas("1080x1920"), (1080, 1920))

    def test_canvas_rejects_nonsense(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_canvas("1080*1920")


if __name__ == "__main__":
    unittest.main()
