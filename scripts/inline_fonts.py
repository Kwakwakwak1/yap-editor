#!/usr/bin/env python3
"""Regenerate render/src/assets/<family>.ts from the woff2 files in
render/public/fonts.

Run this when a typeface is added or swapped. See render/src/fonts/registry.ts
for why the fonts are inlined rather than fetched -- three attempts at loading
them any other way each killed a cold render.

    python3 scripts/inline_fonts.py            # regenerate every module
    python3 scripts/inline_fonts.py --check    # fail if the bundle is too big

Needs fonttools only for --subset, which is optional: the files Google Fonts
serves are already latin-subset, so subsetting them again saves very little.
"""
from __future__ import annotations

import argparse
import base64
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "render/public/fonts"
OUT_DIR = ROOT / "render/src/assets"

# The whole roster. A style pack names a font by KEY, and the API rejects a key
# that is not here at save time -- so this list is the real ceiling on how far a
# data-only catalog can grow, and adding to it is a deliberate act with a
# measurable cost.
FAMILIES = {
    "dm-sans": ("DMSans-Variable.woff2", "dmsans.ts", "DM_SANS_WOFF2"),
    "archivo": ("Archivo-Variable.woff2", "archivo.ts", "ARCHIVO_WOFF2"),
    "instrument-serif": (
        "InstrumentSerif-Regular.woff2", "instrumentserif.ts", "INSTRUMENT_SERIF_WOFF2",
    ),
    "inter": ("Inter-Variable.woff2", "inter.ts", "INTER_WOFF2"),
    "space-grotesk": ("SpaceGrotesk-Variable.woff2", "spacegrotesk.ts", "SPACE_GROTESK_WOFF2"),
    "caveat": ("Caveat-Variable.woff2", "caveat.ts", "CAVEAT_WOFF2"),
}

# Base64 inflates by about a third, and every byte ships in the render bundle.
# The limit is not arbitrary: it is what keeps "add a style" from quietly
# meaning "add a megabyte", and CI fails rather than letting it drift.
BUDGET_BYTES = 2 * 1024 * 1024

HEADER = """// {family}, SIL Open Font License 1.1.
// Licence text: render/public/fonts/OFL.txt · see LICENSES.md for holders.
//
// Inlined as a data URI on purpose. Served from public/ the font is an HTTP
// request that competes with the OffthreadVideo frame server, and under render
// concurrency that request can hang forever, taking the render with it. A data
// URI cannot be starved: no server, no request, no failure mode.
//
// Generated -- do not edit. Regenerate with: python3 scripts/inline_fonts.py
"""


def generate() -> int:
    total = 0
    for key, (source, module, symbol) in FAMILIES.items():
        path = FONT_DIR / source
        if not path.exists():
            print(f"MISSING {source} -- {key} will fall back to a system stack",
                  file=sys.stderr)
            continue
        encoded = base64.b64encode(path.read_bytes()).decode()
        body = (
            HEADER.format(family=key)
            + f'\nexport const {symbol} =\n  "data:font/woff2;base64,{encoded}";\n'
        )
        (OUT_DIR / module).write_text(body, encoding="utf-8")
        total += len(body)
        print(f"{key:<18} {path.stat().st_size / 1024:7.1f} KB -> {module}")
    print(f"\nbundle total: {total / 1024:.1f} KB of {BUDGET_BYTES / 1024:.0f} KB budget")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if the generated modules exceed the budget")
    args = parser.parse_args()

    if args.check:
        total = sum(p.stat().st_size for p in OUT_DIR.glob("*.ts"))
        print(f"font modules: {total / 1024:.1f} KB of {BUDGET_BYTES / 1024:.0f} KB")
        if total > BUDGET_BYTES:
            print("OVER BUDGET -- every byte ships in the render bundle",
                  file=sys.stderr)
            return 1
        return 0

    generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
