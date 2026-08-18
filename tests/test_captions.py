#!/usr/bin/env python3
"""Word-timing projection and caption cue building.

Run with:  python3 -m unittest discover -s tests

Stdlib unittest on purpose. The pipeline scripts are stdlib + ffmpeg only so they
run on a bare machine (minik's non-interactive environment has no pip packages on
PATH), and the tests should not be the thing that breaks that property.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from assemble import build_captions, caption_cue, render_segments  # noqa: E402
from common import map_words_to_timeline  # noqa: E402


def word(text: str, start: float, end: float) -> dict:
    return {"word": text, "start": start, "end": end}


def segment(take: str, start: float, end: float, offset: float, padded_start: float) -> dict:
    return {
        "take": take,
        "start": start,
        "end": end,
        "offset": offset,
        "padded_start": padded_start,
    }


class MapWordsToTimeline(unittest.TestCase):
    def test_shifts_by_offset_minus_padded_start(self):
        # The take says 10.0s; the segment starts at 9.9 (pad) and lands at 3.0
        # in the cut, so the word belongs at 3.0 + (10.0 - 9.9) = 3.1.
        words = {"A": [word("hello", 10.0, 10.5)]}
        result = map_words_to_timeline(words, [segment("A", 10.0, 11.0, 3.0, 9.9)])
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["from"], 3.1)
        self.assertAlmostEqual(result[0]["to"], 3.6)
        self.assertEqual(result[0]["text"], "hello")

    def test_excludes_words_outside_the_kept_range(self):
        words = {
            "A": [
                word("before", 1.0, 1.4),
                word("inside", 5.2, 5.6),
                word("after", 9.0, 9.4),
            ]
        }
        result = map_words_to_timeline(words, [segment("A", 5.0, 6.0, 0.0, 5.0)])
        self.assertEqual([item["text"] for item in result], ["inside"])

    def test_boundary_words_are_half_open(self):
        # A word ending exactly at `start` is out; one starting exactly at `end`
        # is out. Anything overlapping the range is in.
        words = {
            "A": [
                word("touching-start", 4.0, 5.0),
                word("touching-end", 6.0, 7.0),
                word("straddling", 5.9, 6.4),
            ]
        }
        result = map_words_to_timeline(words, [segment("A", 5.0, 6.0, 0.0, 5.0)])
        self.assertEqual([item["text"] for item in result], ["straddling"])

    def test_clamps_negative_timestamps_to_zero(self):
        # Pad can start the extract after the word begins, which would otherwise
        # place it before the start of the cut.
        words = {"A": [word("early", 4.8, 5.2)]}
        result = map_words_to_timeline(words, [segment("A", 4.5, 6.0, 0.0, 5.0)])
        self.assertEqual(result[0]["from"], 0.0)

    def test_strips_surrounding_whitespace(self):
        words = {"A": [word("  spaced  ", 1.0, 1.5)]}
        result = map_words_to_timeline(words, [segment("A", 0.0, 2.0, 0.0, 0.0)])
        self.assertEqual(result[0]["text"], "spaced")

    def test_concatenates_segments_in_order(self):
        words = {
            "A": [word("first", 1.0, 1.4)],
            "B": [word("second", 8.0, 8.4)],
        }
        segments = [
            segment("A", 1.0, 2.0, 0.0, 1.0),
            segment("B", 8.0, 9.0, 1.0, 8.0),
        ]
        result = map_words_to_timeline(words, segments)
        self.assertEqual([item["text"] for item in result], ["first", "second"])
        self.assertAlmostEqual(result[1]["from"], 1.0)

    def test_unknown_take_yields_nothing_rather_than_raising(self):
        result = map_words_to_timeline({"A": [word("x", 1.0, 2.0)]}, [segment("Z", 1.0, 2.0, 0.0, 1.0)])
        self.assertEqual(result, [])

    def test_malformed_word_is_skipped_not_fatal(self):
        words = {"A": [{"word": "broken"}, word("good", 1.0, 1.4)]}
        result = map_words_to_timeline(words, [segment("A", 0.0, 2.0, 0.0, 0.0)])
        self.assertEqual([item["text"] for item in result], ["good"])

    def test_offset_and_padded_start_default_when_absent(self):
        # verify.py tolerated segments without these keys; the shared helper must
        # keep doing so or the join check regresses on older resolved plans.
        words = {"A": [word("bare", 2.0, 2.5)]}
        result = map_words_to_timeline(words, [{"take": "A", "start": 2.0, "end": 3.0}])
        self.assertAlmostEqual(result[0]["from"], 0.0)
        self.assertAlmostEqual(result[0]["to"], 0.5)


class CaptionCue(unittest.TestCase):
    def test_carries_per_word_timings(self):
        cue = caption_cue([
            {"from": 1.0, "to": 1.4, "text": "real"},
            {"from": 1.4, "to": 1.9, "text": "timings"},
        ])
        self.assertEqual(cue["text"], "real timings")
        self.assertEqual(cue["from"], 1.0)
        self.assertEqual(cue["to"], 1.9)
        self.assertEqual(
            cue["words"],
            [
                {"from": 1.0, "to": 1.4, "text": "real"},
                {"from": 1.4, "to": 1.9, "text": "timings"},
            ],
        )

    def test_rounds_to_milliseconds(self):
        cue = caption_cue([{"from": 1.00049, "to": 1.99951, "text": "x"}])
        self.assertEqual(cue["from"], 1.0)
        self.assertEqual(cue["to"], 2.0)
        self.assertEqual(cue["words"][0]["from"], 1.0)


class BuildCaptions(unittest.TestCase):
    """The grouping rules, exercised through the real entry point."""

    def build(self, words, max_words=5, max_seconds=2.4):
        with tempfile.TemporaryDirectory() as tmp:
            words_file = Path(tmp) / "A.words.json"
            words_file.write_text(json.dumps({"words": words}), encoding="utf-8")
            plan = {"takes": {"A": {"words": str(words_file)}}}
            segments = [segment("A", 0.0, 100.0, 0.0, 0.0)]
            return build_captions(plan, segments, max_words, max_seconds)

    def test_splits_on_max_words(self):
        cues, skipped = self.build(
            [word(f"w{i}", i * 0.2, i * 0.2 + 0.15) for i in range(7)],
            max_words=3,
        )
        self.assertEqual(skipped, [])
        self.assertEqual([len(cue["words"]) for cue in cues], [3, 3, 1])

    def test_splits_on_sentence_end(self):
        cues, _ = self.build([
            word("done.", 0.0, 0.3),
            word("next", 0.4, 0.7),
        ])
        self.assertEqual([cue["text"] for cue in cues], ["done.", "next"])

    def test_splits_on_max_seconds(self):
        cues, _ = self.build(
            [word("a", 0.0, 0.2), word("b", 0.3, 0.5), word("c", 3.0, 3.2)],
            max_seconds=1.0,
        )
        self.assertEqual([cue["text"] for cue in cues], ["a b", "c"])

    def test_every_cue_carries_words_covering_its_text(self):
        cues, _ = self.build([word(f"w{i}", i * 0.3, i * 0.3 + 0.2) for i in range(6)])
        for cue in cues:
            self.assertEqual(
                cue["text"],
                " ".join(item["text"] for item in cue["words"]),
                "cue text and its word list must not disagree",
            )
            self.assertEqual(cue["from"], cue["words"][0]["from"])
            self.assertEqual(cue["to"], cue["words"][-1]["to"])

    def test_reports_takes_with_no_words_file(self):
        plan = {"takes": {"A": {"words": "/nonexistent/A.words.json"}, "B": {}}}
        cues, skipped = build_captions(plan, [segment("A", 0.0, 1.0, 0.0, 0.0)], 5, 2.4)
        self.assertEqual(cues, [])
        self.assertEqual(sorted(skipped), ["A", "B"])

    def test_empty_words_do_not_create_empty_cues(self):
        cues, _ = self.build([word("   ", 0.0, 0.2), word("real", 0.3, 0.6)])
        self.assertEqual([cue["text"] for cue in cues], ["real"])


class RenderSegments(unittest.TestCase):
    def test_keeps_only_what_the_renderer_needs(self):
        result = render_segments([
            {
                "take": "A",
                "start": 6.58,
                "end": 11.08,
                "beat": "hook",
                "kind": "structural",
                "reason": "a long editorial justification that the renderer must not carry",
                "padded_start": 6.51,
                "padded_end": 11.15,
                "duration": 4.687,
                "offset": 0.0,
            }
        ])
        self.assertEqual(
            result,
            [{"offset": 0.0, "duration": 4.687, "beat": "hook", "kind": "structural"}],
        )

    def test_defaults_kind_to_mechanical(self):
        result = render_segments([{"offset": 1.0, "duration": 2.0, "beat": "point"}])
        self.assertEqual(result[0]["kind"], "mechanical")

    def test_preserves_order_and_offsets(self):
        result = render_segments([
            {"offset": 0.0, "duration": 4.687, "beat": "hook", "kind": "structural"},
            {"offset": 4.687, "duration": 5.721, "beat": "answer", "kind": "structural"},
            {"offset": 10.408, "duration": 4.088, "beat": "point", "kind": "mechanical"},
        ])
        self.assertEqual([s["beat"] for s in result], ["hook", "answer", "point"])
        # Offsets must be contiguous: each segment starts where the last ended.
        for previous, nxt in zip(result, result[1:]):
            self.assertAlmostEqual(previous["offset"] + previous["duration"], nxt["offset"], places=3)

    def test_empty_plan_yields_empty_list(self):
        self.assertEqual(render_segments([]), [])


if __name__ == "__main__":
    unittest.main()
