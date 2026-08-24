#!/usr/bin/env python3
"""Does this take have an audio track? Three answers, not two.

    python3 pipeline/probe_audio.py media/<slug>/A.mov
    # exit 0 = has audio, 1 = definitely silent, 2 = could not tell

Everything downstream of a take assumes speech. transcribe.py hands the file to
whisper, which hands it to ffmpeg to extract audio; plan.py's energy pass
measures RMS. On a take with no audio track the first of those dies with two
kilobytes of ffmpeg banner whose actual sentence is the last line, and the
second would die right behind it.

THE THIRD ANSWER IS THE POINT. `common.has_audio` returns a plain bool and
collapses "ffprobe told me nothing" into "no audio", which is the one mistake
that must not be made here: refusing a take because it could not be read is
worse than letting it through to a legible failure. The API's indexer states
the same rule for the same reason -- "a probe that did not run is not evidence
of silence" -- and its `has_audio` column is tri-state to preserve it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ffprobe_json, repo_path  # noqa: E402

VOICED = "voiced"
SILENT = "silent"
UNKNOWN = "unknown"

_EXIT = {VOICED: 0, SILENT: 1, UNKNOWN: 2}


def audio_state(streams: Optional[Sequence[dict]]) -> str:
    """`VOICED`, `SILENT` or `UNKNOWN`, from ffprobe's stream list.

    Mirrors the rule the API's own probe uses -- `any(audio) if streams else
    None` -- so the two cannot disagree about what silence is.
    """
    if not streams:
        return UNKNOWN
    return VOICED if any(s.get("codec_type") == "audio" for s in streams) else SILENT


def exit_code(state: str) -> int:
    """The contract claim.py reads. Only `1` may ever stop a job."""
    return _EXIT.get(state, _EXIT[UNKNOWN])


def probe(path: Path) -> str:
    try:
        data: dict[str, Any] = ffprobe_json(path, "stream=codec_type")
    except Exception:
        # Unreadable, unknown format, ffprobe missing. Not evidence of silence.
        return UNKNOWN
    return audio_state(data.get("streams"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", type=Path)
    args = parser.parse_args()

    state = probe(repo_path(str(args.media)))
    if state == SILENT:
        print(f"{args.media} has no audio track", file=sys.stderr)
    return exit_code(state)


if __name__ == "__main__":
    raise SystemExit(main())
