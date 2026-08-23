#!/usr/bin/env python3
"""Execute a hand-edited cuts.json using deterministic FFmpeg passes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from common import (
    REPO_ROOT,
    display_path,
    ffprobe_json,
    has_audio,
    load_json,
    map_words_to_timeline,
    measure_loudness,
    normalize_word,
    project_rows_to_timeline,
    media_duration,
    repo_path,
    safe_record_path,
    run_command,
    video_pixel_format,
    write_json,
)
from grade import filter_string
from align import align
from script_spelling import correct_cues, plausible_respelling, respell


ENCODERS = {"libx264", "h264_videotoolbox", "h264_nvenc"}


def number(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc


def validate_plan(plan: Dict[str, Any]) -> Tuple[str, int, Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    # 2 adds the `style` block. 1 is still accepted: a plan written before style
    # packs must keep assembling, and it simply stages props without a style,
    # which the renderer treats as "use the defaults".
    if plan.get("version") not in (1, 2):
        raise ValueError("version must be 1 or 2")
    slug = plan.get("slug")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9-]+", slug):
        raise ValueError("slug must match [a-z0-9-]+")
    fps = int(plan.get("fps", 30))
    if fps <= 0:
        raise ValueError("fps must be positive")
    takes = plan.get("takes")
    if not isinstance(takes, dict) or not takes:
        raise ValueError("takes must be a non-empty object")
    normalized_takes: Dict[str, Dict[str, Any]] = {}
    for take_id, take in takes.items():
        if not isinstance(take, dict) or not isinstance(take.get("path"), str):
            raise ValueError(f"take {take_id!r} is missing path")
        path = repo_path(take["path"])
        if not path.exists():
            raise ValueError(f"take path does not exist for {take_id}: {take['path']}")
        normalized_takes[str(take_id)] = dict(take, _path=path)
    segments = plan.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("segments must be a non-empty array")
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError(f"segment {index} is not an object")
        take_id = segment.get("take")
        if take_id not in normalized_takes:
            raise ValueError(f"segment {index} names unknown take {take_id!r}")
        start = number(segment.get("start"), f"segment {index} start")
        end = number(segment.get("end"), f"segment {index} end")
        if start >= end:
            raise ValueError(f"segment {index} must have start < end")
        if segment.get("kind", "mechanical") == "structural" and not str(segment.get("reason", "")).strip():
            raise ValueError(f"segment {index} is structural but has no reason")
    return slug, fps, normalized_takes, segments


def encoder_args(encoder: str) -> List[str]:
    if encoder == "libx264":
        return ["-preset", "veryfast", "-crf", "18"]
    if encoder == "h264_videotoolbox":
        return ["-b:v", "8M"]
    return ["-preset", "p4", "-cq", "19"]


def caption_words(path: Path) -> List[Dict[str, Any]]:
    try:
        data = load_json(path)
    except (OSError, ValueError):
        return []
    return data.get("words", []) if isinstance(data, dict) else []


def apply_corrections(
    words: Sequence[Dict[str, Any]],
    corrections: Sequence[Dict[str, Any]],
    take_id: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Respell words a person corrected, and refuse the ones that no longer fit.

    Applied here, at load, rather than to the finished cues -- this is the last
    point where a word still knows which take and index it came from.
    map_words_to_timeline returns `{from, to, text}` and drops everything else,
    by design, so a correction pinned to a word cannot be matched after it.

    THE `from` CHECK IS THE SAFETY MECHANISM. Re-transcribing a take shifts
    every index after an inserted word. A correction applied blindly would then
    respell whatever moved into that slot -- on screen, in someone's voice, with
    nothing downstream able to tell. So a correction whose original text no
    longer matches is refused and reported, never applied.

    Matching ignores case and surrounding punctuation: whisper writes
    "Quackwackwack," and a person types the word. Refusing that would be a
    refusal for something that is not a difference.
    """
    out = [dict(word) for word in words]
    refused: List[str] = []
    for correction in corrections:
        if str(correction.get("take", "")) != str(take_id):
            continue
        index = int(correction.get("word_index", -1))
        was = str(correction.get("from", ""))
        now = str(correction.get("to", ""))
        if index < 0 or index >= len(out):
            refused.append(
                f"take {take_id} word {index} ({was!r} -> {now!r}): the "
                f"transcript has only {len(out)} words")
            continue
        found = str(out[index].get("word", ""))
        if normalize_word(found) != normalize_word(was):
            refused.append(
                f"take {take_id} word {index}: expected {was!r} but the "
                f"transcript now says {found!r} - the correction was not applied")
            continue
        # The same threshold the script pass is held to, and for the same
        # reason: a caption containing a word nobody said is a lie the viewer
        # has no way to detect. A person typing one is still typing one.
        #
        # `override` is how they say "I did say this" -- for a word whisper
        # mangled beyond a respelling, which script_spelling deliberately
        # cannot fix ("kwak" for "quack" is 0.222, below pairs that must be
        # refused). Explicit rather than implied, because it is the only path
        # that can put an unheard word on screen.
        if not correction.get("override") and not plausible_respelling(
                normalize_word(found), normalize_word(now)):
            refused.append(
                f"take {take_id} word {index}: {now!r} is not a respelling of "
                f"{found!r} - set override on the correction to apply it anyway")
            continue
        # respell() keeps the transcript's punctuation, which is the same split
        # the script pass makes: a comma is not part of what somebody corrected,
        # and dropping it would change the caption's grouping.
        out[index] = dict(out[index], word=respell(found, now), manual=True)
    return out, refused


def sentence_end(word: str) -> bool:
    return bool(re.search(r"[.!?][\"')\]]*$", word))


def caption_grouping(plan: Dict[str, Any], cli_words: int, cli_seconds: float) -> Tuple[int, float]:
    """How many words a cue holds, and for how long.

    The style decides this when it has an opinion: 3 words at 1.2s reads nothing
    like 7 at 3.0s, and that difference is as much a part of a style as its
    typeface. It was a CLI flag, which meant every style got whatever the worker
    happened to pass.

    The CLI values remain the default, so a plan with no style -- or a style
    that declines to say -- assembles exactly as it always did.
    """
    grouping = (((plan.get("style") or {}).get("captions") or {}).get("grouping") or {})
    words = grouping.get("maxWords")
    seconds = grouping.get("maxSeconds")
    return (
        int(words) if isinstance(words, (int, float)) and words > 0 else cli_words,
        float(seconds) if isinstance(seconds, (int, float)) and seconds > 0 else cli_seconds,
    )


def props_fingerprint(props: Dict[str, Any]) -> str:
    """A sha256 over everything in props except the fingerprint itself.

    The worker reads props back after staging and checks this. That read-back is
    inherited from `patch_accent`, which existed because assemble never wrote
    the accent and the worker had to patch it in afterwards -- but the check it
    performed guarded a real and separate failure: the MiniKWork sparse image
    can re-attach read-only, leaving an intact, stale, and entirely renderable
    props.json on disk. A render from that file succeeds and publishes the wrong
    look, which is the worst kind of failure because nothing reports it.

    Patching is gone now that the style is written at source. The witness is
    not, and it covers every field rather than one colour.
    """
    payload = {k: v for k, v in props.items() if k != "specHash"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_segments(resolved_segments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The per-segment timeline the renderer needs, and nothing more.

    `offset` and `duration` place each segment on the cut's timeline. `beat` and
    `kind` are what a style keys off: a transition can punctuate *structural*
    joins — where the edit made an editorial decision — while leaving
    *mechanical* joins invisible, and a beat name can drive an on-screen label.
    Both already exist in cuts.json, so this costs nothing to carry.

    The editorial `reason` is deliberately excluded. It exists for the human at
    the approval gate, it is long free text, and the renderer has no use for it.
    """
    return [
        {
            "offset": round(float(segment.get("offset", 0.0)), 3),
            "duration": round(float(segment.get("duration", 0.0)), 3),
            "beat": str(segment.get("beat", "")),
            # Matches the default used when this is printed for the operator, so
            # a segment without an explicit kind reads the same in both places.
            "kind": str(segment.get("kind", "mechanical")),
        }
        for segment in resolved_segments
    ]


def caption_cue(words: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Build one cue, carrying the real per-word timings alongside the joined text.

    The word times are measured -- transcribe.py always runs with
    `word_timestamps=True` -- but this function used to emit only `text`, so the
    renderer re-derived them by weighting each word's character length across the
    cue span. Every word-level caption effect was therefore an approximation of
    data we already had. `words` is additive: `from`, `to` and `text` are
    unchanged, so captions.srt and any existing consumer are unaffected.
    """
    return {
        "from": round(words[0]["from"], 3),
        "to": round(words[-1]["to"], 3),
        "text": " ".join(item["text"] for item in words),
        "words": [
            {
                "from": round(item["from"], 3),
                "to": round(item["to"], 3),
                "text": item["text"],
            }
            for item in words
        ],
    }


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d},{millis:03d}"


def _cue(current: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """A cue, flagged when any word in it was corrected by a person.

    The flag is what keeps the script pass off it. Both passes want authority
    over the same token, and a person who typed a correction outranks a script
    that merely disagrees with the transcript.
    """
    cue = caption_cue(current)
    if any(word.get("manual") for word in current):
        cue["manual"] = True
    return cue


def build_captions(
    plan: Dict[str, Any],
    resolved_segments: Sequence[Dict[str, Any]],
    max_words: int,
    max_seconds: float,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    takes = plan["takes"]
    loaded: Dict[str, List[Dict[str, Any]]] = {}
    skipped: List[str] = []
    corrections = plan.get("caption_corrections") or []
    refusals: List[str] = []
    for take_id, take in takes.items():
        words_value = take.get("words")
        if not words_value:
            skipped.append(str(take_id))
            continue
        words_path = repo_path(words_value)
        if not words_path.exists():
            skipped.append(str(take_id))
            continue
        # Corrections are applied HERE, before the words are projected onto the
        # cut and grouped into cues -- this is the last point at which a word
        # still knows which take and index it came from.
        corrected, refused = apply_corrections(
            caption_words(words_path), corrections, str(take_id))
        refusals.extend(refused)
        loaded[str(take_id)] = corrected

    mapped = map_words_to_timeline(loaded, resolved_segments)

    cues: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    for word in mapped:
        if not word["text"]:
            continue
        would_exceed_words = len(current) >= max_words
        would_exceed_time = bool(current) and word["to"] - current[0]["from"] > max_seconds
        if current and (would_exceed_words or would_exceed_time):
            cues.append(_cue(current))
            current = []
        current.append(word)
        if sentence_end(word["text"]):
            cues.append(_cue(current))
            current = []
    if current:
        cues.append(_cue(current))
    return cues, skipped, refusals


def write_captions(build_dir: Path, cues: Sequence[Dict[str, Any]]) -> None:
    srt_blocks: List[str] = []
    for index, cue in enumerate(cues, start=1):
        srt_blocks.append(
            f"{index}\n{format_srt_time(cue['from'])} --> {format_srt_time(cue['to'])}\n"
            f"{cue['text']}\n"
        )
    (build_dir / "captions.srt").write_text("\n".join(srt_blocks), encoding="utf-8")
    write_json(build_dir / "captions.json", list(cues))


def loudness_targets(plan: Dict[str, Any]) -> Tuple[float, float, float]:
    values = plan.get("loudness", {})
    return float(values.get("i", -14)), float(values.get("tp", -1.5)), float(values.get("lra", 11))


# Keys ffmpeg's analysis pass returns that its second pass consumes. Named
# rather than inlined so a measurement missing any one of them falls back to
# one pass instead of building a filter ffmpeg rejects at runtime.
MEASURED_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh")


def loudnorm_filter(
    target_i: float,
    target_tp: float,
    target_lra: float,
    measured: Optional[Dict[str, float]] = None,
) -> str:
    """The loudnorm filter string, two-pass when a measurement is available.

    One pass does not hit the target, and the tolerance verify.py holds it to is
    +/-1.0. Without the file's statistics up front, loudnorm runs its dynamic
    mode blind: it normalises the opening seconds on incomplete gating data and
    never fully recovers, which on a short reel is most of the file. Measured on
    a 12s cut: -15.86 LUFS against a -14 target, 1.86 off and a hard verify
    failure -- and its true peak came out at -1.30, past the -1.5 ceiling that
    same pass was asked to hold. Feeding the analysis pass's numbers back in
    took the identical file to -14.17.

    `linear=true` asks for one constant gain over the whole file, which is what
    keeps speech dynamics intact. ffmpeg falls back to its dynamic mode on its
    own when that gain would breach the true-peak ceiling, so this is a
    preference, not a promise -- and dynamic *with* the measurements is still
    far closer than dynamic without them.

    `offset` is pass one's `target_offset`, ffmpeg's own correction for the gap
    between what it predicts and what it measures. It is optional in a way the
    other four are not: without it the second pass still runs correctly, just
    slightly less accurately, so a measurement that lacks it is still worth
    using.
    """
    base = f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
    if not measured or any(key not in measured for key in MEASURED_KEYS):
        return base
    parts = [
        base,
        f"measured_I={measured['input_i']}",
        f"measured_TP={measured['input_tp']}",
        f"measured_LRA={measured['input_lra']}",
        f"measured_thresh={measured['input_thresh']}",
    ]
    if "target_offset" in measured:
        parts.append(f"offset={measured['target_offset']}")
    parts.append("linear=true")
    return ":".join(parts)


def respell_from_script(
    plan: Dict[str, Any],
    resolved_segments: Sequence[Dict[str, Any]],
    cues: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Spell the cues the way the attached script spells them.

    Whisper mangles brand names and proper nouns; the script has them right.
    Where alignment is confident, the script's spelling wins -- and where it is
    not, nothing happens, which is the common case and must stay cheap.

    THE CLOCK IS THE WHOLE TRICK. `align` reports each line's span in take
    time. These cues are in cut time. `correct_cues` decides which script words
    are context for which cue by overlapping the two, so they have to be on the
    same timeline first -- and getting that wrong fails silently, returning
    every cue unchanged while reporting that the pass ran.

    Returns the cues and how many changed, so the caller can say so. A count is
    the only signal that this did anything at all: a respelled cue looks exactly
    like a cue that was already right.
    """
    script = str(plan.get("script") or "").strip()
    if not script or not cues:
        return list(cues), 0

    words_by_take: Dict[str, List[Dict[str, Any]]] = {}
    for take_id, take in (plan.get("takes") or {}).items():
        value = take.get("words")
        if not value:
            continue
        path = repo_path(value)
        # Missing is tolerated for the same reason build_captions tolerates it:
        # a take with no transcript is a take with no captions, not a failed
        # assembly.
        if not path.exists():
            continue
        words_by_take[str(take_id)] = load_json(path).get("words", [])
    if not words_by_take:
        return list(cues), 0

    aligned = align(script, words_by_take)
    rows_by_take = {
        take: data.get("lines", [])
        for take, data in (aligned.get("takes") or {}).items()
    }
    # The words go with the rows: clipping a row to a segment has to count
    # words, not seconds, because the gaps between words are most of a take and
    # cutting is the act of removing them.
    rows = project_rows_to_timeline(rows_by_take, resolved_segments, words_by_take)
    if not rows:
        return list(cues), 0

    fixed = correct_cues(cues, rows)
    # A person who typed a correction outranks a script that merely disagrees
    # with the transcript. Both passes want authority over the same token; this
    # is where that is decided, and it is decided in the person's favour.
    fixed = [
        dict(original) if original.get("manual") else corrected
        for original, corrected in zip(cues, fixed)
    ]
    changed = sum(
        1 for before, after in zip(cues, fixed)
        if before.get("text") != after.get("text")
    )
    return fixed, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cuts", type=Path)
    parser.add_argument("--encoder", choices=sorted(ENCODERS), default="libx264")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--caption-words", type=int, default=5)
    parser.add_argument("--caption-max-seconds", type=float, default=2.4)
    parser.add_argument("--no-stage", action="store_true")
    args = parser.parse_args()
    try:
        plan_path = repo_path(str(args.cuts))
        plan = load_json(plan_path)
        slug, fps, takes, segments = validate_plan(plan)
        if args.width <= 0 or args.caption_words <= 0 or args.caption_max_seconds <= 0:
            raise ValueError("width, caption-words, and caption-max-seconds must be positive")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    build_dir = REPO_ROOT / "build" / slug
    build_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="segments-", dir=str(build_dir)))
    resolved_segments: List[Dict[str, Any]] = []
    try:
        take_durations: Dict[str, float] = {}
        take_audio: Dict[str, bool] = {}
        for take_id, take in takes.items():
            try:
                take_durations[take_id] = media_duration(take["_path"])
                take_audio[take_id] = has_audio(take["_path"])
            except (OSError, RuntimeError) as exc:
                raise RuntimeError(f"could not probe take {take_id}: {exc}") from exc

        pad = plan.get("pad", [0.06, 0.06])
        if not isinstance(pad, list) or len(pad) != 2:
            raise ValueError("pad must contain [before, after]")
        pad_before, pad_after = float(pad[0]), float(pad[1])
        if pad_before < 0 or pad_after < 0:
            raise ValueError("pad values cannot be negative")

        grade_filters = filter_string((plan.get("style") or {}).get("grade"))
        if grade_filters:
            print(f"Grading: {grade_filters}")

        print(f"Assembling {slug}: {len(segments)} segment(s), {fps} fps, width {args.width}")
        for index, segment in enumerate(segments, start=1):
            take_id = str(segment["take"])
            source = takes[take_id]["_path"]
            source_duration = take_durations[take_id]
            source_start = float(segment["start"])
            source_end = float(segment["end"])
            padded_start = max(0.0, source_start - pad_before)
            padded_end = min(source_duration, source_end + pad_after)
            if padded_end <= padded_start:
                raise ValueError(f"segment {index - 1} has no duration after padding")
            padded_duration = padded_end - padded_start
            segment_path = work_dir / f"seg_{index:03d}.mp4"
            command = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{padded_start:.3f}", "-i", str(source),
                "-t", f"{padded_duration:.3f}",
                "-map", "0:v:0", "-map", "0:a:0?",
                # The grade joins the chain that already runs, so it costs no
                # extra pass -- and because cut.mp4 is also the preview, the
                # preview shows the grade, which is the point of previewing a
                # style before approving it.
                #
                # After scale, before format: grading at the output size means
                # the same filter values look the same regardless of source
                # resolution, and format=yuv420p must stay last so the pixel
                # format verify.py checks is the one that lands.
                "-vf", ",".join(
                    part for part in (
                        f"scale={args.width}:-2",
                        f"fps={fps}",
                        grade_filters,
                        "format=yuv420p",
                    ) if part
                ),
                "-c:v", args.encoder,
                *encoder_args(args.encoder),
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-avoid_negative_ts", "make_zero",
                str(segment_path),
            ]
            print(f"  extracting segment {index}: {display_path(source)} {source_start:.3f}-{source_end:.3f}s")
            run_command(command)
            measured = media_duration(segment_path)
            resolved_segments.append({
                **segment,
                "padded_start": round(padded_start, 3),
                "padded_end": round(padded_end, 3),
                "duration": round(measured, 3),
                "offset": 0.0,
            })

        offset = 0.0
        for segment in resolved_segments:
            segment["offset"] = round(offset, 3)
            offset += float(segment["duration"])
        planned_duration = round(offset, 3)

        concat_list = work_dir / "concat.txt"
        concat_list.write_text("".join(f"file '{path.name}'\n" for path in sorted(work_dir.glob("seg_*.mp4"))), encoding="utf-8")
        rough = work_dir / "rough.mp4"
        run_command([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", "-pix_fmt", "yuv420p", str(rough),
        ], cwd=work_dir)

        cut_path = build_dir / "cut.mp4"
        target_i, target_tp, target_lra = loudness_targets(plan)
        loudness_command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(rough),
            "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "copy",
        ]
        if any(take_audio.values()):
            # Pass one: measure the concatenated rough, so pass two normalises
            # with its statistics rather than guessing them as it goes. A
            # measurement that fails is not worth failing an assembly over --
            # loudnorm_filter falls back to the single pass, and verify.py is
            # still the thing that decides whether the result is good enough.
            try:
                measured = measure_loudness(rough, target_i, target_tp, target_lra)
            except RuntimeError as exc:
                print(f"Loudness measurement failed, normalising in one pass: {exc}")
                measured = None
            loudness_command += [
                "-af", loudnorm_filter(target_i, target_tp, target_lra, measured),
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            ]
        loudness_command += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(cut_path)]
        run_command(loudness_command)
        final_duration = media_duration(cut_path)

        for segment in resolved_segments:
            print(
                f"{resolved_segments.index(segment) + 1:02d}  {str(segment['take']):<4} "
                f"{str(segment.get('beat', '')):<12} {str(segment.get('kind', 'mechanical')):<11} "
                f"{float(segment['start']):6.2f}-{float(segment['end']):6.2f}  "
                f"{float(segment['duration']):6.3f}s  offset {float(segment['offset']):6.3f}s"
            )

        max_words, max_seconds = caption_grouping(
            plan, args.caption_words, args.caption_max_seconds)
        cues, skipped_takes, refusals = build_captions(
            plan, resolved_segments, max_words, max_seconds)
        cues, respelled = respell_from_script(plan, resolved_segments, cues)
        write_captions(build_dir, cues)
        if respelled:
            print(f"Script spelling: {respelled} cue(s) respelled from the script")
        for refusal in refusals:
            # Prefixed, because render_worker.py parses this output and treats a
            # line it does not recognise as blocking. A refused correction is a
            # warning: the reel is fine, one word is spelled the way whisper
            # heard it.
            print(f"Caption correction refused: {refusal}")
        for take_id in skipped_takes:
            print(f"Captions skipped for take {take_id}: no words file")

        resolved_plan = dict(plan)
        resolved_plan["segments"] = resolved_segments
        resolved_plan["planned_duration"] = planned_duration
        resolved_plan["actual_duration"] = round(final_duration, 3)
        write_json(build_dir / "cuts.resolved.json", resolved_plan)

        if not args.no_stage:
            stage_dir = REPO_ROOT / "render" / "public" / "reels" / slug
            stage_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cut_path, stage_dir / "clip.mp4")
            props = {
                "clip": f"reels/{slug}/clip.mp4",
                "headline": str(plan.get("headline", "")),
                "captions": cues,
                "segments": render_segments(resolved_segments),
                "durationInSeconds": round(final_duration, 3),
                "fps": fps,
            }
            # The style travels inside cuts.json, which is the file that already
            # holds every decision about this video -- one file reproduces one
            # reel, and a second one to keep in sync would drift.
            style = plan.get("style")
            if isinstance(style, dict) and style:
                props["style"] = style
                source = style.get("render", {}).get("sourceOrientation")
                if source:
                    props["sourceOrientation"] = source
            props["specHash"] = props_fingerprint(props)
            # Written atomically: a half-written props.json is indistinguishable
            # from a stale one to anything that reads it later.
            temporary = stage_dir / "props.json.tmp"
            write_json(temporary, props)
            os.replace(temporary, stage_dir / "props.json")
            print(f"Staged renderer inputs at {display_path(stage_dir)}")
        else:
            print("Renderer staging skipped (--no-stage)")
        print(f"Wrote {display_path(cut_path)}, captions, and resolved plan ({final_duration:.3f}s)")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: assembly failed: {exc}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
