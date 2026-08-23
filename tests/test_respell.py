#!/usr/bin/env python3
"""Captions spelled the way the attached script spells them.

Run with:  python3 -m unittest discover -s tests

script_spelling.py has been in the tree, tested, and called from nowhere. The
wiring is this function, and the thing it has to get right is the clock: cues
are in cut time and alignment is in take time.

What is NOT tested here is the correction rule itself -- test_script_spelling.py
owns that, including the refusals that are the whole point of the module.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from assemble import respell_from_script  # noqa: E402


# Eight words with exactly one mangled clears align's confidence at 7/8 = 0.875.
# That matters: correct_cues holds a line to 0.85 before it will trust the
# script's spelling over what was heard -- "a line matched at 0.6 is the right
# span and the wrong authority". A five-word line with one mangled word scores
# 0.8 and is refused, correctly, which is what this fixture originally did.
SAID = ["pat", "the", "filet", "completely", "dry", "before", "you", "sear"]
SCRIPT = "pat the fillet completely dry before you sear"


def words_file(directory: Path, said=SAID, first_word_at=0.0) -> Path:
    """A take transcript, one word every second from `first_word_at`."""
    path = directory / "A.words.json"
    path.write_text(json.dumps({
        "version": 1,
        "words": [
            {"start": first_word_at + i, "end": first_word_at + i + 0.9, "word": word}
            for i, word in enumerate(said)
        ],
    }), encoding="utf-8")
    return path


def cue(text, start, end):
    return {
        "from": start,
        "to": end,
        "text": text,
        "words": [
            {"from": start, "to": end, "text": word} for word in text.split()
        ],
    }


class RespellFromScript(unittest.TestCase):
    def test_returns_cues_untouched_when_no_script_is_attached(self):
        # Most jobs. This must be a cheap no-op, not an alignment pass against
        # an empty string.
        cues = [cue("pat the filet completely dry", 0.0, 5.0)]
        out, changed = respell_from_script({"takes": {}}, [], cues)

        self.assertEqual(changed, 0)
        self.assertEqual(out[0]["text"], "pat the filet completely dry")

    def test_respells_a_word_the_script_spells_differently(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = words_file(Path(tmp))
            plan = {"script": SCRIPT, "takes": {"A": {"words": str(path)}}}
            segments = [{"take": "A", "start": 0.0, "end": 8.0,
                         "offset": 0.0, "padded_start": 0.0}]
            cues = [cue(" ".join(SAID), 0.0, 8.0)]

            out, changed = respell_from_script(plan, segments, cues)

        self.assertEqual(changed, 1)
        self.assertIn("fillet", out[0]["text"])

    def test_respells_against_a_cut_that_moved_the_words(self):
        # The regression this whole task exists for. The segment keeps 2.0-5.0
        # of the take and lands at 0.0 in the cut, so the cue is at 0.0-3.0
        # while the alignment row is still at 0.0-5.0 in take time. Without the
        # projection there is no overlap, and the correction silently does not
        # happen.
        # The take was recorded at 20s in; the cut puts it at 0. So the
        # alignment row sits at 20.0-27.9 in take time while the cue sits at
        # 0.0-7.9 in cut time, and the two do not overlap AT ALL. Without the
        # projection, correct_cues finds no context, changes nothing, and says
        # so by saying nothing.
        with tempfile.TemporaryDirectory() as tmp:
            path = words_file(Path(tmp), first_word_at=20.0)
            plan = {"script": SCRIPT, "takes": {"A": {"words": str(path)}}}
            segments = [{"take": "A", "start": 20.0, "end": 28.0,
                         "offset": 0.0, "padded_start": 20.0}]
            cues = [cue(" ".join(SAID), 0.0, 7.9)]

            out, changed = respell_from_script(plan, segments, cues)

        self.assertEqual(changed, 1)
        self.assertIn("fillet", out[0]["text"])

    def test_reports_zero_when_the_script_agrees_with_the_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            agreed = list(SAID)
            agreed[2] = "fillet"
            path = words_file(Path(tmp), said=agreed)
            plan = {"script": SCRIPT, "takes": {"A": {"words": str(path)}}}
            segments = [{"take": "A", "start": 0.0, "end": 8.0,
                         "offset": 0.0, "padded_start": 0.0}]
            cues = [cue(" ".join(agreed), 0.0, 8.0)]

            out, changed = respell_from_script(plan, segments, cues)

        self.assertEqual(changed, 0)
        self.assertIn("fillet", out[0]["text"])

    def test_survives_a_take_whose_words_file_is_missing(self):
        # build_captions already tolerates this and reports it as a skipped
        # take. Respelling must not be the thing that turns a missing words
        # file into a failed assembly.
        plan = {
            "script": "pat the fillet completely dry",
            "takes": {"A": {"words": "build/nope/A.words.json"}},
        }
        cues = [cue("pat the filet completely dry", 0.0, 5.0)]

        out, changed = respell_from_script(plan, cues=cues, resolved_segments=[])

        self.assertEqual(changed, 0)
        self.assertEqual(out[0]["text"], "pat the filet completely dry")

    def test_does_not_insert_a_script_word_that_was_never_said(self):
        # The safety property, asserted at this level too. test_script_spelling
        # owns the rule; this pins that wiring it up did not route around it.
        with tempfile.TemporaryDirectory() as tmp:
            # Only the first three words were said. The script has five more.
            path = words_file(Path(tmp), said=["pat", "the", "filet"])
            plan = {"script": SCRIPT, "takes": {"A": {"words": str(path)}}}
            segments = [{"take": "A", "start": 0.0, "end": 3.0,
                         "offset": 0.0, "padded_start": 0.0}]
            cues = [cue("pat the filet", 0.0, 3.0)]

            out, _ = respell_from_script(plan, segments, cues)

        self.assertNotIn("completely", out[0]["text"])
        self.assertNotIn("dry", out[0]["text"])


if __name__ == "__main__":
    unittest.main()
