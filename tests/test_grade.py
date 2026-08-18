#!/usr/bin/env python3
"""Compiling a style's grade into an ffmpeg filter chain.

This output is handed to a subprocess, so the tests care as much about what it
refuses as what it produces.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from grade import build_filters, clamp, filter_string  # noqa: E402


class NeutralGrades(unittest.TestCase):
    def test_no_grade_emits_nothing(self):
        # A style with no grade must not pay for a colour pass, and must not
        # change a single pixel of the cut.
        self.assertEqual(filter_string(None), "")
        self.assertEqual(filter_string({}), "")

    def test_an_all_neutral_grade_emits_nothing(self):
        neutral = {
            "exposure": 0, "contrast": 1, "saturation": 1,
            "temperature": 0, "tint": 0,
            "lift": [0, 0, 0], "gain": [1, 1, 1],
            "vignette": 0, "sharpen": 0, "grain": 0,
        }
        self.assertEqual(filter_string(neutral), "")

    def test_one_knob_emits_one_filter(self):
        self.assertEqual(filter_string({"saturation": 1.2}), "eq=saturation=1.2000")


class Neutrals(unittest.TestCase):
    """Getting a neutral wrong is not subtle."""

    def test_gain_is_neutral_at_one_not_zero(self):
        # Defaulting gain to zeros emits rh=-1.0 on every channel, which crushes
        # the highlights of any pack that simply did not mention gain. This was
        # a real bug, caught by reading the compiled output.
        out = filter_string({"lift": [0.02, 0.02, 0.02]})
        self.assertNotIn("rh=", out)
        self.assertIn("rs=0.0200", out)

    def test_lift_is_neutral_at_zero(self):
        out = filter_string({"gain": [1.03, 1.0, 0.97]})
        self.assertNotIn("rs=", out)
        self.assertIn("rh=0.0300", out)

    def test_a_malformed_triplet_falls_back_to_neutral(self):
        self.assertEqual(filter_string({"gain": "oops"}), "")
        self.assertEqual(filter_string({"lift": [1, 2]}), "")


class Clamping(unittest.TestCase):
    """The output reaches a subprocess. Every value is bounded."""

    def test_a_value_past_its_range_is_clamped(self):
        self.assertEqual(clamp(99, -1.0, 1.0, 0.0), 1.0)
        self.assertEqual(clamp(-99, -1.0, 1.0, 0.0), -1.0)

    def test_a_string_falls_back_to_neutral_rather_than_reaching_ffmpeg(self):
        # The injection shape: a value that is not a number must never be
        # interpolated into the filter string.
        out = filter_string({"contrast": "1;rm -rf /"})
        self.assertNotIn("rm -rf", out)
        self.assertEqual(out, "")

    def test_nan_falls_back(self):
        self.assertEqual(clamp(float("nan"), 0.0, 1.0, 0.5), 0.5)

    def test_no_shell_metacharacters_survive_any_input(self):
        hostile = {
            "exposure": "$(whoami)", "contrast": "`id`", "saturation": "1|nc",
            "lift": ["'; DROP", 2, 3], "gain": [";", "&&", "||"],
            "vignette": "1 -f lavfi", "grain": "0;",
        }
        out = filter_string(hostile)
        for character in ";|&`$'\"":
            self.assertNotIn(character, out)


class FilterOrder(unittest.TestCase):
    """Order is not alphabetical and not arbitrary."""

    def test_grain_comes_last_so_it_is_not_sharpened(self):
        # Sharpened noise reads as compression artefacts rather than film.
        filters = build_filters({"sharpen": 0.5, "grain": 0.3})
        self.assertLess(
            next(i for i, f in enumerate(filters) if f.startswith("unsharp")),
            next(i for i, f in enumerate(filters) if f.startswith("noise")),
        )

    def test_colour_balance_precedes_eq(self):
        # Balance shapes the image; eq then stretches what balance produced.
        filters = build_filters({"lift": [0.02, 0, 0], "contrast": 1.2})
        self.assertLess(
            next(i for i, f in enumerate(filters) if f.startswith("colorbalance")),
            next(i for i, f in enumerate(filters) if f.startswith("eq")),
        )

    def test_sharpen_reads_a_graded_image(self):
        filters = build_filters({"saturation": 1.3, "sharpen": 0.4})
        self.assertLess(
            next(i for i, f in enumerate(filters) if f.startswith("eq")),
            next(i for i, f in enumerate(filters) if f.startswith("unsharp")),
        )


class ShippedPacks(unittest.TestCase):
    def test_the_two_catalog_grades_compile_to_different_chains(self):
        warm = filter_string({"temperature": 8, "saturation": 1.22, "contrast": 1.14})
        cool = filter_string({"temperature": -4, "saturation": 0.82, "contrast": 0.94})
        self.assertNotEqual(warm, cool)
        # Warm lifts red and drops blue; cool does the reverse.
        self.assertIn("rm=0.0240", warm)
        self.assertIn("rm=-0.0120", cool)
