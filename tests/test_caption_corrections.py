#!/usr/bin/env python3
"""A word respelled by a person, honoured at render time.

Run with:  python3 -m unittest discover -s tests

The correction is pinned to (take, word_index) and carries the original text.
That `from` is the whole safety mechanism: re-transcribing a take shifts every
index after an inserted word, and a correction applied blindly would respell
whatever moved into that slot -- silently, on screen, in someone's voice.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import json  # noqa: E402
import tempfile  # noqa: E402

from assemble import apply_corrections, build_captions  # noqa: E402


def words(*texts):
    return [
        {"start": float(i), "end": float(i) + 0.9, "word": text}
        for i, text in enumerate(texts)
    ]


def correction(index=0, take="A", was="quackwackwack", now="kwakwakwak",
               override=False):
    return {"take": take, "word_index": index, "from": was, "to": now,
            "override": override}


class ApplyCorrections(unittest.TestCase):
    def test_respells_the_word_at_that_index(self):
        out, refused = apply_corrections(
            words("welcome", "to", "quackwackwack"), [correction(index=2)], "A")

        self.assertEqual(out[2]["word"], "kwakwakwak")
        self.assertEqual(refused, [])

    def test_marks_the_corrected_word_so_the_script_pass_leaves_it_alone(self):
        out, _ = apply_corrections(
            words("welcome", "to", "quackwackwack"), [correction(index=2)], "A")

        self.assertTrue(out[2].get("manual"))
        self.assertFalse(out[0].get("manual"))

    def test_ignores_a_correction_for_a_different_take(self):
        out, refused = apply_corrections(
            words("quackwackwack"), [correction(index=0, take="B")], "A")

        self.assertEqual(out[0]["word"], "quackwackwack")
        self.assertEqual(refused, [])

    def test_refuses_when_the_word_at_that_index_changed(self):
        # The transcript was regenerated and everything shifted. Applying this
        # would respell an unrelated word, and nothing downstream could tell.
        out, refused = apply_corrections(
            words("welcome", "to", "something-else"), [correction(index=2)], "A")

        self.assertEqual(out[2]["word"], "something-else")
        self.assertEqual(len(refused), 1)
        self.assertIn("quackwackwack", refused[0])
        self.assertIn("something-else", refused[0])

    def test_refuses_an_index_past_the_end_of_the_transcript(self):
        out, refused = apply_corrections(words("hello"), [correction(index=9)], "A")

        self.assertEqual(out[0]["word"], "hello")
        self.assertEqual(len(refused), 1)

    def test_matches_ignoring_case_and_surrounding_punctuation(self):
        # whisper writes "Quackwackwack," with a capital and a comma. A person
        # correcting it types the word, not the punctuation, and a correction
        # that only matched an exact string would be refused for something that
        # is not a difference.
        out, refused = apply_corrections(
            words("Quackwackwack,"), [correction(index=0)], "A")

        self.assertEqual(refused, [])
        self.assertEqual(out[0]["word"], "kwakwakwak,")

    def test_refuses_a_rewrite_that_is_not_a_respelling(self):
        # The rule the pipeline already enforces on the script pass, applied to
        # a person too: "chicken" to "salmon" is 0.154, and typing it into a
        # caption box puts a word on screen that nobody said.
        out, refused = apply_corrections(
            words("chicken"), [correction(index=0, was="chicken", now="salmon")], "A")

        self.assertEqual(out[0]["word"], "chicken")
        self.assertEqual(len(refused), 1)
        self.assertIn("override", refused[0])

    def test_applies_a_rewrite_when_the_person_overrode_it(self):
        # "I did say this." The one path that can put a word on screen whisper
        # never heard, which is exactly why it is explicit rather than implied.
        out, refused = apply_corrections(
            words("chicken"),
            [correction(index=0, was="chicken", now="salmon", override=True)], "A")

        self.assertEqual(out[0]["word"], "salmon")
        self.assertEqual(refused, [])

    def test_a_short_phonetic_mishearing_needs_the_override(self):
        # "kwak" for "quack" is 0.222 -- below pairs that MUST be refused, which
        # is why script_spelling leaves them undone. A person can still fix
        # them; they just have to say so.
        _, refused = apply_corrections(
            words("quack"), [correction(index=0, was="quack", now="kwak")], "A")

        self.assertEqual(len(refused), 1)

    def test_leaves_every_other_word_untouched(self):
        out, _ = apply_corrections(
            words("welcome", "to", "quackwackwack"), [correction(index=2)], "A")

        self.assertEqual([w["word"] for w in out[:2]], ["welcome", "to"])

    def test_does_not_mutate_the_words_it_was_given(self):
        original = words("quackwackwack")
        apply_corrections(original, [correction(index=0)], "A")

        self.assertEqual(original[0]["word"], "quackwackwack")


if __name__ == "__main__":
    unittest.main()


class ThroughBuildCaptions(unittest.TestCase):
    """The whole chain: a correction on the plan reaching a cue on screen.

    Worth testing end to end rather than only at apply_corrections, because
    three things sit between them and each drops unknown keys by default --
    the load, map_words_to_timeline's projection, and the grouping.
    """

    def _build(self, said, corrections):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "A.words.json"
            path.write_text(json.dumps({"words": [
                {"start": float(i), "end": float(i) + 0.5, "word": word}
                for i, word in enumerate(said)
            ]}), encoding="utf-8")
            plan = {
                "takes": {"A": {"words": str(path)}},
                "caption_corrections": corrections,
            }
            segments = [{"take": "A", "start": 0.0, "end": 100.0,
                         "offset": 0.0, "padded_start": 0.0}]
            return build_captions(plan, segments, 5, 2.4)

    def test_a_correction_reaches_the_cue_text(self):
        cues, _, refusals = self._build(
            ["welcome", "to", "quackwackwack"], [correction(index=2)])

        # Across the cues, not cues[0]: the grouping decides which cue a word
        # lands in (2.4s and five words by default), and that is the style's
        # business rather than this test's.
        self.assertEqual(refusals, [])
        self.assertIn("kwakwakwak", " ".join(c["text"] for c in cues))

    def test_the_cue_holding_it_is_flagged_for_the_script_pass(self):
        # map_words_to_timeline returns {from, to, text} and drops the rest, so
        # this only passes because the flag is carried through deliberately.
        cues, _, _ = self._build(
            ["welcome", "to", "quackwackwack"], [correction(index=2)])

        flagged = [c for c in cues if c.get("manual")]
        self.assertEqual(len(flagged), 1)
        self.assertIn("kwakwakwak", flagged[0]["text"])

    def test_a_cue_with_no_correction_in_it_is_not_flagged(self):
        cues, _, _ = self._build(["welcome", "to", "there."], [])

        self.assertEqual([c for c in cues if c.get("manual")], [])

    def test_a_refused_correction_is_reported_and_changes_nothing(self):
        cues, _, refusals = self._build(
            ["welcome", "to", "something-else"], [correction(index=2)])

        text = " ".join(c["text"] for c in cues)
        self.assertEqual(len(refusals), 1)
        self.assertIn("something-else", text)
        self.assertNotIn("kwakwakwak", text)
