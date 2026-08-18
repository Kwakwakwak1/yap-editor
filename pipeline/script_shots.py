#!/usr/bin/env python3
"""Read a script's shot list, and turn it into furniture and b-roll slots.

A stored script carries `shots`: one object per spoken line, with an index, the
line, a word count, in/out timecodes, and -- where the writer supplied them --
an editorial roll (A-roll or B-roll) and a description of what is on screen.

THE CONTRACT, AND WHY IT IS TOLERANT
------------------------------------

`shotlist.py` emits `index`, `line`, `words`, `start`, `end`, `seconds`. It does
NOT emit `roll` or the on-screen description: those come from step 9 of
yap-writer's SKILL.md, which instructs the model writing the script to add them.
So the timed skeleton is produced by code and the editorial half is produced by
a language model, and no schema anywhere pins the key names.

That was worth checking rather than assuming -- the handoff note says `shots`
"already carries B-roll staging per line", and the field it names is written by
nobody in particular.

The API stores `shots` unmodelled on purpose, matching `CutPlan.segments`: the
producing tool owns the shape. So the contract is pinned at the two ends
instead. yap-writer's SKILL.md names the keys it must write; this reader accepts
the reasonable spellings of them and treats anything it does not recognise as
absent. An unrecognised roll means no b-roll slot, never a crash and never a
guess -- the same philosophy as an unknown style preset degrading to none.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

#: What counts as "cut away from the speaker here". Spellings a writer or a
#: model plausibly produces, all meaning the same thing.
B_ROLL = {"b", "b-roll", "broll", "b roll", "cutaway", "cut-away"}
A_ROLL = {"a", "a-roll", "aroll", "a roll", "talking-head", "talking head", "camera"}

#: Where the on-screen description might be. `onscreen` is what SKILL.md now
#: names; the rest are what a model reaches for unprompted.
DESCRIPTION_KEYS = ("onscreen", "on_screen", "description", "visual", "shows", "screen")


def roll_of(shot: Dict[str, Any]) -> str | None:
    """`"a"`, `"b"`, or None when the shot does not say.

    None is a real answer and not a default. "This line has no roll assigned"
    and "this line is A-roll" are different facts: the first means the writer
    did not decide, and inventing a decision for them is how a b-roll slot
    appears over a beat that should have stayed on the speaker's face.
    """
    raw = shot.get("roll")
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if value in B_ROLL:
        return "b"
    if value in A_ROLL:
        return "a"
    return None


def description_of(shot: Dict[str, Any]) -> str:
    """What is on screen for this line, or an empty string."""
    for key in DESCRIPTION_KEYS:
        value = shot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _index(shot: Dict[str, Any]) -> int | None:
    value = shot.get("index")
    return value if isinstance(value, int) else None


def broll_slots(
    shots: Sequence[Dict[str, Any]],
    segments: Sequence[Dict[str, Any]],
    never_over_hook: bool = True,
) -> List[Dict[str, Any]]:
    """Where the cut should cut away, in the REEL's timeline.

    A shot list is written against the script's timeline, which is what the
    writer expected the delivery to take. The cut is on the reel's timeline,
    which is what the delivery actually took. They are different, so slots are
    placed by matching `line_index` -- the link a script-driven cut already
    carries -- rather than by trusting the script's timecodes to land anywhere.

    A cut assembled without a script carries no `line_index` and gets no slots,
    which is correct: nothing here knows which line a mechanically-chosen
    segment corresponds to, and guessing by position would put a b-roll shot
    over whatever happened to be third.
    """
    by_line = {
        index: shot for shot in shots
        if (index := _index(shot)) is not None
    }
    slots: List[Dict[str, Any]] = []
    offset = 0.0

    for position, segment in enumerate(segments):
        duration = float(segment.get("duration") or 0.0)
        if not duration:
            duration = float(segment.get("end", 0.0)) - float(segment.get("start", 0.0))
        line_index = segment.get("line_index")
        shot = by_line.get(line_index) if line_index is not None else None

        if shot is not None and roll_of(shot) == "b":
            # The hook is the one beat that must stay on the speaker: a reel
            # that opens on a cutaway has thrown away the only moment anyone
            # decides whether to keep watching.
            if not (never_over_hook and position == 0):
                slots.append({
                    "line_index": line_index,
                    "beat": segment.get("beat", ""),
                    "from": round(offset, 3),
                    "to": round(offset + duration, 3),
                    "onscreen": description_of(shot),
                })
        offset += duration

    return slots


def step_labels(shots: Sequence[Dict[str, Any]],
                segments: Sequence[Dict[str, Any]]) -> Dict[int, str]:
    """`{line_index: label}` for the on-screen label a tutorial style draws.

    The label is the part of a `# Step 2 :: Pat it dry` heading after the `::`.
    A shot's own description is deliberately NOT used as a fallback: it says
    what the CAMERA is doing ("hands blotting the fillet with a towel"), and
    putting that in a step badge tells the viewer something they can already
    see instead of what step they are on.
    """
    labels: Dict[int, str] = {}
    for segment in segments:
        line_index = segment.get("line_index")
        label = str(segment.get("label") or "").strip()
        if line_index is not None and label:
            labels[line_index] = label
    return labels


def annotate(segments: Sequence[Dict[str, Any]],
             shots: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Segments with their shot's editorial fields carried onto them.

    Additive and lossless: a segment keeps everything it had. A cut with no
    script, or a script whose writer assigned no rolls, comes back unchanged --
    which is what makes this safe to call unconditionally.
    """
    by_line = {
        index: shot for shot in shots
        if (index := _index(shot)) is not None
    }
    out: List[Dict[str, Any]] = []
    for segment in segments:
        shot = by_line.get(segment.get("line_index"))
        if shot is None:
            out.append(dict(segment))
            continue
        roll = roll_of(shot)
        enriched = dict(segment)
        if roll:
            enriched["roll"] = roll
        description = description_of(shot)
        if description:
            enriched["onscreen"] = description
        out.append(enriched)
    return out
