#!/usr/bin/env python3
"""Regenerate render/src/assets/dmsans.ts from the woff2 in render/public/fonts.

Run this if you swap the typeface. See render/src/fonts.ts for why the font is
inlined rather than fetched.

    python3 scripts/inline_font.py
"""
import base64
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "render/public/fonts/DMSans-Variable.woff2"
OUT = ROOT / "render/src/assets/dmsans.ts"

HEADER = """// DM Sans (variable, latin subset), SIL Open Font License 1.1.
// Licence: render/public/fonts/OFL.txt · source: fonts.google.com/specimen/DM+Sans
//
// Inlined as a data URI on purpose. Served from public/ the font is an HTTP
// request that competes with the OffthreadVideo frame server, and under render
// concurrency that request can hang forever, taking the render with it. A data
// URI cannot be starved: no server, no request, no failure mode.
//
// Regenerate with: python3 scripts/inline_font.py
"""


def main() -> int:
    b64 = base64.b64encode(SRC.read_bytes()).decode()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(f'{HEADER}export const DM_SANS_WOFF2 = "data:font/woff2;base64,{b64}";\n')
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
