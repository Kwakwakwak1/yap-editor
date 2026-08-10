# PRINCIPLES — the editor's priors

Ten operating laws. ⚑ marks consensus across two or more sources. Tags: OREN · SARAEV ·
HOYOS · VINH · JAKE — see `../../CREDITS.md` for who they are.

1. **⚑ The edit removes resistance, it doesn't add polish.** The finished cut should feel like the speaker's thoughts arriving with zero friction. Silences, flubs, and restarts are resistance; cut them. Decoration is not the job. (OREN recut method · SARAEV VAD pass · JAKE flow)

2. **⚑ One focus per yap.** A yap is one take, one story, or one epiphany. Every kept second serves it; tangents are cut, or the footage becomes two videos. (OREN "what is my take?" · HOYOS one question, one answer)

3. **⚑ The first seconds are the video.** The cut opens on the question or the strong take — never on throat-clearing, wind-up, or "hey guys". If the hook is buried at 0:47 of take two, the edit moves it to 0:00. (HOYOS · OREN)

4. **⚑ Progression is retention.** Every beat must move the viewer measurably closer to the payoff. Where progression flattens, cut the flat part or insert the pattern break — never let smooth sailing run long. (HOYOS · OREN · VINH)

5. **Conflict before the answer.** A story without friction is a report. Keep — do not cut — the moments of struggle, doubt, and interference. They are what make the payoff land. (HOYOS)

6. **⚑ Pay off fast, then stop.** The answer arrives quickly and concisely; nothing after the payoff but at most one close. If it takes longer to tell than to do, it's overcooked. (HOYOS · OREN)

7. **⚑ Rank takes by flow, not cleanliness.** The take where the speaker is lit up and unresisting beats the technically cleaner stiff one — energy transmits through the phone. Later takes usually win, because the speaker warmed up, and intro re-records made at the end of a session almost always win. (JAKE · OREN)

8. **The pause is cut at thought boundaries and kept before payoffs.** Mechanical default: silence of 0.5s or more goes. Structural override: the beat before a reveal or a punchline stays, capped at about 0.4s. (SARAEV vs HOYOS — resolved this way)

9. **⚑ Format decides decoration.** Standard, walking, and car yaps need captions and nothing else. A graphic yap gets one visual roughly every 2 seconds, planned, vertical. Never bolt devices onto a format that didn't ask for them; one or two devices, not a clown show. (OREN · VINH)

10. **⚑ Automate the mechanical, judge the creative.** Silence detection, transcription, cutting, and loudness are scripted and deterministic. Focus analysis, take ranking, and structural cuts are judgement, and they get shown to the user with reasons. (SARAEV · OREN)

## Where the split falls

Principle 10 is the reason this repo is shaped the way it is. Everything left of
`cuts.json` is judgement and belongs to a person or an agent. Everything right of it is
FFmpeg, and belongs to a script that behaves identically every time. When you find
yourself putting taste into a script, or arithmetic into a prompt, you've crossed the
line in the wrong direction.
