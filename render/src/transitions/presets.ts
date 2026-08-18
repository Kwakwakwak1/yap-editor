import type React from "react";

import {segmentAt} from "../layers/zoom";
import type {Segment} from "../types";

/**
 * Punctuation at a cut, not a cross-dissolve.
 *
 * A dissolve needs two overlapping media streams, and cut.mp4 is a single
 * concat -- which is also the preview. Doing it properly means staging every
 * segment separately, teaching Remotion a TransitionSeries, and redefining the
 * reel's duration as sum(durations) - sum(overlaps), which breaks
 * planned_duration and verify's duration check. That is tracked separately and
 * deliberately out of scope.
 *
 * What IS possible on a single stream is punctuation: a flash, a whip, a blur
 * pulse over the join. These read as intent without needing the frames either
 * side to coexist.
 */

export type TransitionPreset =
  | "none"
  | "flash"
  | "whip"
  | "zoom-punch"
  | "blur-pulse"
  | "film-burn";

export interface TransitionSpec {
  preset?: TransitionPreset;
  durationMs?: number;
  intensity?: number;
}

export interface TransitionsSpec {
  atSegmentBoundary?: {
    structural?: TransitionSpec;
    mechanical?: TransitionSpec;
  };
  atHook?: TransitionSpec;
  overlay?: TransitionSpec;
  totalOverlapSeconds?: number;
}

export interface TransitionFrame {
  /** 1 at the join, falling to 0 as the transition completes. */
  progress: number;
  preset: TransitionPreset;
  intensity: number;
}

/**
 * How far into a transition this moment is.
 *
 * Transitions fire at the START of a segment, not across the boundary, because
 * a single stream has no "across" -- there is one frame, and then the next.
 */
export function transitionAt(
  transitions: TransitionsSpec | undefined,
  segments: Segment[] | undefined,
  time: number,
): TransitionFrame | null {
  if (!transitions) return null;
  const found = segmentAt(segments, time);
  if (!found) return null;

  // The start of the reel is not a join. Punctuating it would flash on frame 0
  // of every reel, which reads as a glitch rather than an edit.
  if (found.segment.offset <= 0) return null;

  const spec =
    found.segment.kind === "structural"
      ? transitions.atSegmentBoundary?.structural
      : transitions.atSegmentBoundary?.mechanical;

  const preset = spec?.preset ?? "none";
  if (preset === "none") return null;

  const duration = (spec?.durationMs ?? 0) / 1000;
  if (duration <= 0 || found.elapsed > duration) return null;

  return {
    progress: 1 - found.elapsed / duration,
    preset,
    intensity: spec?.intensity ?? 1,
  };
}

/**
 * The CSS a transition contributes at this moment.
 *
 * Returns an empty object when nothing is happening, so an un-punctuated style
 * adds no properties at all -- a `filter` property alone can change compositing
 * and sub-pixel sampling, which would break the legacy packs' frame identity.
 */
export function transitionStyle(frame: TransitionFrame | null): React.CSSProperties {
  if (!frame || frame.progress <= 0) return {};
  const {progress, intensity, preset} = frame;
  const amount = progress * intensity;

  switch (preset) {
    case "flash":
      // Brightness, not a white overlay: an overlay would sit above the
      // captions and wash the text out along with the footage.
      return {filter: `brightness(${1 + amount * 1.6})`};
    case "whip":
      return {filter: `blur(${amount * 18}px)`, transform: `translateX(${amount * 40}px)`};
    case "zoom-punch":
      return {transform: `scale(${1 + amount * 0.06})`};
    case "blur-pulse":
      return {filter: `blur(${amount * 10}px)`};
    case "film-burn":
      return {filter: `brightness(${1 + amount * 0.9}) sepia(${amount * 0.6})`};
    default:
      // Fail-soft: an uglier reel beats a dead render, and minRendererVersion
      // is the fail-fast that runs before any of this.
      return {};
  }
}
