export type CaptionWord = {
  from: number;
  to: number;
  text: string;
};

export type Caption = {
  from: number;
  to: number;
  text: string;
  /**
   * Measured per-word timings, written by assemble.py's caption builder.
   *
   * Optional because props staged before it existed, and any hand-written
   * props, carry only `text` — consumers must fall back to estimating. Prefer
   * these whenever present: the estimate is wrong by up to ~370ms (11 frames at
   * 30fps) on real footage, which is enough to highlight the wrong word.
   */
  words?: CaptionWord[];
};

/**
 * One kept span of a take, placed on the assembled cut's timeline.
 *
 * `kind` distinguishes an edit the editor made a decision about (`structural`)
 * from one the mechanical pass made (`mechanical`) — the distinction a style
 * uses to punctuate meaningful joins and leave routine ones invisible.
 */
export type Segment = {
  offset: number;
  duration: number;
  beat: string;
  kind: "structural" | "mechanical";
  /**
   * The short on-screen label from a script's `# Step 2 :: Pat it dry`
   * heading. Absent until a job has a script attached, which is why step
   * badges fall back to the beat name.
   */
  label?: string;
};

export type LandscapeProps = {
  clip: string;
  audio?: string;
  headline: string;
  captions: Caption[];
  /** Optional: props staged before this field existed carry no segments. */
  segments?: Segment[];
  durationInSeconds?: number;
  fps?: number;
};

/**
 * What StyledReel receives.
 *
 * `style` is the resolved spec the API froze onto the job; `sourceOrientation`
 * is the probe's reading of the footage, which selects the fit. They are
 * separate on purpose -- the canvas is what the operator asked for, the fit is
 * how the footage sits inside it, and collapsing the two is what made the
 * composer's Aspect picker do nothing for months.
 */
export type StyledReelProps = LandscapeProps & {
  style?: import("./style/types").ResolvedStyle;
  sourceOrientation?: "portrait" | "landscape";
};
