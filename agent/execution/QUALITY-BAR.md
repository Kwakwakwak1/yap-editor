# QUALITY BAR — the definition of done

Nothing ships until it clears these. Grade each **pass / weak / fail**. Any `fail` on a
**non-negotiable (⛔)** blocks handoff — fix it, then re-grade. A `weak` on a
non-negotiable must be justified in the edit report.

| # | Dimension | Pass looks like | ⛔ |
|---|-----------|-----------------|----|
| 1 | **Focus** | ONE named take, story, or epiphany; every kept segment traceably serves it; tangents cut or split out | ⛔ |
| 2 | **Hook** | The cut opens on the question or the strong take within the first seconds — zero throat-clearing before it | ⛔ |
| 3 | **Retake resolution** | Every flub resolved to its best (usually last) attempt; zero duplicated lines anywhere in the cut | ⛔ |
| 4 | **Dead air** | No silence ≥0.5s at a thought boundary; kept beats before payoffs are deliberate and ≤~0.4s | ⛔ |
| 5 | **Join integrity** | Re-transcription of the output matches the planned keep-text — no clipped words, no doubles; audio and video in sync | ⛔ |
| 6 | **Progression** | Each beat moves toward the payoff; no flat stretch long enough to sag (a pattern break placed if a long middle is unavoidable) | — |
| 7 | **Conflict & payoff** | Story cuts keep their friction; the payoff answers the hook's promise, fast, near the end | — |
| 8 | **Audio** | Loudness −14 LUFS ±1, true peak ≤ −1.5dB, no clipping, correct mic channel | — |
| 9 | **Length & format fit** | Duration matches the framework (story ≲60s; take→education ≤2–3 min only if progression holds); decoration matches the declared format | — |
| 10 | **Deliverable completeness** | A playable file, plus `cuts.json`, `captions.srt`, and an edit report with the take ranking and every structural cut reasoned | — |

## Mode interaction

- **⚡ CUT** — ⛔ dimensions enforced in full; 6–9 may land `weak` if flagged in the report.
- **💎 DIRECTOR** — everything enforced; `weak` on any dimension blocks. Adds the overlay plan, pattern-break placement, and reshoot notes.

## Grading procedure

1. Grade all ten with **one line of evidence each** — timestamps, numbers, diff results. Not adjectives.
2. Fix every ⛔ `fail` before handoff. There is no "noted for later" on a non-negotiable.
3. Ship the graded bar inside the edit report.

## What the machine can grade for you

`pipeline/verify.py` produces hard evidence for dimensions 4, 5, and 8, and half of 1
(planned versus actual duration). It cannot grade focus, hook, progression, or conflict —
those are the judgement half, and a report that grades them without a human or an agent
having actually watched the cut is a fabricated grade.
