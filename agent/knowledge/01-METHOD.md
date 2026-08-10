# METHOD — the run order

Seven stages. Never skip one, never reorder them. Tool commands are in
`03-CUT-CRAFT.md`; the analysis lenses are in `02-YAP-CRAFT.md`.

## 1. INGEST

- Inventory every take with `ffprobe`: duration, resolution, fps, audio codec and channel count, creation order.
- Ask, or infer and flag: the intended **topic or take**, the **format** (standard / walking / car / graphic), the **target platform and length**, and whether takes are alternates of the same content or separate beats.
- Multi-take rule: takes are candidates, not a sequence. The cut may splice across them at beat boundaries.

## 2. TRANSCRIBE

- Word-level timestamps on every take. The timestamps are the cut points; a segment-level transcript is not good enough.
- Store per-take JSON plus a readable transcript. Keep filler words and repeats in the transcript — they are data, not noise. You cannot detect a restart if the restart has been cleaned away.

## 3. ANALYSE FOCUS

- Name the ONE focus: the take, the story, or the epiphany. If two focuses coexist, recommend splitting into two videos.
- Detect the content framework (strong take / take→education / small epiphany / humour / story time) and the script framework if one is present (Hook-Story-P1-P2 / the 8 Mile / the Four Things). See `02-YAP-CRAFT.md`.
- Map beats across **all** takes: hook candidates, story or build, points, conflict, payoff, close.
- Flag tangents (segments not serving the focus), filler runs, restarts and flubs (near-duplicate sentence starts), and dead air.

## 4. RANK

- Score every take, and every beat-candidate within a take, on: hook strength, progression, conflict, payoff speed, delivery flow (filler rate, pace, energy), and technical floor (is the audio usable, is the framing usable).
- Apply the two corpus biases: **the later attempt wins** a retake tie, because the speaker warmed up; and **an intro re-recorded at the end of the session beats the cold open**, almost always.
- Output the ranking table with a one-line reason each. This ships in the report even in fast mode.

## 5. CUT PLAN

Build `cuts.json` (schema: `../../pipeline/CUTS-SCHEMA.md`) in this order:

- **(a) Select the best take per beat.** Structural — carries a reason.
- **(b) Remove flubs, keeping the last attempt.** Mechanical — batch-listed.
- **(c) Silence pass** at thought boundaries (≥0.5s), keeping payoff beats (≤0.4s). Mechanical — batch-listed.
- **(d) Tangent trims.** Structural — each carries a reason tied to the focus.
- **(e) Hook surgery.** The cut opens on the hook wherever it was recorded. Structural.

`plan.py` drafts (b) and (c) for you. It cannot do (a), (d), or (e), and it does not
pretend to.

Sanity-check the planned duration against the target length. If it runs over, cut the
weakest progression segment. Never the conflict.

## 6. EXECUTE

- Frame-accurate segment extraction, concat, and loudness normalisation per `03-CUT-CRAFT.md`. Word-boundary padding on every cut point.
- Generate captions from the kept words, timed to the **cut's** timeline rather than the source's.
- Graphic-yap format only: emit the overlay plan — timestamp plus suggested visual, at roughly a 2s cadence. The agent plans overlays; it does not fabricate the images.

## 7. VERIFY AND DELIVER

- Output duration equals the sum of the keeps within 0.5s.
- Re-transcribe the output and diff it against the planned keep-text: no dropped or doubled words at joins.
- Loudness in range. The file plays.
- Deliver the cut plus the EDIT REPORT (format in `../execution/EXECUTION-PROTOCOL.md`), graded against `../execution/QUALITY-BAR.md`. Fix every fail on a non-negotiable before handoff.

A check that could not run is reported as skipped. It is never reported as passed.
