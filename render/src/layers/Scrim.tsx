import React from "react";

import type {ScrimEdge} from "../style/types";

/**
 * The gradient behind the captions and the headline.
 *
 * Its job is contrast: white text over arbitrary footage is unreadable without
 * something between them, and a scrim keeps the footage visible where a solid
 * bar would not.
 */
export const Scrim: React.FC<{edge: "top" | "bottom"; spec?: ScrimEdge; width: number}> = ({
  edge,
  spec,
  width,
}) => {
  if (!spec || spec.mode === "none" || !spec.height) return null;

  const direction = edge === "top" ? "to bottom" : "to top";
  const background =
    spec.mode === "solid"
      ? spec.from
      : `linear-gradient(${direction}, ${spec.from}, ${spec.to})`;

  return (
    <div
      style={{
        position: "absolute",
        [edge]: 0,
        left: 0,
        width,
        height: spec.height,
        background,
        pointerEvents: "none",
      }}
    />
  );
};
