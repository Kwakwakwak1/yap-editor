#!/usr/bin/env python3
"""Promote a render only after an explicit approval decision exists."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict


def approvals_map(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict) and isinstance(value.get("approvals"), dict):
        return value["approvals"]
    if isinstance(value, dict):
        return value
    return {}


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("render", type=Path)
    parser.add_argument("--to", type=Path, default=Path("out/final"))
    parser.add_argument("--approvals", type=Path, default=Path("review/approvals.json"))
    args = parser.parse_args()
    render = args.render.resolve()
    if not render.exists():
        print(f"REFUSED: render does not exist: {args.render}", file=sys.stderr)
        return 1
    if not args.approvals.exists():
        print(f"REFUSED: approvals file is missing: {args.approvals}. Collect the review page decisions first.", file=sys.stderr)
        return 1
    try:
        approvals = approvals_map(args.approvals)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REFUSED: approvals file is unreadable: {exc}", file=sys.stderr)
        return 1
    decision = approvals.get(render.name)
    if not isinstance(decision, dict) or decision.get("status") != "approved":
        status = decision.get("status") if isinstance(decision, dict) else "not present"
        print(f"REFUSED: {render.name} is {status}, not approved. Nothing was promoted.", file=sys.stderr)
        return 1
    destination_dir = args.to.resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / render.name
    shutil.copy2(render, destination)
    print(f"Approved render promoted to {display_path(destination)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
