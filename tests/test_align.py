#!/usr/bin/env python3
"""Matching a transcript to the script it was read from.

Run with:  python3 -m unittest discover -s tests

The fixtures are the honest part. A script aligner that is only ever tested
against footage that follows the script exactly will look excellent and then
make the cut WORSE than the mechanical draft the first time somebody ad-libs --
which is what talking-to-camera footage does constantly. So the three cases
here are: followed closely, ad-libbed heavily, and shot against the wrong
script entirely.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from align import (  # noqa: E402
    FLOOR,
    align,
    align_take,
    best_span,
    coverage,
    script_lines,
)

SCRIPT = """\
Everyone overcooks salmon.
Pat the fillet completely dry.
Four twenty five for twelve minutes.
Look at that flake.
"""


def spoken(text: str, start: float = 0.0, step: float = 0.4) -> list[dict]:
    """A transcript, one word every `step` seconds."""
    words = []
    at = start
    for word in text.split():
        words.append({"word": word, "start": round(at, 3), "end": round(at + 0.3, 3)})
        at += step
    return words


class ScriptLines(unittest.TestCase):
    def test_one_spoken_line_per_line(self):
        lines = script_lines(SCRIPT)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0]["line"], "Everyone overcooks salmon.")
        self.assertEqual(lines[0]["tokens"], ["everyone", "overcooks", "salmon"])

    def test_headings_are_structure_not_speech(self):
        # Aligning "# Hook" would go looking for someone saying the word "hook".
        lines = script_lines("# Hook\nEveryone overcooks salmon.\n")
        self.assertEqual([line["line"] for line in lines], ["Everyone overcooks salmon."])

    def test_a_line_carries_the_heading_it_sits_under(self):
        # This is where a script-driven cut gets its beat names, instead of
        # inventing them.
        lines = script_lines(
            "# Hook\nEveryone overcooks salmon.\n"
            "# Step 1 :: Pat it dry\nPat the fillet completely dry.\n"
        )
        self.assertEqual([line["beat"] for line in lines], ["hook", "step 1"])

    def test_a_script_with_no_headings_gives_every_line_an_empty_beat(self):
        # A fact, not a failure: yap-writer's drafts are one spoken line per
        # line with no headings at all.
        self.assertEqual({line["beat"] for line in script_lines(SCRIPT)}, {""})

    def test_blank_lines_do_not_take_an_index(self):
        lines = script_lines("First line.\n\n\nSecond line.\n")
        self.assertEqual([line["index"] for line in lines], [1, 2])


class BestSpan(unittest.TestCase):
    def test_a_verbatim_line_scores_one(self):
        tokens = ["everyone", "overcooks", "salmon"]
        start, end, confidence = best_span(tokens, tokens)
        self.assertEqual((start, end), (0, 3))
        self.assertEqual(confidence, 1.0)

    def test_saying_more_than_the_line_is_not_penalised(self):
        # A take that delivers the line plus an ad-lib still delivered the
        # line. A symmetric score would mark every honest take as a bad match.
        _, _, confidence = best_span(
            ["pat", "it", "dry"],
            ["so", "basically", "pat", "it", "dry", "you", "know"],
        )
        self.assertEqual(confidence, 1.0)

    def test_a_stumble_inside_the_line_stays_one_span(self):
        # Cutting only the matching parts would splice the stumble out
        # mid-word; the span covers the whole delivery.
        start, end, _ = best_span(
            ["pat", "it", "dry"],
            ["pat", "it", "uh", "sorry", "it", "dry"],
        )
        self.assertEqual((start, end), (0, 6))

    def test_a_line_never_said_scores_zero(self):
        _, _, confidence = best_span(["pat", "it", "dry"], ["completely", "different"])
        self.assertEqual(confidence, 0.0)

    def test_punctuation_only_lines_do_not_divide_by_zero(self):
        self.assertEqual(best_span([], ["anything"]), (0, 0, 0.0))


class FollowedClosely(unittest.TestCase):
    """The easy case, and the one that must stay exact."""

    def test_every_line_is_found_with_its_timecodes(self):
        words = spoken(
            "Everyone overcooks salmon. Pat the fillet completely dry. "
            "Four twenty five for twelve minutes. Look at that flake."
        )
        rows = align_take(script_lines(SCRIPT), words)

        self.assertEqual([row["confidence"] for row in rows], [1.0, 1.0, 1.0, 1.0])
        self.assertTrue(all(row["from"] is not None for row in rows))
        # In order, and non-overlapping: a take is a performance top to bottom.
        starts = [row["from"] for row in rows]
        self.assertEqual(starts, sorted(starts))
        for previous, following in zip(rows, rows[1:]):
            self.assertLessEqual(previous["to"], following["from"])

    def test_coverage_is_total(self):
        words = spoken(
            "Everyone overcooks salmon. Pat the fillet completely dry. "
            "Four twenty five for twelve minutes. Look at that flake."
        )
        self.assertEqual(coverage(align_take(script_lines(SCRIPT), words)), 1.0)


class AdLibbedHeavily(unittest.TestCase):
    """The normal case for talking-to-camera footage."""

    WORDS = spoken(
        "Okay so um hey everyone I wanted to talk about salmon today because "
        "everyone overcooks salmon right so the first thing you do is pat the "
        "fillet completely dry with a towel and then it is four twenty five "
        "for twelve minutes that is it and honestly look at that flake"
    )

    def test_the_lines_are_still_found_under_the_padding(self):
        rows = align_take(script_lines(SCRIPT), self.WORDS)
        self.assertTrue(
            all(row["from"] is not None for row in rows),
            [(row["index"], row["confidence"]) for row in rows],
        )

    def test_the_spans_do_not_run_backwards(self):
        # "salmon" appears twice here. Searching the whole transcript per line
        # independently would let a later line match an earlier occurrence and
        # produce a cut that jumps backwards.
        rows = align_take(script_lines(SCRIPT), self.WORDS)
        starts = [row["from"] for row in rows]
        self.assertEqual(starts, sorted(starts))


class WrongScriptEntirely(unittest.TestCase):
    """The case that has to fail cleanly rather than confidently."""

    def test_nothing_aligns_and_it_says_so(self):
        words = spoken(
            "Today we are going to talk about changing the oil in a lawnmower "
            "which is easier than most people think and takes about ten minutes"
        )
        rows = align_take(script_lines(SCRIPT), words)

        self.assertEqual([row["from"] for row in rows], [None, None, None, None])
        self.assertEqual(coverage(rows), 0.0)

    def test_a_coincidental_word_overlap_does_not_pass_the_floor(self):
        # Two unrelated English sentences share "the", "a", "to" routinely --
        # enough to score on a short line if there were no floor at all.
        words = spoken("the the the a a to to and and")
        rows = align_take(script_lines(SCRIPT), words)
        self.assertTrue(all(row["confidence"] < FLOOR for row in rows))


class Paraphrased(unittest.TestCase):
    """Where this stops working, stated rather than discovered.

    Alignment locates the script's WORDS. It has no idea what they mean, so a
    line delivered as the same idea in different words does not align, and no
    threshold makes it align without also matching unrelated sentences.

    That is a real limitation and it is why #89 needs a confidence floor per
    line below which it falls back to the mechanical draft, and why the review
    UI has to show which lines fell back. A cut planner that treated a
    paraphrase as a miss and silently dropped the line would be worse than one
    that never read the script.
    """

    def test_the_same_idea_in_different_words_does_not_align(self):
        words = spoken(
            "most people cook this fish for far too long "
            "get all the moisture off the surface first"
        )
        rows = align_take(script_lines(SCRIPT), words)
        self.assertTrue(all(row["from"] is None for row in rows[:2]))

    def test_a_half_remembered_line_still_aligns(self):
        # The useful middle: most words present, delivery imperfect. This is
        # what the floor is set for.
        words = spoken("pat the fillet dry")
        rows = align_take(script_lines(SCRIPT), words)
        self.assertGreaterEqual(rows[1]["confidence"], FLOOR)
        self.assertIsNotNone(rows[1]["from"])


class MissingOneLine(unittest.TestCase):
    def test_a_skipped_line_does_not_drag_the_rest_out_of_position(self):
        # The second line is never said. Every later line must still be found.
        words = spoken(
            "Everyone overcooks salmon. "
            "Four twenty five for twelve minutes. Look at that flake."
        )
        rows = align_take(script_lines(SCRIPT), words)

        self.assertIsNone(rows[1]["from"])
        self.assertIsNotNone(rows[2]["from"])
        self.assertIsNotNone(rows[3]["from"])
        self.assertEqual(coverage(rows), 0.75)


class Alignment(unittest.TestCase):
    def test_the_document_reports_every_take(self):
        result = align(SCRIPT, {
            "A": spoken("Everyone overcooks salmon."),
            "B": spoken(
                "Everyone overcooks salmon. Pat the fillet completely dry. "
                "Four twenty five for twelve minutes. Look at that flake."
            ),
        })
        self.assertEqual(result["lines"], 4)
        self.assertEqual(result["takes"]["A"]["coverage"], 0.25)
        self.assertEqual(result["takes"]["B"]["coverage"], 1.0)

    def test_no_takes_is_an_empty_document_not_a_crash(self):
        result = align(SCRIPT, {})
        self.assertEqual(result["takes"], {})


if __name__ == "__main__":
    unittest.main()
