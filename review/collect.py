#!/usr/bin/env python3
"""Merge copied browser decisions into a durable approvals file."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_input(args: argparse.Namespace) -> Dict[str, Any]:
    if args.from_clipboard:
        try:
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(f"could not read macOS clipboard: {exc}") from exc
        raw = result.stdout
    else:
        raw = args.file.read_text(encoding="utf-8")
    value = json.loads(raw)
    if isinstance(value, dict) and isinstance(value.get("decisions"), dict):
        return value["decisions"]
    if not isinstance(value, dict):
        raise RuntimeError("decisions must be a JSON object keyed by render filename")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-clipboard", action="store_true")
    source.add_argument("--file", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        incoming = read_input(args)
        approvals: Dict[str, Any] = {}
        if args.output.exists():
            existing = json.loads(args.output.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                approvals = existing.get("approvals", existing)
        for filename, decision in incoming.items():
            if not isinstance(decision, dict) or decision.get("status") not in {"approved", "denied"}:
                print(f"Skipping {filename}: status must be approved or denied", file=sys.stderr)
                continue
            approvals[str(filename)] = {
                "status": decision["status"],
                "note": str(decision.get("note", "")),
                "decided_at": str(decision.get("decided_at") or now()),
            }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(approvals, indent=2) + "\n", encoding="utf-8")
        print(f"Merged {len(incoming)} decision(s) into {args.output}")
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
