import {describe, expect, it} from "vitest";

import type {Segment} from "../types";
import {stepLabelAt, stepsFor} from "./steps";

const tutorial: Segment[] = [
  {offset: 0, duration: 3, beat: "hook", kind: "structural"},
  {offset: 3, duration: 5, beat: "pat it dry", kind: "structural"},
  {offset: 8, duration: 4, beat: "pat it dry", kind: "mechanical"},
  {offset: 12, duration: 6, beat: "high heat", kind: "structural"},
  {offset: 18, duration: 2, beat: "payoff", kind: "structural"},
];

describe("stepsFor", () => {
  it("does not number the hook or the payoff", () => {
    // A tutorial's hook is not "Step 1". Numbering it is the difference between
    // a badge that helps someone follow along and one that is only counting.
    const steps = stepsFor(tutorial);
    expect(steps[0]).toBeNull();
    expect(steps[4]).toBeNull();
    expect(steps[1]?.index).toBe(1);
    expect(steps[3]?.index).toBe(2);
  });

  it("carries the step across a mechanical join inside it", () => {
    // A silence trim mid-instruction must not advance the number, or one step
    // becomes "Step 2" and "Step 3" halfway through a sentence.
    const steps = stepsFor(tutorial);
    expect(steps[2]?.index).toBe(1);
    expect(steps[2]?.label).toBe("pat it dry");
  });

  it("counts the total over steps only", () => {
    expect(stepsFor(tutorial)[1]?.total).toBe(2);
  });

  it("prefers a script label over the beat name", () => {
    const withLabels: Segment[] = [
      {offset: 0, duration: 4, beat: "step 1", kind: "structural", label: "Pat it dry"},
    ];
    expect(stepsFor(withLabels, "script.label")[0]?.label).toBe("Pat it dry");
  });

  it("numbers every structural segment when the source is index", () => {
    // `index` is the escape hatch for a cut with no editorial beat names, so
    // the bookend rule -- which reads those names -- must not apply.
    const steps = stepsFor(tutorial, "index");
    expect(steps[0]?.index).toBe(1);
    expect(steps[0]?.total).toBe(4);
  });

  it("returns nothing for a cut with no segments", () => {
    expect(stepsFor(undefined)).toEqual([]);
    expect(stepsFor([])).toEqual([]);
  });
});

describe("stepLabelAt", () => {
  const spec = {enabled: true, format: "Step {n}/{total} · {label}"};

  it("formats the step on screen at that moment", () => {
    expect(stepLabelAt(spec, tutorial, 5)).toBe("Step 1/2 · pat it dry");
    expect(stepLabelAt(spec, tutorial, 13)).toBe("Step 2/2 · high heat");
  });

  it("draws nothing over the hook or the payoff", () => {
    expect(stepLabelAt(spec, tutorial, 1)).toBeNull();
    expect(stepLabelAt(spec, tutorial, 19)).toBeNull();
  });

  it("draws nothing when the block is off", () => {
    expect(stepLabelAt({enabled: false}, tutorial, 5)).toBeNull();
    expect(stepLabelAt(null, tutorial, 5)).toBeNull();
  });

  it("draws nothing rather than an empty badge", () => {
    // "{label}" with no label must not leave a pill floating over the footage.
    const bare: Segment[] = [{offset: 0, duration: 4, beat: "", kind: "structural"}];
    expect(stepLabelAt({enabled: true, format: "{label}"}, bare, 1)).toBeNull();
  });

  it("draws nothing past the end of the cut", () => {
    expect(stepLabelAt(spec, tutorial, 99)).toBeNull();
  });
});
