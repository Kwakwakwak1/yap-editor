#!/usr/bin/env python3
"""Match what was said to what was written.

A take is one recording of a script. This finds, for each line of the script,
the span of transcribed words in each take that says it -- with a confidence
figure, because the interesting cases are the ones where nothing does.

    python3 pipeline/align.py --script script.txt --words build/A.words.json --take A
    python3 pipeline/align.py --script script.txt --plan build/slug/cuts.json

Output is `<take>.align.json`: per script line, the best matching word span in
each take, its confidence, and the words it actually covers.

WHY SequenceMatcher
-------------------

`verify.py` already diffs a planned word list against a transcribed one with
`difflib.SequenceMatcher` over normalised tokens, and its join-integrity check
is the same shape of problem: two word sequences that should mostly agree.
Reusing the library and the normaliser means this is a known quantity here
rather than a new dependency with new failure modes -- and `normalize_word` is
the same function on both sides, so "said" and "Said," are the same token in
both checks.

WHAT CONFIDENCE MEANS
---------------------

The ratio of matched tokens to script tokens for that line. 1.0 is a line
delivered verbatim; 0.0 is a line that was never said. It is deliberately NOT
symmetric -- a take that says the line plus an ad-lib still delivered the line,
and should not be penalised for saying more.

That asymmetry is the whole point. Talking-to-camera footage ad-libs
constantly, and a symmetric score would mark every honest take as a poor
match, which is how script-driven cutting ends up worse than the mechanical
draft it replaces.
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import load_json, normalize_word, write_json  # noqa: E402

#: Below this, a line is treated as not delivered in that take. Tuned to sit
#: under a half-remembered delivery and above a coincidental word overlap: two
#: unrelated English sentences routinely share "the", "a" and "to", which is
#: enough to score 0.2 on a short line.
FLOOR = 0.55


def script_lines(text: str) -> List[Dict[str, Any]]:
    """The spoken lines of a script, in order, with their own indices.

    One spoken line per line of the file, which is the shape yap-writer's
    drafts already have and the shape `shotlist.py` times. Blank lines
    separate; a line that is only punctuation carries no tokens and is kept
    anyway, so indices line up with the shot list.

    Markdown headings are dropped rather than treated as speech: `# Hook` is
    structure, and aligning it would look for someone saying the word "hook".
    """
    lines: List[Dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append({
            "index": len(lines) + 1,
            "line": line,
            "tokens": [t for t in (normalize_word(w) for w in line.split()) if t],
        })
    return lines


def transcript_tokens(words: Sequence[Dict[str, Any]]) -> List[str]:
    return [normalize_word(str(word.get("word", ""))) for word in words]


def best_span(
    line_tokens: Sequence[str], tokens: Sequence[str]
) -> tuple[int, int, float]:
    """Where in `tokens` this line was said: (start, end, confidence).

    `end` is exclusive. A line with no tokens -- punctuation only -- matches
    nothing and scores 0.0 rather than dividing by zero.

    The span is the whole matched region including anything the speaker put in
    the middle of it, not just the matching blocks: a line delivered with a
    stumble in the middle is one span with a gap, and cutting only the matching
    parts would splice the stumble out mid-word.
    """
    if not line_tokens or not tokens:
        return 0, 0, 0.0

    matcher = difflib.SequenceMatcher(a=list(line_tokens), b=list(tokens), autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size]
    if not blocks:
        return 0, 0, 0.0

    matched = sum(block.size for block in blocks)
    start = blocks[0].b
    end = blocks[-1].b + blocks[-1].size
    return start, end, round(matched / len(line_tokens), 3)


def align_take(
    lines: Sequence[Dict[str, Any]], words: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Every script line against one take's transcript.

    Lines are matched in order and each search starts after the previous
    line's match, because a take is a performance of the script from top to
    bottom. Searching the whole transcript for every line independently lets a
    repeated phrase -- "so", "here's the thing", a brand name -- match a much
    later occurrence and produce a cut that jumps backwards.

    A line that scores below FLOOR does not consume any transcript: the next
    line searches from the same place, so one skipped line does not drag every
    line after it out of position.
    """
    tokens = transcript_tokens(words)
    results: List[Dict[str, Any]] = []
    cursor = 0

    for line in lines:
        window = tokens[cursor:]
        start, end, confidence = best_span(line["tokens"], window)
        if confidence >= FLOOR and end > start:
            absolute_start = cursor + start
            absolute_end = cursor + end
            cursor = absolute_end
            results.append({
                "index": line["index"],
                "line": line["line"],
                "confidence": confidence,
                "from": _time_of(words, absolute_start, "start"),
                "to": _time_of(words, absolute_end - 1, "end"),
                "words": [
                    str(words[i].get("word", "")).strip()
                    for i in range(absolute_start, absolute_end)
                ],
            })
        else:
            # Recorded, not omitted. "This line was not delivered in this take"
            # is a fact the cut planner needs -- it is how a missing line is
            # told apart from a line nobody wrote.
            results.append({
                "index": line["index"],
                "line": line["line"],
                "confidence": confidence,
                "from": None,
                "to": None,
                "words": [],
            })
    return results


def _time_of(words: Sequence[Dict[str, Any]], index: int, key: str) -> float | None:
    if index < 0 or index >= len(words):
        return None
    value = words[index].get(key)
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def coverage(alignment: Sequence[Dict[str, Any]]) -> float:
    """How much of the script this take delivered, 0.0 to 1.0.

    The figure a human reads to decide whether the take is worth cutting from
    at all, and the one #89 uses to decide whether to fall back to the
    mechanical draft rather than force a bad match.
    """
    if not alignment:
        return 0.0
    delivered = sum(1 for row in alignment if row["from"] is not None)
    return round(delivered / len(alignment), 3)


def align(script: str, takes: Dict[str, Sequence[Dict[str, Any]]]) -> Dict[str, Any]:
    lines = script_lines(script)
    return {
        "version": 1,
        "lines": len(lines),
        "takes": {
            take: {
                "coverage": coverage(rows),
                "lines": rows,
            }
            for take, rows in (
                (take, align_take(lines, words)) for take, words in takes.items()
            )
        },
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--words", type=Path, action="append", default=[],
                        help="a take's whisper output; repeatable")
    parser.add_argument("--take", action="append", default=[],
                        help="the take name for each --words, in the same order")
    parser.add_argument("--out", type=Path, help="where to write the alignment")
    args = parser.parse_args(argv)

    if len(args.take) != len(args.words):
        parser.error("give one --take for each --words")

    takes: Dict[str, Sequence[Dict[str, Any]]] = {}
    for name, path in zip(args.take, args.words):
        data = load_json(path)
        takes[name] = data.get("words", []) if isinstance(data, dict) else data

    result = align(args.script.read_text(encoding="utf-8"), takes)

    if args.out:
        write_json(args.out, result)
        print(f"Wrote {args.out}")

    for take, detail in result["takes"].items():
        missing = [row["index"] for row in detail["lines"] if row["from"] is None]
        print(f"{take}: {detail['coverage'] * 100:.0f}% of {result['lines']} lines"
              + (f", missing {missing}" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
