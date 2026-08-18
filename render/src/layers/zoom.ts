import type {ResolvedStyle} from "../style/types";
import type {Segment} from "../types";

/**
 * The scale applied to the footage at a given moment.
 *
 * Zoom is a transform on the video element, which is free -- but it only looks
 * good because assemble stages the cut at `stageWidth` (canvas x maxScale). A
 * frame scaled past its source is a frame upscaled, and every zoom style would
 * render soft. That coupling is the reason maxScale is clamped in the schema.
 */

export type ZoomMode = "none" | "slow-drift" | "beat" | "punch";

export interface ZoomSpec {
  mode?: ZoomMode;
  baseScale?: number;
  maxScale?: number;
  anchor?: "center" | "upper-third" | "face";
  onSegmentStart?: {
    scaleFrom?: number;
    scaleTo?: number;
    durationMs?: number;
    easing?: "linear" | "outCubic" | "inOutCubic" | "spring";
    applyTo?: ("structural" | "mechanical")[];
  };
  drift?: {perSecond?: number};
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function ease(name: string | undefined, t: number): number {
  switch (name) {
    case "linear":
      return t;
    case "inOutCubic":
      return easeInOutCubic(t);
    // `spring` is deliberately approximated by outCubic rather than simulated.
    // Remotion's spring() needs fps and a frame, and a real spring can overshoot
    // past maxScale -- which is exactly the value stageWidth was sized for, so
    // an overshoot renders the soft frame the staging exists to prevent.
    default:
      return easeOutCubic(t);
  }
}

/**
 * Which segment contains a moment, and how far into it we are.
 *
 * Returns null when props carry no segments, which is what older staged props
 * look like -- those simply get no beat-synced zoom rather than an error.
 */
export function segmentAt(segments: Segment[] | undefined, time: number) {
  if (!segments || segments.length === 0) return null;
  for (const segment of segments) {
    if (time >= segment.offset && time < segment.offset + segment.duration) {
      return {segment, elapsed: time - segment.offset};
    }
  }
  const last = segments[segments.length - 1];
  return {segment: last, elapsed: time - last.offset};
}

export function scaleAt(
  style: ResolvedStyle,
  segments: Segment[] | undefined,
  time: number,
): number {
  const zoom = ((style as {zoom?: ZoomSpec}).zoom) ?? {};
  const mode = zoom.mode ?? "none";
  if (mode === "none") return 1;

  const base = zoom.baseScale ?? 1;
  const max = Math.max(zoom.maxScale ?? base, base);

  // A slow push across the whole reel. Clamped at maxScale so it cannot drift
  // past what the staged frame can cover, however long the reel runs.
  const drift = Math.min((zoom.drift?.perSecond ?? 0) * time, Math.max(max - base, 0));
  let scale = base + drift;

  const punch = zoom.onSegmentStart;
  if ((mode === "beat" || mode === "punch") && punch) {
    const found = segmentAt(segments, time);
    // `applyTo` is what keeps a punch meaningful: firing on every mechanical
    // join -- a silence trim the viewer never sees -- makes the reel twitch
    // constantly and stops the punch marking anything at all.
    const kinds = punch.applyTo ?? ["structural"];
    if (found && kinds.includes(found.segment.kind)) {
      const duration = (punch.durationMs ?? 0) / 1000;
      if (duration > 0 && found.elapsed < duration) {
        const t = ease(punch.easing, found.elapsed / duration);
        const from = punch.scaleFrom ?? max;
        const to = punch.scaleTo ?? base;
        scale = from + (to - from) * t;
      }
    }
  }

  // Never below 1: scaling under 1 would reveal the frame edges.
  return Math.min(Math.max(scale, 1), max);
}

/** Transform origin for the zoom anchor. `face` falls back to upper-third
 *  until face detection exists -- a speaker's eyes sit near there, so it is a
 *  reasonable stand-in rather than a placeholder that looks wrong. */
export function originFor(style: ResolvedStyle): string {
  const anchor = ((style as {zoom?: ZoomSpec}).zoom)?.anchor ?? "center";
  return anchor === "center" ? "50% 50%" : "50% 33%";
}
