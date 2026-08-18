#!/usr/bin/env python3
"""Drafting a cut from a script: the best delivery of every line.

Run with:  python3 -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from align import align  # noqa: E402
from script_cut import MIN_COVERAGE, draft, summarise  # noqa: E402

SCRIPT = """\
Everyone overcooks salmon.
Pat the fillet completely dry.
Look at that flake.
"""


def spoken(text: str, step: float = 0.4) -> list[dict]:
    words, at = [], 0.0
    for word in text.split():
        words.append({"word": word, "start": round(at, 3), "end": round(at + 0.3, 3)})
        at += step
    return words


class BestOfEveryLine(unittest.TestCase):
    def test_the_cut_takes_each_line_from_whichever_take_delivered_it(self):
        # A says line 1 and fluffs the rest; B says lines 2 and 3. The point of
        # the whole feature is that the result is neither take.
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. and then uh"),
            "B": spoken("Pat the fillet completely dry. Look at that flake."),
        })
        plan = draft(alignment)

        self.assertTrue(plan["usable"])
        self.assertEqual([s["take"] for s in plan["segments"]], ["A", "B", "B"])
        self.assertEqual([s["line_index"] for s in plan["segments"]], [1, 2, 3])

    def test_segments_follow_the_script_not_the_footage(self):
        # B says the lines out of order. The cut still runs 1, 2, 3.
        alignment = align(SCRIPT, {
            "B": spoken(
                "Look at that flake. Everyone overcooks salmon. "
                "Pat the fillet completely dry."
            ),
        })
        plan = draft(alignment)
        self.assertEqual([s["line_index"] for s in plan["segments"]],
                         sorted(s["line_index"] for s in plan["segments"]))

    def test_a_higher_confidence_take_wins(self):
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. Pat the fillet completely dry. "
                        "Look at that flake."),
            "B": spoken("Everyone overcooks the salmon I guess. "
                        "Pat the fillet completely dry. Look at that flake."),
        })
        plan = draft(alignment)
        self.assertEqual(plan["segments"][0]["take"], "A")

    def test_a_tie_goes_to_the_tightest_delivery(self):
        # Two takes that both deliver every word are not equally good. A run-up
        # is not the distinction -- the span already starts at the first
        # matching word, so "um so anyway everyone overcooks salmon" and
        # "everyone overcooks salmon" produce identical spans.
        #
        # What does differ is a stumble INSIDE the line, which the span has to
        # include or the cut splices mid-sentence. A said line 2 with a
        # self-correction in the middle; B said it clean.
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. Pat the fillet uh sorry the "
                        "fillet completely dry. Look at that flake."),
            "B": spoken("Everyone overcooks salmon. Pat the fillet completely dry. "
                        "Look at that flake."),
        })
        plan = draft(alignment)

        line_two = [s for s in plan["segments"] if s["line_index"] == 2][0]
        self.assertEqual(line_two["take"], "B")
        self.assertIn("tightest", line_two["reason"])


class StatedReasons(unittest.TestCase):
    """assemble.py refuses a structural cut with no reason. These are derived."""

    def test_every_segment_carries_a_reason(self):
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. Pat the fillet completely dry. "
                        "Look at that flake."),
        })
        plan = draft(alignment)
        self.assertTrue(all(s["reason"] for s in plan["segments"]))

    def test_the_reason_names_what_it_beat(self):
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. Pat the fillet completely dry. "
                        "Look at that flake."),
            "B": spoken("Everyone cooks salmon wrong. Pat the fillet completely dry. "
                        "Look at that flake."),
        })
        plan = draft(alignment)
        self.assertIn("best of 2 takes", plan["segments"][0]["reason"])

    def test_a_single_take_says_so_rather_than_claiming_a_contest(self):
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. Pat the fillet completely dry. "
                        "Look at that flake."),
        })
        plan = draft(alignment)
        self.assertIn("only take", plan["segments"][0]["reason"])


class Fallbacks(unittest.TestCase):
    """The failure mode worth designing against, because it would be invisible."""

    def test_a_line_nobody_delivered_is_reported_not_guessed(self):
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. Look at that flake."),
        })
        plan = draft(alignment)

        self.assertEqual([row["index"] for row in plan["fallbacks"]], [2])
        self.assertNotIn(2, [s["line_index"] for s in plan["segments"]])

    def test_a_fallback_records_how_close_it_got(self):
        # So a person can see whether this was nearly right or nowhere near.
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. Look at that flake."),
        })
        plan = draft(alignment)
        self.assertIn("confidence", plan["fallbacks"][0])

    def test_footage_shot_against_the_wrong_script_produces_no_plan(self):
        # Not a cut with holes in it. The mechanical draft is the honest answer.
        alignment = align(SCRIPT, {
            "A": spoken("Today we are changing the oil in a lawnmower and it "
                        "takes about ten minutes start to finish"),
        })
        plan = draft(alignment)

        self.assertFalse(plan["usable"])
        self.assertEqual(plan["segments"], [])
        self.assertIn("refused", summarise(plan))

    def test_a_mostly_missing_script_is_refused_even_though_some_lines_matched(self):
        # One line out of three is 33%, below the floor: a third of a video is
        # not a draft.
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. and then something else entirely"),
        })
        plan = draft(alignment)

        self.assertLess(plan["coverage"], MIN_COVERAGE)
        self.assertFalse(plan["usable"])

    def test_the_summary_names_the_lines_that_fell_back(self):
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. Pat the fillet completely dry."),
        })
        plan = draft(alignment)
        self.assertIn("lines 3", summarise(plan))


class Beats(unittest.TestCase):
    def test_beats_come_from_the_scripts_own_headings(self):
        script = (
            "# Hook\nEveryone overcooks salmon.\n"
            "# Step 1 :: Pat it dry\nPat the fillet completely dry.\n"
            "# Payoff\nLook at that flake.\n"
        )
        alignment = align(script, {
            "A": spoken("Everyone overcooks salmon. Pat the fillet completely dry. "
                        "Look at that flake."),
        })
        plan = draft(alignment)
        self.assertEqual([s["beat"] for s in plan["segments"]],
                         ["hook", "step 1", "payoff"])

    def test_a_script_with_no_headings_still_produces_named_segments(self):
        # assemble.py wants a beat; "line" is honest where the script says
        # nothing, and an empty string would read as a missing field.
        alignment = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon. Pat the fillet completely dry. "
                        "Look at that flake."),
        })
        plan = draft(alignment)
        self.assertTrue(all(s["beat"] for s in plan["segments"]))


class Empty(unittest.TestCase):
    def test_no_takes_is_refused_rather_than_crashing(self):
        plan = draft(align(SCRIPT, {}))
        self.assertFalse(plan["usable"])
        self.assertEqual(plan["segments"], [])

    def test_an_empty_script_is_refused(self):
        plan = draft(align("", {"A": spoken("anything at all")}))
        self.assertFalse(plan["usable"])


if __name__ == "__main__":
    unittest.main()
