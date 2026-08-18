#!/usr/bin/env python3
"""Compile a style pack's `grade` block into an ffmpeg filter chain.

Grade runs in ffmpeg, not in the renderer, and that is a deliberate choice with
two reasons behind it.

assemble.py already re-encodes every segment, so adding filters to that pass is
free. The alternative -- a CSS `filter` on the video element in Remotion --
would run per frame in headless Chrome on a 1080x1920 surface, adding real time
to a render that already takes four minutes.

And the preview is `cut.mp4`, produced by that same pass. Grading there means
the preview shows the grade, which is the entire point of previewing a style
before approving it.

SECURITY: the accepted keys are a closed whitelist and every value is clamped to
a range. This output is handed to a subprocess, so a raw filter string from a
pack would be a filtergraph injection. The schema rejects unknown keys at save
time; this clamps whatever survives that.
"""

from __future__ import annotations

from typing import Any, Dict, List

# key -> (minimum, maximum, neutral). Neutral is what "this does nothing" means
# for that key, and a value at neutral emits no filter at all -- so a style that
# only sharpens does not pay for a colour pass it did not ask for.
LIMITS: Dict[str, tuple] = {
    "exposure": (-1.0, 1.0, 0.0),
    "contrast": (0.5, 2.0, 1.0),
    "saturation": (0.0, 3.0, 1.0),
    "temperature": (-100.0, 100.0, 0.0),
    "tint": (-100.0, 100.0, 0.0),
    "vignette": (0.0, 1.0, 0.0),
    "sharpen": (0.0, 2.0, 0.0),
    "grain": (0.0, 1.0, 0.0),
}

TRIPLET_LIMITS = (-1.0, 2.0)


def clamp(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number:  # NaN
        return fallback
    return max(low, min(high, number))


def _triplet(value: Any, neutral: float) -> List[float]:
    """Three channel values, or the neutral triplet when absent or malformed.

    `neutral` differs by key and getting it wrong is not subtle: lift is neutral
    at 0 (no shadow shift) while gain is neutral at 1 (a multiplier). Defaulting
    gain to zeros emits rh=-1.0 on every channel, which crushes the highlights
    of any pack that simply did not mention gain.
    """
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return [neutral, neutral, neutral]
    return [clamp(item, *TRIPLET_LIMITS, neutral) for item in value]


def _near(value: float, neutral: float) -> bool:
    return abs(value - neutral) < 1e-6


def build_filters(grade: Dict[str, Any] | None) -> List[str]:
    """The filter list for this grade, in the order ffmpeg should apply it.

    Order matters and is not alphabetical: colour balance shapes the image
    before `eq` stretches it, sharpening reads a graded image rather than a raw
    one, and grain goes last so it is not itself sharpened -- sharpening noise
    is how a grade starts to look like compression artefacts.
    """
    if not isinstance(grade, dict) or not grade:
        return []

    values = {key: clamp(grade.get(key), *limits) for key, limits in LIMITS.items()}
    lift = _triplet(grade.get("lift"), 0.0)
    gain = _triplet(grade.get("gain"), 1.0)
    filters: List[str] = []

    # 1. Colour balance: lift moves the shadows, gain the highlights. `gain` is
    #    expressed as a multiplier around 1.0 in the pack, because that is how
    #    colourists think about it, and colorbalance wants an offset around 0.
    balance = []
    for channel, value in zip("rgb", lift):
        if not _near(value, 0.0):
            balance.append(f"{channel}s={value:.4f}")
    for channel, value in zip("rgb", gain):
        if not _near(value, 1.0):
            balance.append(f"{channel}h={value - 1.0:.4f}")
    if balance:
        filters.append("colorbalance=" + ":".join(balance))

    # 2. Temperature. Warmer lifts red and drops blue; ffmpeg's own
    #    colortemperature filter takes Kelvin, which is a less useful axis for a
    #    style to express, so this stays in colorbalance's vocabulary.
    temperature = values["temperature"] / 100.0
    tint = values["tint"] / 100.0
    if not _near(temperature, 0.0) or not _near(tint, 0.0):
        parts = []
        if not _near(temperature, 0.0):
            parts.append(f"rm={temperature * 0.3:.4f}")
            parts.append(f"bm={-temperature * 0.3:.4f}")
        if not _near(tint, 0.0):
            parts.append(f"gm={tint * 0.3:.4f}")
        filters.append("colorbalance=" + ":".join(parts))

    # 3. Exposure and contrast and saturation, in one eq pass.
    eq = []
    if not _near(values["exposure"], 0.0):
        eq.append(f"brightness={values['exposure']:.4f}")
    if not _near(values["contrast"], 1.0):
        eq.append(f"contrast={values['contrast']:.4f}")
    if not _near(values["saturation"], 1.0):
        eq.append(f"saturation={values['saturation']:.4f}")
    if eq:
        filters.append("eq=" + ":".join(eq))

    # 4. Vignette. ffmpeg takes a lens angle where LARGER means stronger, and
    #    its own default is PI/5. The pack's 0..1 maps onto PI/10 (barely there)
    #    through PI/2 (extreme), so a mild 0.2 reads as mild.
    #
    #    An earlier mapping sent 0.2 to PI/1.92 -- near the maximum -- and the
    #    graded frame came out ten times darker than the source. It looked like
    #    a plausible filter string, which is why this was only visible by
    #    measuring the pixels.
    if not _near(values["vignette"], 0.0):
        divisor = 10.0 - 8.0 * values["vignette"]
        filters.append(f"vignette=angle=PI/{divisor:.3f}")

    # 5. Sharpen, after the grade so it works on the final contrast.
    if not _near(values["sharpen"], 0.0):
        filters.append(f"unsharp=5:5:{values['sharpen']:.3f}:5:5:0")

    # 6. Grain last, so it is not sharpened. Sharpened noise reads as
    #    compression artefacts rather than film.
    if not _near(values["grain"], 0.0):
        filters.append(f"noise=alls={int(values['grain'] * 40)}:allf=t")

    return filters


def filter_string(grade: Dict[str, Any] | None) -> str:
    """The filters as one comma-joined string, or "" for a neutral grade."""
    return ",".join(build_filters(grade))
