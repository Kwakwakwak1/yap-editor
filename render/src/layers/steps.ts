import type {Segment} from "../types";

/**
 * Which numbered step is on screen, and what it is called.
 *
 * Kept separate from the component because the numbering rule is the part with
 * an opinion in it, and an opinion is worth a test.
 */

export type StepSource = "segment.beat" | "script.label" | "index";

export interface StepLabelsSpec {
  enabled?: boolean;
  source?: StepSource;
  /** `{n}`, `{total}` and `{label}` are substituted. */
  format?: string;
  family?: string;
  size?: number;
  color?: string;
  anchor?: import("../style/types").Anchor;
}

/**
 * Beats that open or close a reel rather than instruct.
 *
 * A tutorial's hook is not "Step 1". Numbering it as one is the difference
 * between a badge that helps someone follow along and a badge that is simply
 * counting.
 */
const BOOKEND_BEATS = new Set([
  "hook",
  "intro",
  "opening",
  "payoff",
  "close",
  "closing",
  "cta",
  "outro",
]);

interface Step {
  index: number;
  total: number;
  label: string;
}

/**
 * Number the steps in a cut.
 *
 * Only STRUCTURAL segments are counted. A mechanical segment is a silence trim
 * inside one continuous instruction -- numbering it would split a single step
 * into "Step 2" and "Step 3" halfway through a sentence -- so it inherits the
 * step it sits inside.
 */
export function stepsFor(
  segments: Segment[] | undefined,
  source: StepSource = "segment.beat",
): (Step | null)[] {
  if (!segments?.length) return [];

  const isStep = (segment: Segment) =>
    segment.kind === "structural" &&
    (source === "index" || !BOOKEND_BEATS.has((segment.beat ?? "").toLowerCase()));

  const total = segments.filter(isStep).length;
  let counted = 0;
  let carried: Step | null = null;

  return segments.map((segment) => {
    if (isStep(segment)) {
      counted += 1;
      carried = {
        index: counted,
        total,
        label: source === "index" ? "" : (segment.label ?? segment.beat ?? ""),
      };
      return carried;
    }
    // A mechanical join inside a step keeps that step's badge on screen. A
    // structural bookend after the last step (a payoff, a CTA) clears it.
    return segment.kind === "mechanical" ? carried : null;
  });
}

/** The badge text at this moment, or null when nothing should be drawn. */
export function stepLabelAt(
  spec: StepLabelsSpec | null | undefined,
  segments: Segment[] | undefined,
  time: number,
): string | null {
  if (!spec || spec.enabled === false) return null;

  const steps = stepsFor(segments, spec.source);
  if (!steps.length) return null;

  const index = (segments ?? []).findIndex(
    (segment) => time >= segment.offset && time < segment.offset + segment.duration,
  );
  const step = index >= 0 ? steps[index] : null;
  if (!step) return null;

  const text = (spec.format ?? "Step {n}")
    .replace(/\{n\}/g, String(step.index))
    .replace(/\{total\}/g, String(step.total))
    .replace(/\{label\}/g, step.label)
    .trim();

  // A format that resolves to nothing -- "{label}" with no label -- draws
  // nothing, rather than an empty badge sitting over the footage.
  return text.length ? text : null;
}
