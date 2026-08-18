/**
 * The resolved style spec, as the API hands it to the worker.
 *
 * "Resolved" means every @token has already been replaced with a real value:
 * the brand's accent, a bundled font key, an asset URL. The renderer never sees
 * a pack or a brand, only this.
 *
 * Mirrors render/style-pack.schema.json. Every field is optional here even
 * where the schema requires it, because a spec can arrive from an older pack
 * version -- `withDefaults` fills the gaps rather than the components guarding
 * each field.
 */

export type CaptionMode = "word-highlight" | "line-pop" | "static" | "off";
export type TextCase = "upper" | "lower" | "sentence" | "as-written";
export type AnimationPreset = "none" | "pop" | "rise" | "fade" | "blur-in" | "typewriter";

export interface Anchor {
  edge?: "top" | "bottom" | "top-left" | "bottom-left" | "center";
  /**
   * One number for the anchored edge, or [x, y]. A plain array rather than a
   * tuple because these arrive from JSON, where TypeScript widens `[64, 240]`
   * to `number[]` and a tuple type then rejects the whole fixture.
   */
  offset?: number | number[];
  insetX?: number;
}

export interface EnterExit {
  preset?: "none" | "fade" | "rise" | "pop" | "blur-in";
  distance?: number;
  durationMs?: number;
}

export interface Shadow {
  blur?: number;
  y?: number;
  color?: string;
}

export interface CaptionStyle {
  mode?: CaptionMode;
  family?: string;
  weight?: number;
  size?: {portrait?: number; landscape?: number};
  case?: TextCase;
  tracking?: number;
  lineHeight?: number;
  align?: "left" | "center" | "right";
  anchor?: Anchor;
  safeArea?: "reels" | "none";
  colors?: {idle?: string; active?: string; idleOpacity?: number};
  box?: {
    enabled?: boolean;
    fill?: string;
    opacity?: number;
    radius?: number;
    padX?: number;
    padY?: number;
    scope?: "active-word" | "line";
  };
  stroke?: {width?: number; color?: string};
  shadow?: Shadow | Shadow[];
  animation?: {
    preset?: AnimationPreset;
    activeScale?: number;
    spring?: {damping?: number; stiffness?: number; mass?: number};
    enter?: EnterExit;
    exit?: EnterExit;
  };
}

export interface ScrimEdge {
  mode?: "none" | "gradient" | "solid";
  height?: number;
  from?: string;
  to?: string;
}

export interface Headline {
  enabled?: boolean;
  family?: string;
  size?: number;
  weight?: number;
  case?: TextCase;
  color?: string;
  anchor?: Anchor;
  holdSeconds?: number;
  animation?: EnterExit;
}

export interface LogoBug {
  /** Already an asset URL, or null when the brand had none. */
  asset?: string | null;
  corner?: "top-left" | "top-right" | "bottom-left" | "bottom-right";
  size?: number;
  opacity?: number;
  /** [x, y]. A plain array because it arrives from JSON. */
  inset?: number[];
}

export interface LowerThird {
  enabled?: boolean;
  /**
   * The dotted path the PACK declared ("job.speaker"). Kept for provenance;
   * the renderer never resolves it.
   */
  source?: string;
  /** What the API resolved that path to. Empty means draw nothing. */
  text?: string | null;
  family?: string;
  size?: number;
  color?: string;
  rule?: {width?: number; color?: string};
  /** [from, to] in seconds. A plain array because it arrives from JSON,
   *  where a tuple type would fail to widen. */
  showSeconds?: number[];
}

export interface Endcard {
  asset?: string | null;
  durationSeconds?: number;
  fit?: "cover" | "contain";
  background?: string;
  audio?: "duck" | "silence" | "continue";
}

export interface ResolvedStyle {
  id?: string;
  version?: number;
  minRendererVersion?: number;
  sourceFit?: {portrait?: string; landscape?: string};
  captions?: CaptionStyle;
  scrim?: {top?: ScrimEdge; bottom?: ScrimEdge};
  /**
   * Furniture blocks are `null` -- not merely absent -- when the brand had no
   * asset for them. resolve_style switches the whole block off rather than
   * drawing it empty, so a missing endcard also stops claiming its duration.
   */
  furniture?: {
    headline?: Headline | null;
    logoBug?: LogoBug | null;
    stepLabels?: import("../layers/steps").StepLabelsSpec | null;
    lowerThird?: LowerThird | null;
    endcard?: Endcard | null;
  };
  transitions?: import("../transitions/presets").TransitionsSpec;
  zoom?: import("../layers/zoom").ZoomSpec;
  render?: {
    canvas?: "portrait" | "landscape";
    width?: number;
    height?: number;
    stageWidth?: number;
    tokens?: Record<string, unknown>;
    assets?: {role: string; url: string; sha256: string; dest: string}[];
  };
}
