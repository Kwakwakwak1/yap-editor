#!/usr/bin/env python3
"""Draft a mechanical cuts.json from word timestamps."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from common import load_json, media_duration, repo_path, safe_record_path, write_json


FILLERS = {"sorry", "wait", "hold on", "let me try that again"}
SENTENCE_END = re.compile(r"[.!?][\"')\]]*$")


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", value.lower())


def sentence_groups(words: Sequence[Dict[str, Any]]) -> List[List[int]]:
    groups: List[List[int]] = []
    current: List[int] = []
    for index, item in enumerate(words):
        current.append(index)
        if SENTENCE_END.search(str(item.get("word", ""))):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def group_tokens(words: Sequence[Dict[str, Any]], indexes: Sequence[int]) -> List[str]:
    return [token for token in (normalized(str(words[i].get("word", ""))) for i in indexes) if token]


def common_prefix_length(left: Sequence[str], right: Sequence[str]) -> int:
    count = 0
    for a, b in zip(left, right):
        if a != b:
            break
        count += 1
    return count


def mark_flubs(
    words: Sequence[Dict[str, Any]],
    groups: Sequence[Sequence[int]],
    markers: Sequence[str],
) -> Tuple[Set[int], int, int]:
    dropped: Set[int] = set()
    flub_resolutions = 0
    filler_drops = 0
    marker_tokens = [normalized(marker) for marker in markers if normalized(marker)]
    token_groups = [group_tokens(words, group) for group in groups]

    for index, tokens in enumerate(token_groups):
        sentence_text = " ".join(tokens)
        if sentence_text in FILLERS:
            dropped.add(index)
            filler_drops += 1
            continue
        if any(marker in sentence_text for marker in marker_tokens):
            dropped.add(index)
            filler_drops += 1

    for earlier in range(len(groups)):
        if earlier in dropped:
            continue
        for later in range(earlier + 1, len(groups)):
            if later in dropped:
                continue
            left, right = token_groups[earlier], token_groups[later]
            prefix = common_prefix_length(left, right)
            one_is_prefix = bool(left and right and (left == right[:len(left)] or right == left[:len(right)]))
            if prefix >= 4 or one_is_prefix:
                dropped.add(earlier)
                flub_resolutions += 1
                break
    return dropped, flub_resolutions, filler_drops


def parse_silences(output: str) -> List[Tuple[float, float]]:
    starts: List[float] = []
    silences: List[Tuple[float, float]] = []
    for line in output.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            starts.append(float(start_match.group(1)))
        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end_match and starts:
            silences.append((starts.pop(0), float(end_match.group(1))))
    return silences


def cross_check_media(media: Path, noise: str, minimum: float, word_gaps: Sequence[Tuple[float, float]]) -> None:
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-i", str(media), "-af",
                f"silencedetect=noise={noise}:d={minimum}", "-f", "null", "-",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(f"Silence cross-check SKIPPED: ffmpeg unavailable ({exc})")
        return
    detected = parse_silences(result.stderr)
    disagreements: List[str] = []
    if abs(len(detected) - len(word_gaps)) > 0:
        disagreements.append(f"word gaps={len(word_gaps)} vs silencedetect={len(detected)}")
    for index, (word_start, word_end) in enumerate(word_gaps):
        if index >= len(detected):
            break
        silence_start, silence_end = detected[index]
        if abs(word_start - silence_start) > 0.35 or abs(word_end - silence_end) > 0.35:
            disagreements.append(
                f"gap {index + 1}: words {word_start:.3f}-{word_end:.3f}s vs "
                f"audio {silence_start:.3f}-{silence_end:.3f}s"
            )
    if disagreements:
        print("Silence cross-check disagreement:")
        for item in disagreements:
            print(f"  {item}")
    else:
        print(f"Silence cross-check agrees on {len(word_gaps)} gap(s)")


def choose_slug(words_path: Path, media: Optional[Path], supplied: Optional[str]) -> str:
    if supplied:
        return supplied
    source = media or words_path
    name = source.stem
    if name.endswith(".words"):
        name = name[:-6]
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return slug or "draft"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("words", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--media", type=Path)
    parser.add_argument("--slug")
    parser.add_argument("--min-silence", type=float, default=0.5)
    parser.add_argument("--payoff-hold", type=float, default=0.4)
    parser.add_argument("--noise", default="-35dB")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--marker", action="append", default=[])
    parser.add_argument(
        "--energy", action="store_true",
        help="measure the take and use it: snap cuts to the quietest moment "
             "near each boundary, and drop voiced regions the transcript says "
             "are empty (um, uh). Needs --media.")
    parser.add_argument(
        "--energy-out", type=Path,
        help="also write the measured envelope, for music ducking to reuse")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    words_path = repo_path(str(args.words))
    output = repo_path(str(args.output))
    media = repo_path(str(args.media)) if args.media else None
    try:
        data = load_json(words_path)
    except (OSError, ValueError) as exc:
        print(f"ERROR: could not read words JSON: {exc}", file=sys.stderr)
        return 1
    words = data.get("words") if isinstance(data, dict) else None
    if not isinstance(words, list) or not words:
        print("ERROR: words JSON contains no word timestamps", file=sys.stderr)
        return 1
    if args.min_silence <= 0 or args.payoff_hold < 0:
        print("ERROR: silence thresholds must be positive", file=sys.stderr)
        return 1
    if media and not media.exists():
        print(f"ERROR: media file not found: {args.media}", file=sys.stderr)
        return 1

    groups = sentence_groups(words)
    dropped_groups, flub_count, filler_count = mark_flubs(words, groups, args.marker)
    retained_indexes = [
        index
        for group_index, group in enumerate(groups)
        if group_index not in dropped_groups
        for index in group
    ]
    retained = [words[index] for index in retained_indexes]
    if not retained:
        print("ERROR: mechanical passes removed every word", file=sys.stderr)
        return 1

    segments: List[Dict[str, Any]] = []
    gaps: List[Tuple[float, float]] = []
    current_start = float(retained[0]["start"])
    previous = retained[0]
    for item in retained[1:]:
        gap_start = float(previous["end"])
        gap_end = float(item["start"])
        gap = gap_end - gap_start
        if gap >= args.min_silence:
            segments.append({
                "take": "A",
                "start": round(current_start, 3),
                "end": round(float(previous["end"]), 3),
                "beat": f"mechanical-{len(segments) + 1:03d}",
                "kind": "mechanical",
            })
            gaps.append((gap_start, gap_end))
            current_start = gap_end
        previous = item
    segments.append({
        "take": "A",
        "start": round(current_start, 3),
        "end": round(float(previous["end"]), 3),
        "beat": f"mechanical-{len(segments) + 1:03d}",
        "kind": "mechanical",
    })

    # Keep up to payoff_hold seconds of a pause immediately before either of the
    # final two segments. Word timestamps remain the authority for the cut.
    first_payoff_index = max(1, len(segments) - 2)
    for boundary, gap in enumerate(gaps):
        next_index = boundary + 1
        if next_index >= first_payoff_index:
            gap_length = gap[1] - gap[0]
            retained_pause = min(args.payoff_hold, gap_length)
            segments[boundary]["end"] = round(gap[1] - retained_pause, 3)

    # The energy pass, if asked for. Deliberately opt-in: it is a second
    # measurement of the media and it changes the cut, so a draft that did not
    # ask for it gets exactly the cut word timestamps imply.
    energy_report = ""
    if args.energy and media:
        from energy import envelope as build_envelope
        from energy import fillers as find_fillers
        from energy import measure as measure_energy
        from energy import remove as remove_fillers
        from energy import snap as snap_boundary

        env = build_envelope(measure_energy(media))
        if not env["levels"]:
            print("Energy pass SKIPPED: no audio measured", file=sys.stderr)
        else:
            found = find_fillers(retained, env)
            # Splits a segment around a filler inside it. A filler that landed
            # in a gap is already out of the cut and is not counted -- the
            # first version of this narrowed already-placed boundaries and
            # announced a cut it had not made.
            segments, removed = remove_fillers(segments, found)

            # Snap last, so a boundary the filler pass just moved is snapped to
            # the quiet either side of the sound that was removed.
            for segment in segments:
                segment["start"] = snap_boundary(segment["start"], env)
                segment["end"] = snap_boundary(segment["end"], env)

            if args.energy_out:
                write_json(repo_path(str(args.energy_out)), env)
            energy_report = (
                f"Energy pass: floor {env['floor']:.1f} dBFS, speech "
                f"{env['speech']:.1f} dBFS, {removed} of {len(found)} filler "
                f"region(s) were inside the cut and were removed, "
                f"every boundary snapped to the nearest quiet moment")
    elif args.energy:
        print("Energy pass SKIPPED: --energy needs --media", file=sys.stderr)

    word_gaps = []
    for left, right in zip(retained, retained[1:]):
        if float(right["start"]) - float(left["end"]) >= args.min_silence:
            word_gaps.append((float(left["end"]), float(right["start"])))
    if media:
        cross_check_media(media, args.noise, args.min_silence, word_gaps)

    slug = choose_slug(words_path, media, args.slug)
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        print("ERROR: slug must match [a-z0-9-]+", file=sys.stderr)
        return 1
    source = data.get("source", safe_record_path(media or words_path))
    media_value = safe_record_path(media) if media else source
    output_payload = {
        "version": 1,
        "slug": slug,
        "fps": args.fps,
        "headline": "",
        "pad": [0.07, 0.07],
        "loudness": {"i": -14, "tp": -1.5, "lra": 11},
        "takes": {"A": {"path": media_value, "words": safe_record_path(words_path)}},
        "segments": segments,
    }
    write_json(output, output_payload)
    print(f"Wrote draft {safe_record_path(output)} with {len(segments)} mechanical segment(s)")
    print(f"Mechanical passes performed: flub resolution ({flub_count} retake(s), {filler_count} filler/marker sentence(s)) and silence pass")
    if energy_report:
        print(energy_report)
    print("Not done by plan.py: best-take selection, tangent trims, and hook surgery. Those are the human's job.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
