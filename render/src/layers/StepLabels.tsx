import React from "react";
import {useCurrentFrame, useVideoConfig} from "remotion";

import {stepBadgeStyle} from "../style/css";
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

  return (
    <div style={stepBadgeStyle(spec)}>
      {text}
    </div>
  );
};
