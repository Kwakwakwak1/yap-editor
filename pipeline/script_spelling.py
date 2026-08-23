#!/usr/bin/env python3
"""Spell captions the way the script does, without putting unsaid words on screen.

Whisper mangles brand names and proper nouns -- "kwakwakwak" comes back as
"quack wack wack", "Kitchen Pal" as "kitchen pow". The script has them right,
so where alignment is confident the script's spelling wins.

    from script_spelling import correct_cues
    cues = correct_cues(cues, alignment_rows)

THE LINE THIS MUST NOT CROSS
----------------------------

This substitutes SPELLING for tokens that already aligned. It never inserts a
script word that is missing from the audio.

That is the difference between fixing "quack wack wack" and fabricating a
sentence, and it is the whole risk of the feature: captions are a transcript of
what was said, and a caption containing a word nobody said is a lie the viewer
has no way to detect. So the rule is mechanical rather than a matter of
judgement -- a correction must be a one-for-one replacement of a word that is
already there, at a position alignment matched, and anything else is refused.

It also means the join-integrity check in verify.py keeps diffing against the
TRANSCRIPT, never the script. The script is what was meant; the transcript is
what was said. Confusing the two would make the check flag every ad-lib as edit
damage.
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import normalize_word  # noqa: E402

#: A correction has to be a plausible misspelling, not a different word.
#: Measured rather than guessed, over pairs from real transcripts:
#:
#:   should fix     instagrams/instagram 0.947  fillet/filet 0.909
#:                  tay/taye 0.857  reel/real 0.750  sear/seer 0.750
#:                  mise/meese 0.667  quackwackwack/kwakwakwak 0.609
#:   should refuse  twelve/twenty 0.500  this/that 0.500  hours/minutes 0.333
#:                  cook/bake 0.250  chicken/salmon 0.154  dry/wet 0.000
#:
#: 0.55 sits in the gap between those two groups. The cost of a wrong
#: correction is a caption that misquotes someone; the cost of a missed one is
#: a caption spelled the way whisper heard it, which is where we started.
SIMILARITY = 0.55

#: WHAT THIS CANNOT DO
#:
#: Short phonetic mishearings. "pow" for "pal" is 0.333 and "kwak" for "quack"
#: is 0.222 -- both below several pairs that MUST be refused ("twelve" for
#: "twenty" is 0.500). No character-similarity threshold separates them, because
#: they are not similar as strings; they are similar as sounds.
#:
#: Fixing those needs a phonetic comparison, and it is left undone deliberately
#: rather than approximated: a threshold low enough to catch "pow"/"pal" also
#: rewrites "cook" to "bake".


def _similar(said: str, written: str) -> float:
    return difflib.SequenceMatcher(a=said, b=written, autojunk=False).ratio()


def plausible_respelling(said: str, written: str) -> bool:
    """Whether `written` is a plausible misspelling of `said`, not a different word.

    The public form of the threshold this module already applies. Exported so
    the manual-correction path in assemble.py holds a person to the same rule as
    the script pass, rather than carrying a second copy of the number -- which
    is how the two would come to disagree about what counts as a correction.
    """
    return _similar(said, written) >= SIMILARITY


def corrections_for(
    said: Sequence[str], written: Sequence[str]
) -> Dict[int, str]:
    """`{index into said: replacement}` for one aligned line.

    Only substitutions are taken. `difflib`'s `insert` and `delete` opcodes are
    deliberately ignored: an insert is a script word the speaker did not say,
    and taking it would put words on screen that were never spoken.

    A `replace` block of unequal length is also refused. Two said words
    becoming three written ones is not a spelling correction, it is a rewrite,
    and there is no one-to-one mapping to apply.
    """
    if not said or not written:
        return {}

    matcher = difflib.SequenceMatcher(
        a=[normalize_word(word) for word in said],
        b=[normalize_word(word) for word in written],
        autojunk=False,
    )
    out: Dict[int, str] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        # `insert` is a script word the speaker did not say; `delete` is a
        # spoken word the script does not have. Taking either would change WHAT
        # was said rather than how it is spelled, and that is the safety
        # property of this whole module.
        #
        # An uneven `replace` is refused for the same reason: two said words
        # becoming three written ones is a rewrite, not a spelling fix, and
        # there is no one-to-one mapping to apply. Matching best-effort inside
        # an uneven block was tried and is genuinely dangerous -- given a cue of
        # "honestly this bit is off script entirely" against the script line
        # "pat the fillet completely dry", it rewrote "honestly" and "entirely"
        # to "completely", both above threshold. The block rule is what stops
        # that, so it stays.
        if tag != "replace" or (i2 - i1) != (j2 - j1):
            continue
        for offset in range(i2 - i1):
            heard = normalize_word(said[i1 + offset])
            intended = written[j1 + offset]
            if not heard or not normalize_word(intended):
                continue
            if _similar(heard, normalize_word(intended)) >= SIMILARITY:
                out[i1 + offset] = intended
    return out


def respell(word: str, replacement: str) -> str:
    """The script's spelling, keeping the transcript's punctuation.

    Whisper attaches sentence punctuation to words and the script does not
    always agree about where a sentence ends. Dropping the transcript's comma
    would change the caption's grouping, which is a separate decision the style
    already owns.
    """
    def split(value: str) -> tuple[str, str, str]:
        head, core, tail = "", value, ""
        while core and not core[0].isalnum():
            head, core = head + core[0], core[1:]
        while core and not core[-1].isalnum():
            core, tail = core[:-1], core[-1] + tail
        return head, core, tail

    prefix, _, suffix = split(word)
    # The replacement's OWN punctuation is dropped, not kept alongside: the
    # script writes "kwakwakwak," and the transcript writes "quackwackwack,",
    # and keeping both produces "kwakwakwak,,".
    _, core, _ = split(replacement)
    return f"{prefix}{core or replacement}{suffix}"


def correct_cue(cue: Dict[str, Any], written: Sequence[str]) -> Dict[str, Any]:
    """One cue, respelled against the script line it aligned to.

    Timings are untouched. A correction changes how a word is written, never
    when it is said, so the caption still lands on the frame the speaker said
    it on.
    """
    words = cue.get("words") or []
    if not words:
        return cue

    said = [str(word.get("text", "")) for word in words]
    corrections = corrections_for(said, written)
    if not corrections:
        return cue

    fixed = [
        dict(word, text=respell(str(word.get("text", "")), corrections[index]))
        if index in corrections else word
        for index, word in enumerate(words)
    ]
    return dict(cue, words=fixed, text=" ".join(word["text"] for word in fixed))


def correct_cues(
    cues: Sequence[Dict[str, Any]],
    lines: Sequence[Dict[str, Any]],
    floor: float = 0.85,
) -> List[Dict[str, Any]]:
    """Every cue, respelled from the aligned script lines that overlap it.

    `floor` is deliberately higher than alignment's own: locating a line well
    enough to cut from it is a lower bar than trusting its spelling over what
    was actually heard. A line matched at 0.6 is the right span and the wrong
    authority.
    """
    confident = [
        row for row in lines
        if row.get("from") is not None and row.get("confidence", 0) >= floor
    ]
    if not confident:
        return list(cues)

    out: List[Dict[str, Any]] = []
    for cue in cues:
        written: List[str] = []
        for row in confident:
            # A cue is a few words and routinely straddles the boundary between
            # two script lines, so overlapping lines contribute -- but only the
            # PART of each line the cue actually overlaps.
            #
            # Handing the matcher both lines whole was the first attempt, and it
            # compared a 3-word cue against 9 written words: the block came out
            # uneven, the correction was refused, and loosening the block rule
            # to compensate rewrote ad-libs into script words. Slicing the
            # context to the overlap keeps the comparison one-for-one, which is
            # what makes the strict rule workable.
            written.extend(_overlapping_words(row, cue))
        out.append(correct_cue(cue, written) if written else cue)
    return out


def _overlapping_words(row: Dict[str, Any], cue: Dict[str, Any]) -> List[str]:
    """The part of an aligned script line that falls inside this cue.

    The line's words are assumed evenly spread across its aligned span, which
    is the same assumption `shotlist.py` makes when it times a draft. It is an
    approximation, and it only has to be good enough to bring the right handful
    of words into the comparison -- the similarity threshold is what decides
    whether any of them is a correction.
    """
    words = str(row.get("line", "")).split()
    start, end = row.get("from"), row.get("to")
    cue_from, cue_to = cue.get("from", 0.0), cue.get("to", 0.0)
    if not words or start is None or end is None:
        return []
    if start > cue_to or end < cue_from:
        return []

    span = end - start
    if span <= 0:
        return words

    first = max(0, int(len(words) * (cue_from - start) / span))
    last = min(len(words), int(round(len(words) * (cue_to - start) / span)) + 1)
    return words[first:last] or words
