import {describe, expect, it} from "vitest";

import type {Segment} from "../types";
import {transitionAt, transitionStyle} from "./presets";

const segments: Segment[] = [
  {offset: 0, duration: 4, beat: "hook", kind: "structural"},
  {offset: 4, duration: 4, beat: "point", kind: "mechanical"},
  {offset: 8, duration: 4, beat: "payoff", kind: "structural"},
];

const spec = {
  atSegmentBoundary: {
    structural: {preset: "whip" as const, durationMs: 200, intensity: 0.75},
    mechanical: {preset: "none" as const},
  },
};

describe("transitionAt", () => {
  it("fires at a structural join", () => {
    const frame = transitionAt(spec, segments, 8);
    expect(frame?.preset).toBe("whip");
    expect(frame?.progress).toBeCloseTo(1);
  });

  it("decays across its duration", () => {
    expect(transitionAt(spec, segments, 8.1)?.progress).toBeCloseTo(0.5, 2);
    expect(transitionAt(spec, segments, 8.25)).toBeNull();
  });

  it("does NOT fire at a mechanical join", () => {
    // A mechanical join is a silence trim the viewer never sees. Punctuating
    // every one is noise that stops the punctuation meaning anything.
    expect(transitionAt(spec, segments, 4)).toBeNull();
  });

  it("does not punctuate the start of the reel", () => {
    // Frame 0 is not a join. Flashing there reads as a glitch, not an edit.
    expect(transitionAt(spec, segments, 0)).toBeNull();
  });

  it("returns nothing when the style asks for none", () => {
    const quiet = {atSegmentBoundary: {structural: {preset: "none" as const}}};
    expect(transitionAt(quiet, segments, 8)).toBeNull();
  });

  it("returns nothing without segments or a spec", () => {
    expect(transitionAt(undefined, segments, 8)).toBeNull();
    expect(transitionAt(spec, undefined, 8)).toBeNull();
  });
});

describe("transitionStyle", () => {
  it("contributes nothing at all when idle", () => {
    // An un-punctuated style must add no CSS, not a no-op filter: a filter
    // property alone changes compositing and sub-pixel sampling, which would
    // break the legacy packs' frame identity.
    expect(transitionStyle(null)).toEqual({});
    expect(transitionStyle({progress: 0, preset: "whip", intensity: 1})).toEqual({});
  });

  it("scales with intensity", () => {
    const strong = transitionStyle({progress: 1, preset: "blur-pulse", intensity: 1});
    const weak = transitionStyle({progress: 1, preset: "blur-pulse", intensity: 0.25});
    expect(strong.filter).toBe("blur(10px)");
    expect(weak.filter).toBe("blur(2.5px)");
  });

  it("flashes with brightness rather than a white overlay", () => {
    // An overlay would sit above the captions and wash the text out along with
    // the footage.
    expect(transitionStyle({progress: 1, preset: "flash", intensity: 1}).filter)
      .toContain("brightness");
  });

  it("degrades an unknown preset to nothing rather than throwing", () => {
    expect(transitionStyle({progress: 1, preset: "star-wipe" as never, intensity: 1}))
      .toEqual({});
  });
});
