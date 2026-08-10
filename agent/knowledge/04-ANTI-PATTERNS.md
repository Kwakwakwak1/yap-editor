# ANTI-PATTERNS — how these edits go wrong

Each one is a real failure mode. The replacement guidance is the rule.

1. **Machine-stripping every pause.** Blind 0.5s removal flattens rhythm and kills the tension beat before a payoff — the uncertain-answer moment needs air. → Run the mechanical pass first, then re-check every cut adjacent to a payoff or a punchline and restore up to 0.4s where the beat is load-bearing.

2. **Keeping the cold open.** The first take's intro is the most awkward moment of the session. → Always check the session's *last* takes for an intro re-record. It almost always wins.

3. **Opening on wind-up.** "Hey guys, so today…" is throat-clearing. → The cut opens on the question or the strong take, even if that was recorded at minute three.

4. **Cutting the conflict to hit a length target.** Trimming the struggle because it "delays the answer" turns a story into a report. → Cut flat progression. Never conflict.

5. **Polishing production instead of shipping.** Colour-grading debates, set upgrades, gear spirals. The format's entire premise is ease. → Silence, flubs, structure, loudness, captions. Ship. Everything else is optional and second.

6. **Decorating a format that didn't ask.** Bolting graphics onto a standard yap, or stacking every device at once. → The format declared at intake decides the decoration budget. One or two devices, maximum.

7. **Ranking takes by cleanliness.** Picking the flub-free flat take over the lit-up take with two restarts. → Flubs are cuttable; flatness is not. Rank flow first, then subtract fixable defects.

8. **`-c copy` cutting.** Stream-copy cuts snap to keyframes and drift off word boundaries, so joins clip words. → Re-encode every segment, then verify by re-transcribing the output.

9. **Editing a generic script well.** A flawless cut of "my top three productivity tips" is still dead. → Say so in the report *before* cutting, and recommend the reshoot angle instead of burning effort on a corpse.

10. **Splitting focus.** Two takes braided into one video because both were "too good to cut". → One video, one focus. Recommend two; deliver the primary.

## Three more that are specific to this pipeline

11. **Trusting in-script metrics instead of output frames.** A render that reports the right numbers and looks wrong is the normal failure, not the exotic one — the numbers describe what the script *intended*, and the bug is usually between the intent and FFmpeg. → Measure the finished file. Extract frames and look at them.

12. **Concatenating segments with mismatched parameters.** Different fps, resolution, or pixel format across takes produces a concat that succeeds, prints nothing alarming, and yields a file that is three seconds long or plays only the first segment. → Normalise at extraction. `assemble.py` does; if you hand-roll a cut, you must too.

13. **Seeding a cutout on frame 0.** SAM defines the object from the prompt frame, so a hand that enters at 0:04 is permanently excluded. → Seed on the frame where every limb you want is visible, click every part separately, and propagate in both directions. `cutout/README.md` has the full rule.
