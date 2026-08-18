#!/usr/bin/env python3
"""Reading a script's shot list into furniture and b-roll slots.

Run with:  python3 -m unittest discover -s tests

`shotlist.py` emits the timed skeleton; the roll and the on-screen description
are written by the model following yap-writer's SKILL.md. No schema pins those
key names, so this reader is tolerant by design and these tests are mostly
about what it refuses to invent.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from script_shots import (  # noqa: E402
    annotate,
    broll_slots,
    description_of,
    roll_of,
    step_labels,
)


def shot(index: int, **extra) -> dict:
    # The shape shotlist.py actually emits, plus whatever the caller adds.
    base = {"index": index, "line": f"line {index}", "words": 5,
            "start": 0.0, "end": 2.0, "seconds": 2.0}
    base.update(extra)
    return base


def segment(line_index: int | None, duration: float = 2.0, **extra) -> dict:
    base = {"take": "A", "start": 0.0, "end": duration, "duration": duration,
            "beat": "line", "kind": "structural", "line_index": line_index}
    base.update(extra)
    return base


class RollSpelling(unittest.TestCase):
    """Tolerant on the way in, because nothing pins these strings."""

    def test_the_spellings_a_writer_plausibly_produces_all_work(self):
        for value in ("B", "b-roll", "B-Roll", "broll", "b roll", "cutaway"):
            self.assertEqual(roll_of({"roll": value}), "b", value)
        for value in ("A", "a-roll", "talking head", "camera"):
            self.assertEqual(roll_of({"roll": value}), "a", value)

    def test_a_shot_with_no_roll_says_so_rather_than_defaulting(self):
        # "The writer did not decide" and "the writer chose A-roll" are
        # different facts. Inventing the second is how a cutaway appears over a
        # beat that should have stayed on someone's face.
        self.assertIsNone(roll_of(shot(1)))

    def test_an_unrecognised_roll_is_absent_not_an_error(self):
        self.assertIsNone(roll_of({"roll": "drone shot"}))
        self.assertIsNone(roll_of({"roll": 3}))

    def test_the_description_is_read_from_any_of_its_plausible_names(self):
        for key in ("onscreen", "on_screen", "description", "visual"):
            self.assertEqual(description_of(shot(1, **{key: "hands blotting"})),
                             "hands blotting")

    def test_no_description_is_an_empty_string(self):
        self.assertEqual(description_of(shot(1)), "")


class BrollSlots(unittest.TestCase):
    def test_a_b_roll_line_becomes_a_slot_on_the_reels_timeline(self):
        # The script's timecodes are what the writer EXPECTED the delivery to
        # take. The reel's are what it took. Slots are placed by line index.
        shots = [shot(1), shot(2, roll="b-roll", onscreen="paper towel blotting")]
        segments = [segment(1, duration=3.0), segment(2, duration=4.0)]

        slots = broll_slots(shots, segments)
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0]["from"], 3.0)
        self.assertEqual(slots[0]["to"], 7.0)
        self.assertEqual(slots[0]["onscreen"], "paper towel blotting")

    def test_an_a_roll_line_gets_no_slot(self):
        shots = [shot(1, roll="a-roll"), shot(2, roll="talking head")]
        self.assertEqual(broll_slots(shots, [segment(1), segment(2)]), [])

    def test_never_over_the_hook(self):
        # A reel that opens on a cutaway has thrown away the only moment
        # anyone decides whether to keep watching.
        shots = [shot(1, roll="b"), shot(2, roll="b")]
        slots = broll_slots(shots, [segment(1), segment(2)])
        self.assertEqual([s["line_index"] for s in slots], [2])

    def test_the_hook_guard_can_be_turned_off(self):
        shots = [shot(1, roll="b")]
        slots = broll_slots(shots, [segment(1)], never_over_hook=False)
        self.assertEqual(len(slots), 1)

    def test_a_cut_with_no_script_gets_no_slots(self):
        # Nothing here knows which line a mechanically-chosen segment
        # corresponds to, and guessing by position would put a cutaway over
        # whatever happened to be third.
        shots = [shot(1, roll="b"), shot(2, roll="b")]
        mechanical = [segment(None), segment(None), segment(None)]
        self.assertEqual(broll_slots(shots, mechanical), [])

    def test_a_script_whose_writer_assigned_no_rolls_gets_no_slots(self):
        # The common case: shotlist.py alone emits no roll at all.
        shots = [shot(1), shot(2), shot(3)]
        self.assertEqual(broll_slots(shots, [segment(1), segment(2), segment(3)]), [])

    def test_a_segment_whose_line_is_missing_from_the_shot_list_is_skipped(self):
        slots = broll_slots([shot(1, roll="b")], [segment(1), segment(99)])
        self.assertEqual([s["line_index"] for s in slots], [])

    def test_duration_is_derived_when_the_segment_only_carries_start_and_end(self):
        shots = [shot(1), shot(2, roll="b")]
        segments = [
            {"line_index": 1, "start": 4.0, "end": 7.0},
            {"line_index": 2, "start": 9.0, "end": 12.5},
        ]
        slots = broll_slots(shots, segments)
        self.assertEqual((slots[0]["from"], slots[0]["to"]), (3.0, 6.5))


class StepLabels(unittest.TestCase):
    def test_the_label_comes_from_the_headings_double_colon_half(self):
        segments = [segment(1, label="Pat it dry"), segment(2, label="High heat")]
        self.assertEqual(step_labels([], segments), {1: "Pat it dry", 2: "High heat"})

    def test_a_shots_description_is_not_used_as_a_label(self):
        # It says what the CAMERA is doing. Putting that in a step badge tells
        # the viewer something they can already see.
        shots = [shot(1, onscreen="hands blotting the fillet with a towel")]
        self.assertEqual(step_labels(shots, [segment(1)]), {})


class Annotate(unittest.TestCase):
    def test_editorial_fields_are_carried_onto_the_segment(self):
        shots = [shot(1, roll="b-roll", onscreen="paper towel blotting")]
        out = annotate([segment(1)], shots)
        self.assertEqual(out[0]["roll"], "b")
        self.assertEqual(out[0]["onscreen"], "paper towel blotting")

    def test_a_segment_keeps_everything_it_already_had(self):
        out = annotate([segment(1, reason="line 1: the only take that delivered it")],
                       [shot(1, roll="b")])
        self.assertEqual(out[0]["reason"], "line 1: the only take that delivered it")
        self.assertEqual(out[0]["kind"], "structural")

    def test_no_shots_returns_the_segments_unchanged(self):
        # What makes this safe to call unconditionally.
        segments = [segment(1), segment(2)]
        self.assertEqual(annotate(segments, []), segments)

    def test_it_does_not_mutate_what_it_was_given(self):
        segments = [segment(1)]
        annotate(segments, [shot(1, roll="b")])
        self.assertNotIn("roll", segments[0])


if __name__ == "__main__":
    unittest.main()
