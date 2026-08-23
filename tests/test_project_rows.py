#!/usr/bin/env python3
"""Aligned script lines, moved onto the assembled cut's timeline.

Run with:  python3 -m unittest discover -s tests

An alignment row is in TAKE time and a caption cue is in CUT time. Comparing
them directly is the failure this function exists to prevent, and it is a silent
one: script_spelling's overlap test simply finds no context, returns every cue
unchanged, and the respelling pass reports success having done nothing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from common import project_rows_to_timeline  # noqa: E402


def row(index=0, start=None, end=None, line="pat the fillet dry", confidence=0.9):
    return {
        "index": index,
        "line": line,
        "beat": "",
        "confidence": confidence,
        "from": start,
        "to": end,
        "words": line.split(),
    }


def segment(take="A", start=0.0, end=0.0, offset=0.0, padded_start=None):
    return {
        "take": take,
        "start": start,
        "end": end,
        "offset": offset,
        "padded_start": start if padded_start is None else padded_start,
    }


class ProjectRows(unittest.TestCase):
    def test_shifts_a_row_by_offset_minus_padded_start(self):
        # The segment keeps 11.12-11.88 of take A and lands at 0.0 in the cut,
        # with 0.07s of pad before it -- so a word moves by 0.0 - 11.05.
        rows = {"A": [row(start=11.20, end=11.60)]}
        out = project_rows_to_timeline(
            rows, [segment("A", 11.12, 11.88, offset=0.0, padded_start=11.05)]
        )

        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]["from"], 0.15, places=6)
        self.assertAlmostEqual(out[0]["to"], 0.55, places=6)

    def test_carries_every_other_key_through_untouched(self):
        # confidence especially: correct_cues filters on it at a 0.85 floor, so
        # a row that lost it would be silently dropped from the correction pass.
        rows = {"A": [row(index=3, line="sear it hard", confidence=0.93, start=1.0, end=2.0)]}
        out = project_rows_to_timeline(rows, [segment("A", 0.0, 5.0, offset=0.0)])

        self.assertEqual(out[0]["index"], 3)
        self.assertEqual(out[0]["line"], "sear it hard")
        self.assertEqual(out[0]["confidence"], 0.93)
        self.assertEqual(out[0]["words"], ["sear", "it", "hard"])

    def test_clips_a_row_to_the_kept_range(self):
        # The row runs 1.0-9.0 but the cut keeps only 2.0-4.0. What is on screen
        # is the overlap, and the projected row has to say so or the correction
        # pass will look for script words against a cue that does not exist.
        rows = {"A": [row(start=1.0, end=9.0)]}
        out = project_rows_to_timeline(rows, [segment("A", 2.0, 4.0, offset=0.0)])

        self.assertAlmostEqual(out[0]["from"], 0.0, places=6)
        self.assertAlmostEqual(out[0]["to"], 2.0, places=6)

    def test_a_row_spanning_two_segments_is_projected_into_both(self):
        # Cutting mid-sentence is ordinary -- a filler in the middle of a line
        # splits it. Both halves are on screen, so both need their spelling.
        rows = {"A": [row(start=1.0, end=9.0)]}
        out = project_rows_to_timeline(rows, [
            segment("A", 1.0, 3.0, offset=0.0),
            segment("A", 7.0, 9.0, offset=2.0),
        ])

        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[0]["from"], 0.0, places=6)
        self.assertAlmostEqual(out[0]["to"], 2.0, places=6)
        self.assertAlmostEqual(out[1]["from"], 2.0, places=6)
        self.assertAlmostEqual(out[1]["to"], 4.0, places=6)

    def test_drops_a_row_that_was_cut_out_entirely(self):
        # Not an error. The line was not delivered on screen, so there is
        # nothing to respell, and a row projected anyway would offer script
        # words as context for a cue built from different audio.
        rows = {"A": [row(start=20.0, end=21.0)]}
        out = project_rows_to_timeline(rows, [segment("A", 0.0, 5.0, offset=0.0)])

        self.assertEqual(out, [])

    def test_drops_a_line_the_take_never_delivered(self):
        # align_take records these with from/to of None rather than omitting
        # them, because "not delivered in this take" is a fact the cut planner
        # needs. It is not a row that can be projected.
        rows = {"A": [row(start=None, end=None, confidence=0.2)]}
        out = project_rows_to_timeline(rows, [segment("A", 0.0, 5.0, offset=0.0)])

        self.assertEqual(out, [])

    def test_only_projects_rows_belonging_to_the_segment_s_take(self):
        # A cut mixes takes. Take B's alignment against take A's segment would
        # place script words at times nobody said them.
        rows = {"A": [row(start=1.0, end=2.0)], "B": [row(start=1.0, end=2.0)]}
        out = project_rows_to_timeline(rows, [segment("B", 0.0, 5.0, offset=0.0)])

        self.assertEqual(len(out), 1)

    def test_survives_a_segment_with_no_usable_bounds(self):
        # map_words_to_timeline skips these rather than raising, and this
        # function is called from the same place with the same data.
        rows = {"A": [row(start=1.0, end=2.0)]}
        out = project_rows_to_timeline(rows, [{"take": "A", "start": "nope"}])

        self.assertEqual(out, [])

    def test_defaults_padded_start_to_start_when_absent(self):
        # verify.py tolerates a segment without offset/padded_start and
        # assemble.py does not; map_words_to_timeline took the permissive
        # reading, and a second projection with a stricter one would crash on
        # data the first one accepts.
        rows = {"A": [row(start=3.0, end=4.0)]}
        out = project_rows_to_timeline(rows, [{"take": "A", "start": 3.0, "end": 5.0}])

        self.assertAlmostEqual(out[0]["from"], 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
