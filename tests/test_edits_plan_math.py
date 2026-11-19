"""The arithmetic of cutting an approved plan into Edits clips.

These are the decisions a reviewer can check without ffmpeg: which file a beat
becomes, where its padded window falls, which words belong to it, and whether
there is room on disk.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from edits_export import (  # noqa: E402
    DISK_FACTOR,
    check_disk,
    clip_name,
    clip_windows,
    clip_words,
    estimate_bytes,
)


def seg(take, start, end, beat="b"):
    return {"take": take, "start": start, "end": end, "beat": beat}


class ClipNameTest(unittest.TestCase):
    def test_position_and_slugged_beat(self):
        self.assertEqual(clip_name(1, "hook"), "01-hook.mov")
        self.assertEqual(clip_name(2, "Point 2: the price!"), "02-point-2-the-price.mov")
        self.assertEqual(clip_name(12, ""), "12-segment.mov")
        self.assertEqual(clip_name(3, None), "03-segment.mov")


class ClipWindowsTest(unittest.TestCase):
    def test_padding_is_per_segment_and_order_is_kept(self):
        windows = clip_windows(
            [seg("B", 2.10, 6.60, "hook"), seg("A", 1.00, 2.00)],
            (0.07, 0.07), {"A": 30.0, "B": 30.0},
        )
        self.assertEqual([w["take"] for w in windows], ["B", "A"])
        self.assertAlmostEqual(windows[0]["clip_start"], 2.03)
        self.assertAlmostEqual(windows[0]["clip_end"], 6.67)
        self.assertAlmostEqual(windows[0]["duration"], 4.64)
        self.assertEqual(windows[0]["source_start"], 2.10)

    def test_padding_is_clamped_to_the_take(self):
        windows = clip_windows([seg("A", 0.02, 9.98)], (0.07, 0.07), {"A": 10.0})
        self.assertEqual(windows[0]["clip_start"], 0.0)
        self.assertEqual(windows[0]["clip_end"], 10.0)

    def test_an_empty_window_is_an_error(self):
        with self.assertRaises(ValueError):
            clip_windows([seg("A", 12.0, 13.0)], (0.0, 0.0), {"A": 10.0})


class ClipWordsTest(unittest.TestCase):
    WORDS = [
        {"start": 1.00, "end": 1.20, "word": "before"},
        {"start": 2.05, "end": 2.40, "word": "Why"},
        {"start": 2.45, "end": 2.70, "word": "kwakwakwak?"},
        {"start": 6.60, "end": 6.90, "word": "straddles"},
        {"start": 7.00, "end": 7.30, "word": "after"},
    ]

    def test_words_whose_midpoint_is_inside_are_kept_and_shifted(self):
        out = clip_words(self.WORDS, 2.03, 6.67)
        self.assertEqual([w["text"] for w in out], ["Why", "kwakwakwak?"])
        self.assertEqual(out[0], {"from": 0.02, "to": 0.37, "text": "Why"})

    def test_a_word_straddling_the_end_goes_by_its_midpoint(self):
        out = clip_words(self.WORDS, 2.03, 6.80)
        self.assertEqual([w["text"] for w in out], ["Why", "kwakwakwak?", "straddles"])

    def test_a_word_starting_before_the_clip_is_kept_if_its_midpoint_is_inside(self):
        words = [{"start": 1.90, "end": 2.40, "word": "Why"}]   # midpoint 2.15, inside 2.03-6.67
        out = clip_words(words, 2.03, 6.67)
        self.assertEqual(out, [{"from": 0.0, "to": 0.37, "text": "Why"}])


class DiskTest(unittest.TestCase):
    def test_estimate_is_147_mbit_per_second(self):
        self.assertEqual(estimate_bytes(60), 1_102_500_000)

    def test_refuses_without_three_times_the_estimate(self):
        needed = estimate_bytes(60)
        check_disk(Path("."), needed, free_bytes=needed * DISK_FACTOR)
        with self.assertRaises(RuntimeError):
            check_disk(Path("."), needed, free_bytes=needed * DISK_FACTOR - 1)


if __name__ == "__main__":
    unittest.main()
