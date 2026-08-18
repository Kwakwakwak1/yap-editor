#!/usr/bin/env python3
"""Spelling captions from the script, without putting unsaid words on screen.

Run with:  python3 -m unittest discover -s tests

The tests that matter here are the refusals. A caption containing a word nobody
said is a lie the viewer has no way to detect, so the rule is mechanical: a
correction must replace a word that is already there, one for one, at a
position alignment matched.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from script_spelling import (  # noqa: E402
    correct_cue,
    correct_cues,
    corrections_for,
)


def cue(text: str, start: float = 0.0, step: float = 0.4) -> dict:
    words, at = [], start
    for word in text.split():
        words.append({"from": round(at, 3), "to": round(at + 0.3, 3), "text": word})
        at += step
    return {"from": words[0]["from"], "to": words[-1]["to"], "text": text, "words": words}


def line(text: str, start: float, end: float, confidence: float = 1.0) -> dict:
    return {"index": 1, "line": text, "from": start, "to": end, "confidence": confidence}


class WhatItFixes(unittest.TestCase):
    def test_a_mangled_brand_name_takes_the_scripts_spelling(self):
        fixed = correct_cue(cue("follow quackwackwack for more"),
                            "follow kwakwakwak for more".split())
        self.assertEqual(fixed["text"], "follow kwakwakwak for more")

    def test_the_correction_does_not_move_the_word(self):
        # A correction changes how a word is written, never when it is said.
        original = cue("follow quackwackwack for more")
        fixed = correct_cue(original, "follow kwakwakwak for more".split())
        self.assertEqual(
            [w["from"] for w in fixed["words"]],
            [w["from"] for w in original["words"]],
        )

    def test_punctuation_from_the_transcript_survives(self):
        # Dropping the comma would change the caption's grouping, which is a
        # separate decision the style already owns.
        fixed = correct_cue(cue("quackwackwack, obviously"),
                            "kwakwakwak, obviously".split())
        self.assertEqual(fixed["words"][0]["text"], "kwakwakwak,")


class WhatItRefuses(unittest.TestCase):
    """The whole risk of the feature lives here."""

    def test_it_never_inserts_a_word_that_was_not_said(self):
        # The script says more than the speaker did. Taking the extra word
        # would put it on screen having never been spoken.
        fixed = correct_cue(cue("pat it dry"), "pat it completely dry".split())
        self.assertEqual(fixed["text"], "pat it dry")

    def test_it_never_deletes_a_word_that_was_said(self):
        fixed = correct_cue(cue("pat it completely dry"), "pat it dry".split())
        self.assertEqual(fixed["text"], "pat it completely dry")

    def test_a_different_word_is_not_a_spelling_correction(self):
        # "salmon" heard as "chicken" is a mishearing of a different kind:
        # correcting it would misquote the speaker.
        fixed = correct_cue(cue("cook the chicken"), "cook the salmon".split())
        self.assertEqual(fixed["text"], "cook the chicken")

    def test_an_uneven_rewrite_is_refused(self):
        # Two said words becoming three written ones is a rewrite, not a
        # spelling fix, and there is no one-to-one mapping to apply.
        self.assertEqual(corrections_for(["kitchen", "pow"],
                                         ["Kitchen", "Pal", "app"]), {})

    def test_an_ad_lib_is_left_exactly_as_spoken(self):
        fixed = correct_cue(cue("honestly this bit is off script entirely"),
                            "pat the fillet completely dry".split())
        self.assertEqual(fixed["text"], "honestly this bit is off script entirely")


class WhatItCannotDo(unittest.TestCase):
    """Stated, so nobody discovers it in a published reel.

    Short phonetic mishearings are not corrected. They are not similar as
    strings -- "pow"/"pal" scores 0.333, below "twelve"/"twenty" at 0.500 --
    so no character-similarity threshold catches them without also rewriting
    "cook" to "bake". That needs a phonetic comparison, and approximating it
    would be worse than leaving it.
    """

    def test_a_short_phonetic_mishearing_is_left_alone(self):
        fixed = correct_cue(cue("open kitchen pow"), "open Kitchen Pal".split())
        self.assertEqual(fixed["text"], "open kitchen pow")

    def test_but_a_long_one_is_caught(self):
        # The common case: a proper noun whose spelling whisper mangles while
        # keeping most of its letters.
        fixed = correct_cue(cue("follow quackwackwack today"),
                            "follow kwakwakwak today".split())
        self.assertEqual(fixed["text"], "follow kwakwakwak today")

    def test_a_number_is_never_rewritten_as_another_number(self):
        # "twelve"/"twenty" is 0.500 and correcting it would change a recipe.
        fixed = correct_cue(cue("bake it twelve minutes"),
                            "bake it twenty minutes".split())
        self.assertEqual(fixed["text"], "bake it twelve minutes")


class Confidence(unittest.TestCase):
    def test_a_weakly_aligned_line_does_not_get_to_respell_anything(self):
        # Locating a line well enough to cut from it is a lower bar than
        # trusting its spelling over what was actually heard.
        cues = [cue("follow quackwackwack for more")]
        weak = [line("follow kwakwakwak for more", 0.0, 1.2, confidence=0.6)]
        self.assertEqual(correct_cues(cues, weak)[0]["text"],
                         "follow quackwackwack for more")

    def test_a_confidently_aligned_line_does(self):
        cues = [cue("follow quackwackwack for more")]
        strong = [line("follow kwakwakwak for more", 0.0, 1.2, confidence=1.0)]
        self.assertEqual(correct_cues(cues, strong)[0]["text"],
                         "follow kwakwakwak for more")

    def test_an_unaligned_line_is_ignored_entirely(self):
        cues = [cue("follow quackwackwack for more")]
        missing = [dict(line("follow kwakwakwak for more", 0.0, 1.2), **{"from": None})]
        self.assertEqual(correct_cues(cues, missing)[0]["text"],
                         "follow quackwackwack for more")


class Overlap(unittest.TestCase):
    def test_a_cue_inside_one_line_is_corrected(self):
        # The common case, and the one the feature exists for.
        cues = [cue("follow quackwackwack for more", start=0.2)]
        lines = [line("Follow kwakwakwak for more.", 0.0, 2.0)]
        self.assertIn("kwakwakwak", correct_cues(cues, lines)[0]["text"])

    def test_a_cue_straddling_two_lines_declines_rather_than_half_correcting(self):
        # A cue is a few words and routinely crosses a line boundary. The
        # context either side is sliced to the overlap, but the comparison
        # still comes out uneven often enough that the block rule refuses --
        # and refusing is the right outcome. This is a MISS, not a wrong
        # correction: the caption keeps whisper's spelling, which is where we
        # started, rather than gaining a word nobody said.
        cues = [cue("dry. follow quackwackwack", start=1.0)]
        lines = [
            line("Pat the fillet completely dry.", 0.0, 1.4),
            dict(line("Follow kwakwakwak for more.", 1.2, 3.0), index=2),
        ]
        corrected = correct_cues(cues, lines)[0]["text"]
        self.assertEqual(corrected, "dry. follow quackwackwack")

    def test_cues_with_no_words_are_passed_through(self):
        # Props staged before per-word timings existed carry only `text`.
        bare = {"from": 0.0, "to": 1.0, "text": "no per-word timings here"}
        self.assertEqual(correct_cues([bare], [line("anything", 0.0, 1.0)])[0], bare)

    def test_no_confident_lines_returns_the_cues_untouched(self):
        cues = [cue("follow quackwackwack for more")]
        self.assertEqual(correct_cues(cues, [])[0]["text"],
                         "follow quackwackwack for more")


if __name__ == "__main__":
    unittest.main()
