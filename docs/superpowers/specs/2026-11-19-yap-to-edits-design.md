# Yap → Edits: the approved cut, editable in Instagram Edits

**Date:** 2026-11-19
**Status:** Draft, for review
**Scope:** Let an approved yap cut plan drive an Instagram Edits for Mac project,
one clip per beat, so Kris can see and adjust the edit, then post from Edits or
have it scheduled through the studio. The studio's Remotion path is unchanged.

## Why

yap-editor already makes the editorial decisions that matter: word-level
transcripts, silence and filler cuts, last-attempt-wins retakes, the hook at
0:00, the HOYOS beat spine, -14 LUFS, orientation-aware framing, and a hard
approval gate. Its output is rendered by Remotion and approved on the phone,
which Kris can't adjust.

Edits for Mac (driven through the `insta-edits` MCP bridge) is where Kris can
see an edit, change it, add music and post. But an edit built there by hand
skipped all of yap's rules. The 2026-11-18 beard-vow trials kept every silence,
had no hook moved up, and letterboxed a 16:9 take without yap's framing.

This joins the two: yap decides, Edits finishes.

## The flow

1. **Upload** (unchanged): phone Shortcut → R2 `inbox/` → `r2-drain` → T9
   `dropbox/` → indexer → studio library. (2026-11-19: kwakmini64's launchd
   interval timers had stopped since about 2026-09-10; the jobs now use
   `StartCalendarInterval`.)
2. **Prep** (unchanged, minik): `transcribe.py` → `plan.py --energy` gives a
   draft `cuts.json`.
3. **Editorial pass and approval gate** (unchanged rules, `agent/AGENT.md`):
   hook selection, beat order, length, story rules. Nothing is cut until Kris
   answers.
4. **Cut for Edits** (new, minik): `pipeline/edits_export.py`.
5. **Build in Edits** (new, this Mac): the `yap-to-edits` skill, driving the
   Edits MCP tools.
6. **Finish:** Kris posts from Edits, or asks for an export, which is verified
   and scheduled through the studio under the existing rules (trials post on
   their own; follower posts wait for approval).
7. **Learn** (later, the analytics project): each post records its hook text
   and `built_by: "yap→edits"`.

## Part 1: `pipeline/edits_export.py`

```
python pipeline/edits_export.py build/<slug>/cuts.json [--out build/<slug>/edits]
```

Input is an approved `cuts.json` (CUTS-SCHEMA v1 or v2). Output is one folder:

```
build/<slug>/edits/
  01-hook.mov  02-build.mov  …  NN-<beat>.mov
  plan.json
```

### Clips

| Decision | Choice | Why |
|---|---|---|
| Container and codec | ProRes 422 HQ `.mov`, 30 fps (the plan's `fps`), PCM 48 kHz audio | Edits imports and scrubs ProRes without re-decoding |
| Cut points | Frame-accurate re-encode at `start - pad[0]` … `end + pad[1]`, clamped to the take, with the plan's `pad` (default 0.07/0.07) | The same boundaries `assemble.py` uses, so a clip is exactly the beat yap meant |
| File name | `NN-<beat>.mov`: NN is the 1-based position in `segments` (two digits), and the beat is slugged to `[a-z0-9-]`, falling back to `segment` | Sorts in cut order in Finder and Edits; segments are never re-sorted |
| HDR sources (iPhone HLG/PQ) | Tone-mapped to BT.709 SDR (`zscale` + `tonemap=hable`, then `format=yuv422p10le`) | Edits projects here are SDR. Untreated HDR looks washed out or blown out |
| Rotation | Read the display rotation the same way `render_worker`'s probe does, never raw width and height | Phones store portrait as rotated landscape |
| 9:16 source | 1080×1920 | Matches `PortraitFull` |
| 16:9 source | 1920×1080, kept landscape | The builder fits it to width on black in Edits, as `LandscapeOnBlack` does, but it stays reframable |
| Mixed takes | Each segment is cut from its own take; the orientation is per take | `takes` is a map, and a segment can come from any take |
| Loudness | One shared gain for every clip. The loudness of all kept segments concatenated is measured with `loudnorm` (first pass), and the linear gain is applied with a true-peak limiter at the plan's `tp` | Normalising each clip separately would make beats jump in level against each other |

### `plan.json`

```json
{
  "version": 1,
  "slug": "20261119-kwakwakwak-xxxx",
  "headline": "…",
  "fps": 30,
  "orientation": "portrait" ,
  "loudness": {"target_i": -14, "measured_i": -19.3, "gain_db": 5.3},
  "clips": [
    {"file": "01-hook.mov", "beat": "hook", "kind": "structural", "reason": "…",
     "take": "B", "source_start": 2.10, "source_end": 6.60,
     "clip_start": 2.03, "clip_end": 6.67, "duration": 4.64,
     "orientation": "portrait",
     "words": [{"from": 0.07, "to": 0.31, "text": "Why"}, …]}
  ]
}
```

- `words` holds that clip's words from the take's `words.json`, with any
  `caption_corrections` and script respellings applied (the same functions
  `assemble.py` uses), shifted so 0 is the clip's first frame.
- `duration` is the clip file's measured duration.
- Top-level `orientation` is `portrait`, `landscape` or `mixed`.

### Failures

- An invalid plan (`validate_plan` from `assemble.py`) exits non-zero with no
  partial folder: writes go to a temp directory, which is renamed into place.
- A missing take file, or an ffmpeg failure: same.
- A clip whose measured duration differs from its expected duration by more
  than one frame is a hard failure.

## Part 2: the `yap-to-edits` skill (this Mac)

It lives with the other skills (dotfiles `claude/skills/yap-to-edits/`), with a
helper `scripts/edits_plan.py`. It runs only when Kris asks, because Edits has
to be open.

### Steps

1. **Fetch:** copy `/Volumes/MiniKWork/yap-editor/build/<slug>/edits/` to
   `~/Movies/yap/<slug>/`, which is the only folder Edits may read.
   `edits_plan.py check` confirms every clip in `plan.json` exists with its
   duration within one frame.
2. **Preflight:** `appState` is reachable. If Edits is closed or the automation
   server is off, stop and say so.
3. **Project:** `newProject` named `yap · <headline>`;
   `setProjectDynamicRange SDR`; 9:16; black background.
4. **Clips:** add each clip in `plan.json` order to the main track. Read
   `elements` back: the order and each duration must match the plan within one
   frame, or stop.
5. **Framing:** portrait clips fill the canvas. For landscape clips, read
   `getTransform` and scale to fit the width, centred. `captureFrame` at every
   clip boundary.
6. **Captions:**
   - `generateCaptions`, then read `captions`.
   - `edits_plan.py align` lines Edits' words up against `plan.json` words
     (sequence alignment on normalised tokens, by clip) and returns the edits
     to make.
   - Apply them with `editCaption`.
   - A region where alignment confidence is below the threshold is left
     alone and reported with its time.
   - Style: one caption preset (default `Word Highlight Box`), with the
     highlight in the brand accent from `brand.json`.
7. **Decoration:** none for standard, walking or car yaps. Graphic yaps get the
   overlays `overlays.json` suggests (yap's rule).
8. **Checks:** frame 0 is the hook and reads as a cover. `captureFrame` at every
   cut. `previewVideo` plays through.
9. **Report:** each beat's length and reason, the total, and anything flagged.
   The project is left open.

### Export and scheduling (only when asked)

- `setExportSettings` (HD, `nineBySixteen`, 30, high, SDR) immediately before
  `export` to `~/Movies/yap/<slug>/<slug>.mp4`. Poll `exportStatus`.
- Verify: integrated loudness -14 ±1 LUFS, true peak ≤ -1.0 dB, duration equal to
  the timeline within 0.1 s, 1080×1920.
- Upload and schedule through the studio as today: `POST /media`, then a batch.
  Trials use `trial_params` and post on their own; follower posts wait for
  Kris's approval. The batch title carries the slug, and the post records the
  hook text and `built_by: "yap→edits"` for the analytics project.
- If Kris changed the project by hand, the export includes the changes. The
  builder never rebuilds over a project Kris has touched.

## What stays the same

- The approval gate, `cuts.json`, and the studio's Remotion render and phone
  approval path. Both paths start from the same approved plan.
- `kwakfit-reel-edit` stays the skill for workout footage. It can adopt
  `plan.json` later.

## Testing

**`edits_export.py`** (pytest, the repo's existing style, with tiny generated
test media like the current tests):
- clip count, order and file names follow `segments`, which are never sorted;
- each clip's duration equals segment plus padding, within one frame, and
  padding is clamped at the take's edges;
- `words` are the right subset, shifted to clip time, with corrections applied;
- the gain is the same for every clip, and a quiet and a loud segment keep
  their difference;
- a landscape and a portrait take in one plan give per-clip orientation and
  `mixed`;
- an HDR test source comes out BT.709 (checked with ffprobe's `color_transfer`);
- an invalid plan leaves no output folder.

**`edits_plan.py`**: `check` (missing file, wrong duration); `align` (exact
match, a misheard name, a dropped word, an inserted word, a region too
different to correct, which is reported and not changed).

**End to end on Kris's 2026-11-19 take**
(`dropbox/2026-11-19-015108-b43073695b7b-take.mov`): run the yap pipeline,
approval, export and build. Check frames at every cut, spot-check captions, and
verify the exported file's loudness and duration.

## Out of scope

- Music selection (Kris's call in Edits; the Edits notes cover loudness when it
  is added).
- Driving Edits' own split, trim or reorder tools: undocumented, and slower
  than importing clean clips once.
- Unattended runs: Edits needs to be open.
- The analytics loop (separate project), which only reads the recorded fields.
