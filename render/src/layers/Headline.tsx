import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";

import {applyCase, headlineStyle} from "../style/css";
import type {Headline as HeadlineSpec} from "../style/types";

/**
 * The optional title over the opening of the reel.
 *
 * Full-bleed footage rarely needs a second title competing with the captions,
 * which is why an empty headline renders nothing at all rather than an empty
 * band -- carried over from PortraitFull, where that was a deliberate choice.
 */
export const Headline: React.FC<{
  text: string;
  spec?: HeadlineSpec | null;
  width: number;
}> = ({text, spec, width}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  if (!text || !spec || spec.enabled === false) return null;

  const time = frame / fps;
  const hold = spec.holdSeconds ?? 0;
  // holdSeconds 0 means "for the whole reel"; a positive value fades it out
  // after that point rather than cutting, so it does not pop off mid-word.
  let opacity = 1;
  if (hold > 0) {
    opacity = interpolate(time, [hold - 0.4, hold], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }
  if (opacity <= 0) return null;

  return (
    <div style={headlineStyle(spec, width, opacity)}>
      {applyCase(text, spec.case)}
    </div>
  );
};
