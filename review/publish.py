#!/usr/bin/env python3
"""Publish a static review build to S3-compatible storage."""

from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional


CONFIG_NAMES = (
    "S3_ENDPOINT_URL", "S3_BUCKET", "S3_REGION", "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY", "PUBLIC_BASE_URL", "S3_KEY_PREFIX",
)


def read_dotenv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key in CONFIG_NAMES:
            values[key] = value.strip('"\'')
    return values


def config() -> Dict[str, str]:
    local = read_dotenv(Path(".env"))
    return {name: os.environ.get(name, local.get(name, "")) for name in CONFIG_NAMES}


def content_type(path: Path) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".mp4": "video/mp4",
        ".srt": "application/x-subrip",
    }.get(path.suffix.lower(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")


def files_to_upload(build: Path, requested: List[Path], all_files: bool) -> List[Path]:
    if all_files:
        return sorted(path for path in build.rglob("*") if path.is_file())
    if requested:
        return [path.resolve() for path in requested]
    defaults = [build / "index.html", build / "manifest.json"]
    return [path for path in defaults if path.exists()]


def object_key(build: Path, path: Path, prefix: str) -> str:
    try:
        relative = path.resolve().relative_to(build.resolve()).as_posix()
    except ValueError:
        relative = f"media/{path.name}"
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{relative}" if clean_prefix else relative


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--file", action="append", type=Path, default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--build", type=Path, default=Path("review/build"))
    args = parser.parse_args()
    build = args.build.resolve()
    files = files_to_upload(build, args.file, args.all)
    if not files:
        print("ERROR: no review files to upload", file=sys.stderr)
        return 1
    settings = config()
    missing = [name for name in ("S3_BUCKET", "S3_REGION", "PUBLIC_BASE_URL") if not settings[name]]
    if not args.dry_run:
        missing += [name for name in ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY") if not settings[name]]
    if missing:
        print(f"ERROR: missing configuration: {', '.join(missing)}. Set them in the environment or local .env", file=sys.stderr)
        return 1
    for path in files:
        if not path.exists() or not path.is_file():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            return 1
    plans = [(path, object_key(build, path, settings["S3_KEY_PREFIX"])) for path in files]
    if args.dry_run:
        print("Dry run. Nothing uploaded.")
        for path, key in plans:
            print(f"  {path.name} -> {key} ({content_type(path)})")
        if settings["PUBLIC_BASE_URL"]:
            print(f"Final public URL: {settings['PUBLIC_BASE_URL'].rstrip('/')}/index.html")
        else:
            print("Final public URL unavailable until PUBLIC_BASE_URL is set")
        return 0
    try:
        boto3 = __import__("boto3")
    except ImportError:
        print("ERROR: publishing needs boto3. Install it with: pip install boto3", file=sys.stderr)
        return 2
    client = boto3.client(
        "s3",
        endpoint_url=settings["S3_ENDPOINT_URL"] or None,
        region_name=settings["S3_REGION"],
        aws_access_key_id=settings["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=settings["S3_SECRET_ACCESS_KEY"],
    )
    try:
        for path, key in plans:
            client.upload_file(str(path), settings["S3_BUCKET"], key, ExtraArgs={"ContentType": content_type(path)})
            print(f"Uploaded {path.name} as {key}")
    except Exception as exc:
        print(f"ERROR: upload failed: {exc}", file=sys.stderr)
        return 1
    print(f"Final public URL: {settings['PUBLIC_BASE_URL'].rstrip('/')}/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
