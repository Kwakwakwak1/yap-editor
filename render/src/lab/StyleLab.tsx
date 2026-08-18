import React from "react";

import {StyledReel} from "../StyledReel";
import type {ResolvedStyle} from "../style/types";
import type {Caption} from "../types";
import fixture from "./fixture.json";

/**
 * The authoring loop for style packs.
 *
 * Open Remotion Studio, edit a pack, watch it change. Without this, designing a
 * style means editing JSON, running the API to resolve it, running assemble to
 * stage it, and paying a four-minute render to see whether the caption sits
 * three pixels too low. That loop is unbearable enough that styles would end up
 * designed by guessing.
 *
 * The fixture is committed on purpose -- captions with REAL per-word timings
 * lifted from the sample transcript, and a clip under public/lab/. StyleLab has
 * to work on a fresh clone, before anything has been assembled, or authoring a
 * style would require running the pipeline first.
 *
 * Real word timings matter here specifically: a style is judged on how its
 * highlight lands on the beat, and the character-length estimate is wrong by up
 * to 11 frames. Authoring against estimated timings would mean tuning a style
 * to compensate for a bug.
 */

export interface StyleLabProps extends Record<string, unknown> {
  /** Which shipped style to preview. Editable live in the Studio sidebar. */
  style: string;
  /** Paste a resolved spec here to preview one that is not shipped yet. */
  override?: ResolvedStyle | null;
}

const STYLES = fixture.styles as Record<string, ResolvedStyle>;

export const LAB_DEFAULTS: StyleLabProps = {
  style: "impact",
  override: null,
};

export const StyleLab: React.FC<StyleLabProps> = ({style, override}) => {
  const resolved = override ?? STYLES[style] ?? STYLES.impact;

  return (
    <StyledReel
      clip="lab/clip.mp4"
      headline="the edit is not the hard part"
      captions={fixture.captions as Caption[]}
      style={resolved}
      sourceOrientation="landscape"
    />
  );
};

/** Every style the lab can show, for the Studio dropdown and for tests. */
export const LAB_STYLE_IDS = Object.keys(STYLES);
