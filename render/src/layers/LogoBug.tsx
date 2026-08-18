import React from "react";
import {Img} from "remotion";

import type {LogoBug as LogoBugSpec} from "../style/types";

/**
 * The brand mark in a corner.
 *
 * Renders nothing when the block is null -- resolve_style switches a furniture
 * block off entirely when the brand has no asset for it, rather than leaving an
 * empty frame where a logo would be.
 */
export const LogoBug: React.FC<{spec?: LogoBugSpec | null}> = ({spec}) => {
  if (!spec || !spec.asset) return null;

  const [insetX, insetY] = spec.inset ?? [44, 44];
  const corner = spec.corner ?? "top-right";
  const vertical = corner.startsWith("top") ? {top: insetY} : {bottom: insetY};
  const horizontal = corner.endsWith("left") ? {left: insetX} : {right: insetX};

  return (
    <Img
      src={spec.asset}
      style={{
        position: "absolute",
        ...vertical,
        ...horizontal,
        width: spec.size ?? 84,
        height: "auto",
        opacity: spec.opacity ?? 1,
        pointerEvents: "none",
      }}
    />
  );
};
