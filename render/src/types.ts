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
