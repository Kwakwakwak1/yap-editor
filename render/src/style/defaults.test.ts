import {describe, expect, it} from "vitest";

import {applyCase, withDefaults} from "./defaults";

describe("applyCase", () => {
  it("shouts only when a style asks for it", () => {
    expect(applyCase("edit", "upper")).toBe("EDIT");
    expect(applyCase("EDIT", "lower")).toBe("edit");
    // The default: a style must opt in to changing the transcript's own casing.
    expect(applyCase("iPhone", "as-written")).toBe("iPhone");
    expect(applyCase("iPhone", undefined)).toBe("iPhone");
  });

  describe("sentence case", () => {
    it("capitalises the first word of a cue", () => {
      expect(applyCase("why", "sentence", true)).toBe("Why");
    });

    it("leaves every other word alone", () => {
      // The bug this exists for: captions render word by word, so each word is
      // its own element -- that is what lets the active one be coloured and
      // scaled. Applying sentence case in that loop produced Title Case:
      // "Why Does Every Edit" instead of "Why does every edit". Caught by
      // looking at a render, which is an expensive way to find it.
      expect(applyCase("does", "sentence", false)).toBe("does");
      expect(applyCase("every", "sentence", false)).toBe("every");
    });

    it("does not lowercase a proper noun mid-sentence", () => {
      expect(applyCase("Instagram", "sentence", false)).toBe("Instagram");
    });

    it("treats a word as first by default, so a lone word still reads right", () => {
      expect(applyCase("why", "sentence")).toBe("Why");
    });
  });
});

describe("withDefaults", () => {
  it("fills a spec so layers can read fields directly", () => {
    const style = withDefaults({});
    expect(style.captions?.size?.portrait).toBe(58);
    expect(style.captions?.colors?.idle).toBe("#ffffff");
    expect(style.captions?.anchor?.offset).toBe(430);
    expect(style.render?.width).toBe(1080);
  });

  it("keeps what the spec actually said", () => {
    const style = withDefaults({captions: {size: {portrait: 96}, case: "upper"}});
    expect(style.captions?.size?.portrait).toBe(96);
    expect(style.captions?.case).toBe("upper");
    // Untouched fields still get their default.
    expect(style.captions?.lineHeight).toBe(1.15);
  });

  it("does not resurrect a furniture block that was switched off", () => {
    // null means "the brand had no asset for this", and resolve_style switches
    // the whole block off rather than drawing it empty -- an endcard drawn empty
    // would still claim its duration. A naive deep merge would bring it back
    // from the defaults, which is why furniture is spread rather than merged.
    const style = withDefaults({furniture: {logoBug: null, endcard: null}});
    expect(style.furniture?.logoBug).toBeNull();
    expect(style.furniture?.endcard).toBeNull();
  });

  it("passes a shadow list through without turning it into an object", () => {
    // Spreading defaults over an array would produce {0: …, 1: …, blur: 0}.
    const style = withDefaults({
      captions: {shadow: [{blur: 10, y: 2}, {blur: 3, y: 1}]},
    });
    expect(Array.isArray(style.captions?.shadow)).toBe(true);
    expect((style.captions?.shadow as unknown[]).length).toBe(2);
  });

  it("handles an undefined spec, which is what an older pack stages", () => {
    expect(withDefaults(undefined).captions?.mode).toBe("word-highlight");
  });
});
