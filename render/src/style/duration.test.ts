import {describe, expect, it} from "vitest";

import {endcardSeconds, reelDurationSeconds} from "./duration";

describe("endcardSeconds", () => {
  it("adds the endcard to the cut", () => {
    expect(reelDurationSeconds(17.61, {furniture: {endcard: {asset: "a.png", durationSeconds: 2.2}}}))
      .toBeCloseTo(19.81);
  });

  it("adds nothing when the block is switched off", () => {
    // resolve_style nulls the whole block when the brand has no endcard.
    expect(reelDurationSeconds(17.61, {furniture: {endcard: null}})).toBe(17.61);
    expect(reelDurationSeconds(17.61, {})).toBe(17.61);
    expect(reelDurationSeconds(17.61, undefined)).toBe(17.61);
  });

  it("adds nothing when a duration was left behind without an asset", () => {
    // Otherwise every reel for a brand with no endcard ends on a black hold.
    expect(endcardSeconds({furniture: {endcard: {asset: null, durationSeconds: 2.2}}})).toBe(0);
  });

  it("ignores a nonsense duration rather than shortening the reel", () => {
    expect(endcardSeconds({furniture: {endcard: {asset: "a.png", durationSeconds: -3}}})).toBe(0);
  });
});
