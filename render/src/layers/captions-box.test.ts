import {describe, expect, it} from "vitest";

import {boxFill} from "./Captions";

describe("boxFill", () => {
  it("folds opacity into the colour rather than onto the element", () => {
    // A CSS `opacity` would fade the text sitting on the box along with the
    // box, which is the opposite of what a scrim behind text is for.
    expect(boxFill("#0B0B0B", 0.85)).toBe("rgba(11, 11, 11, 0.85)");
  });

  it("leaves a fully opaque fill as the hex it was", () => {
    expect(boxFill("#0B0B0B", 1)).toBe("#0B0B0B");
    expect(boxFill("#0B0B0B", undefined)).toBe("#0B0B0B");
  });

  it("expands shorthand hex", () => {
    expect(boxFill("#fff", 0.5)).toBe("rgba(255, 255, 255, 0.5)");
  });

  it("passes a colour it cannot parse straight through", () => {
    // An uglier box beats a dead render, and the schema is the fail-fast.
    expect(boxFill("rgba(0,0,0,0.4)", 0.5)).toBe("rgba(0,0,0,0.4)");
  });

  it("draws nothing without a fill", () => {
    expect(boxFill(undefined, 0.5)).toBeUndefined();
  });
});
