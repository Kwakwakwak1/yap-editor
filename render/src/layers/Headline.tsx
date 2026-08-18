import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";

import {resolveFont} from "../fonts/registry";
import {applyCase} from "../style/defaults";
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

  const anchor = spec.anchor ?? {};
  const offset = typeof anchor.offset === "number" ? anchor.offset : (anchor.offset?.[1] ?? 96);

  return (
    <div
      style={{
        position: "absolute",
        [anchor.edge === "bottom" ? "bottom" : "top"]: offset,
        left: 60,
        right: 60,
        width: width - 120,
        textAlign: "center",
        fontFamily: resolveFont(spec.family),
        fontSize: spec.size ?? 62,
        fontWeight: spec.weight ?? 700,
        color: spec.color ?? "#ffffff",
        lineHeight: 1.16,
        letterSpacing: -1,
        textShadow: "0 2px 12px rgba(0,0,0,0.6)",
        opacity,
        pointerEvents: "none",
      }}
    >
      {applyCase(text, spec.case)}
    </div>
  );
};
