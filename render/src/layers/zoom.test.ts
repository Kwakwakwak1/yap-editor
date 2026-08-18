import {describe, expect, it} from "vitest";

import type {Segment} from "../types";
import {originFor, scaleAt, segmentAt} from "./zoom";

const segments: Segment[] = [
  {offset: 0, duration: 4, beat: "hook", kind: "structural"},
  {offset: 4, duration: 4, beat: "point", kind: "mechanical"},
  {offset: 8, duration: 4, beat: "payoff", kind: "structural"},
];

const punchy = {
  zoom: {
    mode: "beat" as const,
    baseScale: 1.03,
    maxScale: 1.18,
    onSegmentStart: {
      scaleFrom: 1.18, scaleTo: 1.03, durationMs: 400,
      easing: "outCubic" as const, applyTo: ["structural" as const],
    },
  },
};

describe("scaleAt", () => {
  it("is exactly 1 when a style asks for no zoom", () => {
    // Not 1.0001: an un-zoomed style must produce byte-identical frames to no
    // transform at all, which is what the legacy packs depend on.
    expect(scaleAt({}, segments, 2)).toBe(1);
    expect(scaleAt({zoom: {mode: "none"}} as never, segments, 2)).toBe(1);
  });

  it("punches in at the start of a structural segment and settles", () => {
    const atStart = scaleAt(punchy as never, segments, 0);
    const settled = scaleAt(punchy as never, segments, 3.9);
    expect(atStart).toBeCloseTo(1.18, 2);
    expect(settled).toBeCloseTo(1.03, 2);
    expect(atStart).toBeGreaterThan(settled);
  });

  it("does NOT punch on a mechanical join", () => {
    // A mechanical join is a silence trim the viewer never sees. Punching on
    // every one makes the reel twitch constantly and stops the punch marking
    // anything at all.
    expect(scaleAt(punchy as never, segments, 4)).toBeCloseTo(1.03, 2);
  });

  it("never scales below 1, which would show the frame edges", () => {
    const shrinking = {zoom: {mode: "beat", baseScale: 0.5, maxScale: 1.2}};
    expect(scaleAt(shrinking as never, segments, 1)).toBeGreaterThanOrEqual(1);
  });

  it("never exceeds maxScale, because stageWidth was sized for exactly that", () => {
    // Past maxScale the frame is upscaled beyond its staged resolution and the
    // reel goes soft -- the failure staging exists to prevent.
    const drifting = {zoom: {mode: "slow-drift", baseScale: 1, maxScale: 1.04,
                             drift: {perSecond: 0.01}}};
    expect(scaleAt(drifting as never, segments, 600)).toBeLessThanOrEqual(1.04);
  });

  it("drifts slowly rather than jumping", () => {
    const drifting = {zoom: {mode: "slow-drift", baseScale: 1, maxScale: 1.1,
                             drift: {perSecond: 0.01}}};
    expect(scaleAt(drifting as never, segments, 2)).toBeCloseTo(1.02, 3);
    expect(scaleAt(drifting as never, segments, 5)).toBeCloseTo(1.05, 3);
  });

  it("works when props carry no segments", () => {
    // Older staged props have none; they get no beat-synced zoom rather than
    // an error.
    expect(scaleAt(punchy as never, undefined, 1)).toBeCloseTo(1.03, 2);
  });
});

describe("segmentAt", () => {
  it("finds the segment containing a moment", () => {
    expect(segmentAt(segments, 5)?.segment.beat).toBe("point");
    expect(segmentAt(segments, 5)?.elapsed).toBeCloseTo(1);
  });

  it("treats a boundary as the start of the next segment", () => {
    expect(segmentAt(segments, 4)?.segment.beat).toBe("point");
  });

  it("clamps past the end rather than returning nothing", () => {
    // The last frame of a reel can land a hair past the final offset+duration
    // through rounding; returning null there would drop the zoom for one frame.
    expect(segmentAt(segments, 99)?.segment.beat).toBe("payoff");
  });

  it("returns null with no segments at all", () => {
    expect(segmentAt(undefined, 1)).toBeNull();
    expect(segmentAt([], 1)).toBeNull();
  });
});

describe("originFor", () => {
  it("anchors on the upper third for a speaker", () => {
    expect(originFor({zoom: {anchor: "upper-third"}} as never)).toBe("50% 33%");
  });

  it("falls back to the upper third for face, which is where eyes sit", () => {
    expect(originFor({zoom: {anchor: "face"}} as never)).toBe("50% 33%");
  });

  it("centres by default", () => {
    expect(originFor({} as never)).toBe("50% 50%");
  });
});
