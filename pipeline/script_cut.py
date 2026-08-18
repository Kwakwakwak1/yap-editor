#!/usr/bin/env python3
"""Draft a cut from a script: the best delivery of every line, across takes.

The editorial pass infers intent from the transcript alone today, and
`mark_flubs` guesses a retake by looking for a near-duplicate sentence prefix
of four or more tokens -- a heuristic standing in for a fact nobody supplied.
When a script exists, that fact exists.

The reel stops being "the best take" and becomes "the best of every line".
Three takes of the same script produce one cut that uses line 1 from take B,
line 2 from take A, and line 3 from take C, because that is what was actually
delivered best.

    from script_cut import draft
    plan = draft(alignment, floor=0.55)

WHAT THIS REFUSES TO DO
-----------------------

It does not force a match. A line no take delivered above the floor is reported
as a fallback, never guessed at, and a script the footage does not follow at all
produces no plan rather than a confident wrong one. Talking-to-camera footage
ad-libs constantly, and low-confidence alignment forced into a cut would make
script-driven drafting WORSE than the mechanical pass it replaces -- which is
the failure mode worth designing against, because it would be invisible.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

#: Below this, a line is not considered delivered. Same figure align.py uses,
#: imported rather than repeated so the two cannot drift.
try:  # pragma: no cover - import shape differs between CLI and package use
    from align import FLOOR
except ImportError:  # pragma: no cover
    FLOOR = 0.55

#: A cut needs most of its script to be worth calling script-driven. Below
#: this, the honest answer is "use the mechanical draft", not "here is a cut
#: with half the video missing".
MIN_COVERAGE = 0.6


def _candidates(alignment: Dict[str, Any], index: int) -> List[Dict[str, Any]]:
    """Every take's attempt at one script line, best first.

    Sorted by confidence, then by how TIGHT the span is -- the fewest extra
    words around the line. Two takes that both nail a line are not equally
    good: the one that said it without a run-up is the one to cut.
    """
    found = []
    for take, detail in alignment.get("takes", {}).items():
        for row in detail.get("lines", []):
            if row["index"] != index:
                continue
            if row["from"] is None:
                continue
            found.append({
                "take": take,
                "confidence": row["confidence"],
                "from": row["from"],
                "to": row["to"],
                "words": len(row.get("words", [])),
                "line": row["line"],
                "beat": row.get("beat", ""),
            })
    return sorted(found, key=lambda row: (-row["confidence"], row["words"]))


def _reason(chosen: Dict[str, Any], candidates: Sequence[Dict[str, Any]]) -> str:
    """Why this span, in words a human reviewing the cut can check.

    assemble.py refuses a structural cut with no reason, which is a good
    forcing function that used to cost the editor real effort per segment.
    With an alignment it is derived: the take, the score, and what it beat.
    """
    if len(candidates) == 1:
        return (f"line {chosen['index']}: the only take that delivered it "
                f"({chosen['confidence']:.2f})")
    runner_up = candidates[1]
    if chosen["confidence"] > runner_up["confidence"]:
        return (f"line {chosen['index']}: best of {len(candidates)} takes "
                f"({chosen['confidence']:.2f} vs {runner_up['confidence']:.2f})")
    return (f"line {chosen['index']}: tied at {chosen['confidence']:.2f} across "
            f"{len(candidates)} takes, took the tightest delivery "
            f"({chosen['words']} words vs {runner_up['words']})")


def draft(alignment: Dict[str, Any], floor: float = FLOOR,
          min_coverage: float = MIN_COVERAGE) -> Dict[str, Any]:
    """A cut plan's segments, plus what could not be planned.

    Returns `{"segments": [...], "fallbacks": [...], "coverage": float,
    "usable": bool}`. `usable` is False when too little of the script was
    delivered to draft from -- the caller then keeps the mechanical draft, and
    the review UI shows why rather than showing a cut with holes in it.

    Segments are in SCRIPT order, not take order, which is the whole point:
    the cut follows the writing, and the take changes wherever a different one
    delivered the line better.
    """
    total = alignment.get("lines", 0)
    segments: List[Dict[str, Any]] = []
    fallbacks: List[Dict[str, Any]] = []

    for index in range(1, total + 1):
        candidates = [c for c in _candidates(alignment, index) if c["confidence"] >= floor]
        if not candidates:
            best = _candidates(alignment, index)
            fallbacks.append({
                "index": index,
                # The best anybody managed, so a person can see whether this
                # was close or nowhere near.
                "confidence": best[0]["confidence"] if best else 0.0,
                "reason": "no take delivered this line above the floor",
            })
            continue

        chosen = dict(candidates[0], index=index)
        segments.append({
            "take": chosen["take"],
            "start": chosen["from"],
            "end": chosen["to"],
            "beat": chosen["beat"] or "line",
            # Every script-driven segment is structural: it exists because the
            # writing says it should, which is a decision rather than a
            # mechanical trim.
            "kind": "structural",
            "reason": _reason(chosen, candidates),
            "line_index": index,
            "confidence": chosen["confidence"],
        })

    coverage = round(len(segments) / total, 3) if total else 0.0
    return {
        "segments": segments,
        "fallbacks": fallbacks,
        "coverage": coverage,
        "usable": bool(segments) and coverage >= min_coverage,
    }


def summarise(plan: Dict[str, Any]) -> str:
    """One line for a log, naming what fell back rather than only what worked."""
    if not plan["usable"]:
        return (f"script-driven draft refused: {plan['coverage'] * 100:.0f}% of the "
                f"script was delivered, below the {MIN_COVERAGE * 100:.0f}% floor")
    takes = sorted({segment["take"] for segment in plan["segments"]})
    detail = f"{len(plan['segments'])} lines from take(s) {', '.join(takes)}"
    if plan["fallbacks"]:
        missing = ", ".join(str(row["index"]) for row in plan["fallbacks"])
        detail += f"; lines {missing} fell back to the mechanical draft"
    return detail
