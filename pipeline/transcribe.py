#!/usr/bin/env python3
"""Transcribe a media file into the repository's word-timestamp JSON shape."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from common import media_duration, repo_path, safe_record_path, write_json


INSTALL_LINES = {
    "mlx": "pip install mlx-whisper",
    "faster": "pip install faster-whisper",
    "openai": "pip install openai-whisper",
}
BACKEND_ORDER = ("mlx", "faster", "openai")


def _word(start: Any, end: Any, value: Any) -> Optional[Dict[str, Any]]:
    try:
        start_number = round(float(start), 3)
        end_number = round(float(end), 3)
    except (TypeError, ValueError):
        return None
    text = str(value).strip()
    if not text or end_number <= start_number:
        return None
    return {"start": start_number, "end": end_number, "word": text}


def _from_mlx(media: Path, model: str) -> Tuple[str, str, List[Dict[str, Any]], str]:
    module = importlib.import_module("mlx_whisper")
    result = module.transcribe(
        str(media),
        path_or_hf_repo=model,
        word_timestamps=True,
        verbose=False,
    )
    language = str(result.get("language", "en"))
    words: List[Dict[str, Any]] = []
    for segment in result.get("segments", []):
        for item in segment.get("words", []) or []:
            parsed = _word(item.get("start"), item.get("end"), item.get("word"))
            if parsed:
                words.append(parsed)
    return "mlx", model, words, language


def _from_faster(media: Path, model: str) -> Tuple[str, str, List[Dict[str, Any]], str]:
    module = importlib.import_module("faster_whisper")
    whisper_model = module.WhisperModel(model, device="auto", compute_type="int8")
    segments, info = whisper_model.transcribe(str(media), word_timestamps=True)
    words: List[Dict[str, Any]] = []
    for segment in segments:
        for item in getattr(segment, "words", None) or []:
            parsed = _word(getattr(item, "start", None), getattr(item, "end", None), getattr(item, "word", ""))
            if parsed:
                words.append(parsed)
    language = str(getattr(info, "language", "en"))
    return "faster", model, words, language


def _from_openai(media: Path, model: str) -> Tuple[str, str, List[Dict[str, Any]], str]:
    module = importlib.import_module("whisper")
    whisper_model = module.load_model(model)
    result = whisper_model.transcribe(str(media), word_timestamps=True)
    words: List[Dict[str, Any]] = []
    for segment in result.get("segments", []):
        for item in segment.get("words", []) or []:
            parsed = _word(item.get("start"), item.get("end"), item.get("word"))
            if parsed:
                words.append(parsed)
    language = str(result.get("language", "en"))
    return "openai", model, words, language


BACKEND_LOADERS = {
    "mlx": _from_mlx,
    "faster": _from_faster,
    "openai": _from_openai,
}


def transcribe(media: Path, backend: str, model: str) -> Tuple[str, str, List[Dict[str, Any]], str]:
    candidates = BACKEND_ORDER if backend == "auto" else (backend,)
    missing: List[str] = []
    for candidate in candidates:
        try:
            return BACKEND_LOADERS[candidate](media, model)
        except ImportError:
            missing.append(candidate)
        except Exception as exc:  # optional backends should never leak a traceback
            raise RuntimeError(f"{candidate} transcription failed: {exc}") from None
    install = "\n".join(f"  {INSTALL_LINES[name]}" for name in BACKEND_ORDER)
    raise ImportError(f"No transcription backend is installed. Install one of:\n{install}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--backend", choices=("auto", "mlx", "faster", "openai"),
                        default=os.environ.get("TRANSCRIBE_BACKEND", "auto"))
    parser.add_argument("--model", default=os.environ.get("TRANSCRIBE_MODEL", "large-v3-turbo"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    media = repo_path(str(args.media))
    if not media.exists():
        print(f"ERROR: media file not found: {args.media}", file=sys.stderr)
        return 1
    output = args.output or media.with_suffix(".words.json")
    output = repo_path(str(output))
    try:
        backend, model, words, language = transcribe(media, args.backend, args.model)
        duration = round(media_duration(media), 3)
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    text = " ".join(item["word"] for item in words)
    payload = {
        "version": 1,
        "source": safe_record_path(media),
        "backend": backend,
        "model": model,
        "language": language,
        "duration": duration,
        "text": text,
        "words": words,
    }
    write_json(output, payload)
    print(f"Transcribed {safe_record_path(media)} with {backend} ({model})")
    print(f"Wrote {safe_record_path(output)}: {len(words)} word timestamps, {duration:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
