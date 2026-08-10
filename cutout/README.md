# Greenscreen cutout

This path is Apple-Silicon only and uses `mlx-sam`.

Rules:

- Scrub to a frame where every limb you want is visible. Never seed frame 0. SAM defines the object from the prompt frame, so a hand that enters later is permanently excluded.
- Click every part you want to keep separately, including the torso and each hand. One click segments only one part.
- Shift-click marks a negative point to exclude something.
- Approve the seed preview before tracking. Nothing propagates until the painted frame has been looked at. Propagation is the expensive step and a bad seed wastes all of it.
- Then track. Propagation runs both directions from the seed frame.
- Download `sam2.1-hiera-small-mlx` from Hugging Face into `models/`. `mlx-sam` infers the architecture from the filename, so keep that published name.

Install the optional dependencies from the repository root with the lines in
`pipeline/requirements.txt`. The model checkpoint is intentionally not in git.

## Studio

```bash
python3 cutout/studio.py clip.mp4 --checkpoint models/sam2.1-hiera-small-mlx
```

The studio extracts frames once, lets you scrub and click on one frame, writes
the seed preview before Track starts, and writes 1-indexed masks beside the clip.

## Headless tracking

```bash
python3 cutout/track.py clip.mp4 clip_masks --seed-frame 24 --points 420,260,1 700,480,1 30,30,0
```

The default 512px image size was measured at about 3.3x faster than 1024px at
IoU 0.996 against the 1024px result. The seed mask is cleaned before prompting:
components smaller than 1% of the largest are dropped and counted in the log.

## Composite

```bash
python3 cutout/composite.py clip.mp4 clip_masks -o clip-green.mp4
```

The default background is `#00b140`. Erosion and Gaussian feathering happen
before the original audio is re-muxed. The adjacent-frame QA report is written
next to the output and flags mask-area jumps over 12% for inspection.
