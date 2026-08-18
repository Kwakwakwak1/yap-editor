#!/usr/bin/env python3
"""Energy envelopes, boundary snapping, and finding fillers whisper cannot.

Run with:  python3 -m unittest discover -s tests

These work on synthetic envelopes so the suite stays stdlib-only and needs no
ffmpeg. `measure()` itself is validated against real audio -- see the module
docstring in pipeline/energy.py and the commit that added it.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from energy import (  # noqa: E402
    envelope,
    fillers,
    snap,
    word_gaps,
)


def levels(*runs: tuple[float, int]) -> list[float]:
    """`(dBFS, frame count)` pairs into a flat envelope."""
    out: list[float] = []
    for level, count in runs:
        out.extend([level] * count)
    return out


def word(text: str, start: float, end: float) -> dict:
    return {"word": text, "start": start, "end": end}


class Floor(unittest.TestCase):
    """The threshold has to come out of the data, not out of a constant."""

    def test_digital_silence_does_not_drag_the_floor_below_every_real_sound(self):
        # An AAC-encoded gap reads about -201 dBFS. Anchoring the floor to the
        # quietest frame put it at -184 -- below everything -- so every silent
        # gap counted as voiced. That is what the first version did to the
        # reference clip, reporting three fillers in a take that has none.
        env = envelope(levels((-201.0, 200), (-25.0, 800)))
        self.assertGreater(env["floor"], -120.0)
        self.assertLess(env["floor"], -25.0)

    def test_room_tone_sits_below_the_floor_not_above_it(self):
        # The opposite failure: a fixed offset below speech puts a -55 dBFS
        # room above a -60 floor and calls it speech.
        env = envelope(levels((-55.0, 400), (-25.0, 600)))
        self.assertGreater(env["floor"], -55.0)
        self.assertLess(env["floor"], -25.0)

    def test_speech_is_a_median_so_one_bang_does_not_define_it(self):
        env = envelope(levels((-60.0, 200), (-25.0, 700), (-3.0, 5)))
        self.assertLess(abs(env["speech"] - (-25.0)), 2.0)

    def test_an_empty_measurement_is_not_a_crash(self):
        env = envelope([])
        self.assertEqual(env["levels"], [])
        self.assertEqual(env["speech"], -120.0)


class Snap(unittest.TestCase):
    """Cutting on a word boundary cuts mid-breath."""

    def setUp(self):
        # Quiet trough centred at frame 50 (0.50s), speech either side.
        self.env = envelope(levels((-25.0, 45), (-70.0, 10), (-25.0, 45)))

    def test_a_boundary_moves_to_the_quietest_moment_near_it(self):
        moved = snap(0.47, self.env)
        self.assertGreaterEqual(moved, 0.45)
        self.assertLess(moved, 0.55)

    def test_it_never_moves_further_than_the_window(self):
        # Beyond the window the cut stops being the one the editor chose.
        moved = snap(1.00, self.env, window_ms=120)
        self.assertLessEqual(abs(moved - 1.00), 0.12)

    def test_no_envelope_means_the_boundary_the_editor_asked_for(self):
        self.assertEqual(snap(3.21, {"levels": []}), 3.21)
        self.assertEqual(snap(3.21, {}), 3.21)

    def test_a_boundary_past_the_end_of_the_audio_is_left_alone(self):
        self.assertEqual(snap(99.0, self.env), 99.0)


class WordGaps(unittest.TestCase):
    def test_only_gaps_long_enough_to_hold_something(self):
        words = [word("a", 0.0, 0.30), word("b", 0.35, 0.60), word("c", 1.10, 1.40)]
        # 50ms is the space between two words; 500ms is a pause.
        self.assertEqual(word_gaps(words), [(0.60, 1.10)])

    def test_a_malformed_word_is_skipped_not_fatal(self):
        words = [word("a", 0.0, 0.3), {"word": "broken"}, word("c", 1.0, 1.3)]
        self.assertEqual(word_gaps(words), [])


class Fillers(unittest.TestCase):
    """What an um IS, mechanically: energy where the transcript has no words."""

    def test_a_voiced_region_in_an_empty_gap_is_a_filler(self):
        # Words either side, and sound in the middle where whisper heard none.
        env = envelope(levels((-25.0, 100), (-70.0, 20), (-25.0, 30),
                              (-70.0, 20), (-25.0, 100)))
        # The gap is the 70 frames between the words, 1.00-1.70. Letting the
        # trailing speech fall inside it -- which the first draft of this test
        # did -- measures the speech and calls it a filler.
        words = [word("before", 0.0, 1.00), word("after", 1.70, 2.70)]
        found = fillers(words, env)

        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0]["from"], 1.20, places=2)
        self.assertAlmostEqual(found[0]["to"], 1.50, places=2)
        self.assertGreater(found[0]["voiced_ratio"], 0.2)

    def test_a_genuine_pause_is_left_alone(self):
        # Pauses carry meaning, and cutting them all is how an edit starts
        # sounding like a machine made it.
        env = envelope(levels((-25.0, 100), (-70.0, 70), (-25.0, 100)))
        words = [word("before", 0.0, 1.00), word("after", 1.70, 2.70)]
        self.assertEqual(fillers(words, env), [])

    def test_a_click_is_not_a_syllable(self):
        # 30ms of energy is a chair or a lip smack, not an "um".
        env = envelope(levels((-25.0, 100), (-70.0, 30), (-25.0, 3),
                              (-70.0, 30), (-25.0, 100)))
        words = [word("before", 0.0, 1.00), word("after", 1.63, 2.63)]
        self.assertEqual(fillers(words, env), [])

    def test_a_gap_shorter_than_the_minimum_is_not_examined(self):
        env = envelope(levels((-25.0, 100), (-70.0, 5), (-25.0, 100)))
        words = [word("before", 0.0, 1.00), word("after", 1.05, 2.05)]
        self.assertEqual(fillers(words, env), [])

    def test_no_envelope_finds_nothing_rather_than_guessing(self):
        words = [word("before", 0.0, 1.0), word("after", 2.0, 3.0)]
        self.assertEqual(fillers(words, {"levels": []}), [])

    def test_the_report_says_where_and_how_much(self):
        env = envelope(levels((-25.0, 100), (-70.0, 20), (-25.0, 30),
                              (-70.0, 20), (-25.0, 100)))
        words = [word("before", 0.0, 1.00), word("after", 1.70, 2.70)]
        found = fillers(words, env)[0]
        for key in ("from", "to", "gap", "voiced_ratio"):
            self.assertIn(key, found)
        self.assertLess(found["from"], found["to"])


if __name__ == "__main__":
    unittest.main()
