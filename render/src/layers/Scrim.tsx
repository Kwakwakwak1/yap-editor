import React from "react";

import {scrimStyle} from "../style/css";
import type {ScrimEdge} from "../style/types";

/**
 * The gradient behind the captions and the headline.
 *
 * Its job is contrast: white text over arbitrary footage is unreadable without
 * something between them, and a scrim keeps the footage visible where a solid
 * bar would not. The geometry lives in ../style/css so the style editor's
 * preview draws the same band.
 */
export const Scrim: React.FC<{edge: "top" | "bottom"; spec?: ScrimEdge; width: number}> = ({
  edge,
  spec,
  width,
}) => {
  const style = scrimStyle(edge, spec, width);
  return style ? <div style={style} /> : null;
};
