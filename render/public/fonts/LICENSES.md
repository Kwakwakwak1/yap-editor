# Bundled typefaces

Every face here is licensed under the SIL Open Font License 1.1. The licence
text is in `OFL.txt` and applies to all of them; the copyright holders differ
and are listed below.

These files are inlined into the render bundle as data URIs (see
`render/src/fonts/registry.ts` for why), so the licence travels with the source
rather than with a served file.

| key | family | copyright | source |
|---|---|---|---|
| `dm-sans` | DM Sans | Colophon Foundry, Jonny Pinhorn | fonts.google.com/specimen/DM+Sans |
| `archivo` | Archivo | Omnibus-Type | fonts.google.com/specimen/Archivo |
| `instrument-serif` | Instrument Serif | Instrument | fonts.google.com/specimen/Instrument+Serif |
| `inter` | Inter | Rasmus Andersson | fonts.google.com/specimen/Inter |
| `space-grotesk` | Space Grotesk | Florian Karsten | fonts.google.com/specimen/Space+Grotesk |
| `caveat` | Caveat | Impallari Type | fonts.google.com/specimen/Caveat |

Regenerate the inlined modules with `python3 scripts/inline_fonts.py`.
