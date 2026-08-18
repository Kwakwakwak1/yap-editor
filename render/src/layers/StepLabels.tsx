import React from "react";
import {useCurrentFrame, useVideoConfig} from "remotion";

import {resolveFont} from "../fonts/registry";
import type {Segment} from "../types";
import {stepLabelAt, type StepLabelsSpec} from "./steps";

/**
 * The numbered step badge -- Blueprint's signature, and the reason tutorials
 * are worth a style of their own.
 *
 * A pill rather than plain text: it sits over moving footage for the whole of a
 * step, and text alone becomes unreadable the moment the shot brightens.
 */
export const StepLabels: React.FC<{
  spec?: StepLabelsSpec | null;
  segments?: Segment[];
}> = ({spec, segments}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const text = stepLabelAt(spec, segments, frame / fps);
  if (!text) return null;

  const anchor = spec?.anchor ?? {};
  const edge = anchor.edge ?? "top-left";
  const offset = anchor.offset;
  const [insetX, insetY] = Array.isArray(offset)
    ? offset
    : [anchor.insetX ?? 64, typeof offset === "number" ? offset : 220];

  const size = spec?.size ?? 34;

  return (
    <div
      style={{
        position: "absolute",
        [edge.startsWith("bottom") ? "bottom" : "top"]: insetY,
        left: insetX,
        display: "inline-flex",
        alignItems: "center",
        gap: size * 0.4,
        padding: `${size * 0.42}px ${size * 0.72}px`,
        borderRadius: size * 0.34,
        backgroundColor: "rgba(0,0,0,0.62)",
        // The hairline is what keeps the pill legible over a bright shot
        // without making the fill opaque enough to read as a graphic.
        boxShadow: `inset 0 0 0 1.5px ${spec?.color ?? "#ffffff"}`,
        fontFamily: resolveFont(spec?.family),
        fontSize: size,
        fontWeight: 700,
        letterSpacing: size * 0.02,
        color: spec?.color ?? "#ffffff",
        whiteSpace: "nowrap",
        pointerEvents: "none",
      }}
    >
      {text}
    </div>
  );
};
