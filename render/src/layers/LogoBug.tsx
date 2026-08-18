import React from "react";
import {Img, staticFile} from "remotion";

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

  const [insetX = 44, insetY = 44] = spec.inset ?? [];
  const corner = spec.corner ?? "top-right";
  const vertical = corner.startsWith("top") ? {top: insetY} : {bottom: insetY};
  const horizontal = corner.endsWith("left") ? {left: insetX} : {right: insetX};

  // A staged path is relative to render/public/ and resolves through
  // staticFile(). An absolute URL is accepted so StyleLab can point at a live
  // asset while authoring, but the worker localises everything before a real
  // render -- the render path must not touch the network mid-frame.
  const source = /^https?:\/\//.test(spec.asset)
    ? spec.asset
    : staticFile(spec.asset);

  return (
    <Img
      src={source}
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
