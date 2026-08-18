import {describe, expect, it} from "vitest";

import {FONT_REGISTRY, resolveFont} from "./registry";
import {FONT_STACKS} from "../style/css";

describe("the bundled roster", () => {
  it("carries actual font bytes for every family", () => {
    // A family with no woff2 is not a fallback, it is a silent substitution:
    // the render succeeds and draws a system face that looks plausible.
    for (const [key, font] of Object.entries(FONT_REGISTRY)) {
      expect(font.woff2, `${key} has no inlined font`).toBeTruthy();
      expect(font.woff2!.startsWith("data:font/woff2;base64,"), `${key} is not a data URI`).toBe(true);
    }
  });

  it("carries enough bytes to be a real Latin subset", () => {
    // Five of these were once Cyrillic subsets -- they loaded, parsed, reported
    // themselves ready, and had no Latin glyphs at all, so every caption fell
    // through to a system font. The smallest honest Latin subset here is ~14KB;
    // the Cyrillic ones were 6-7KB.
    for (const [key, font] of Object.entries(FONT_REGISTRY)) {
      const bytes = Math.floor((font.woff2!.length - "data:font/woff2;base64,".length) * 3 / 4);
      expect(bytes, `${key} is suspiciously small for a Latin subset`).toBeGreaterThan(12_000);
    }
  });

  it("has a stack for every key and a key for every stack", () => {
    expect(Object.keys(FONT_REGISTRY).sort()).toEqual(Object.keys(FONT_STACKS).sort());
  });

  it("falls back to dm-sans for a key that is not bundled", () => {
    expect(resolveFont("no-such-font")).toBe(FONT_STACKS["dm-sans"]);
    expect(resolveFont(undefined)).toBe(FONT_STACKS["dm-sans"]);
  });
});
