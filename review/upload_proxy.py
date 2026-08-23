#!/usr/bin/env python3
"""Put one proxy on R2 and print where it landed.

    python3 review/upload_proxy.py build/<slug>/A.proxy.mp4 --key proxies/<slug>/A.mp4

Separate from publish.py because that script's job is the approval page -- it
rewrites an index of every reel awaiting a decision. A proxy is not something
anyone approves.

It lives in review/ rather than pipeline/ for one specific reason: uploading
needs boto3, and pipeline/ is imported by a test suite that runs on minik's
system interpreter, which does not have it. publish.py already imports boto3
lazily here, and this borrows its settings rather than adding a third reader of
the same .env file.

ON STDOUT: the URL, alone. claim.py reads it to learn what to store on the job,
so anything else printed here becomes part of a URL in the database.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish import config, content_type  # noqa: E402


def public_url(base: str, prefix: str, key: str) -> str:
    """Where the object will actually be readable.

    The prefix is included. publish.py composes its own URL ignoring
    `S3_KEY_PREFIX`, which is why the skill carries a warning that setting that
    variable makes the printed link 404. This function does not have that bug,
    and the tests pin it.
    """
    parts = [base.rstrip("/")]
    if prefix.strip("/"):
        parts.append(prefix.strip("/"))
    parts.append(key.lstrip("/"))
    return "/".join(parts)


def upload(
    path: Path,
    key: str,
    settings: Dict[str, str],
    client: Optional[Any] = None,
) -> str:
    """Upload one file to one key. Returns its public URL."""
    if client is None:
        try:
            boto3 = __import__("boto3")
        except ImportError:
            raise RuntimeError(
                "uploading needs boto3 - run this with .venv/bin/python"
            ) from None
        client = boto3.client(
            "s3",
            endpoint_url=settings.get("S3_ENDPOINT_URL") or None,
            region_name=settings.get("S3_REGION") or "auto",
            aws_access_key_id=settings.get("S3_ACCESS_KEY_ID"),
            aws_secret_access_key=settings.get("S3_SECRET_ACCESS_KEY"),
        )
    prefix = settings.get("S3_KEY_PREFIX", "").strip("/")
    object_key = f"{prefix}/{key}" if prefix else key
    # ContentType matters: without it the browser is handed
    # application/octet-stream and downloads the proxy instead of playing it.
    client.upload_file(
        str(path), settings["S3_BUCKET"], object_key,
        ExtraArgs={"ContentType": content_type(path)},
    )
    return public_url(settings["PUBLIC_BASE_URL"], prefix, key)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()

    if not args.path.exists():
        print(f"ERROR: no such file: {args.path}", file=sys.stderr)
        return 1
    try:
        url = upload(args.path, args.key, config())
    except Exception as exc:
        print(f"ERROR: upload failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
