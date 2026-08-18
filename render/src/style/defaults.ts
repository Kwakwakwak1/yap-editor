import type {CaptionStyle, ResolvedStyle} from "./types";

/**
 * Fill a resolved spec so every component can read fields directly.
 *
 * A spec may arrive from a pack version written before a field existed, and the
 * alternative -- every layer guarding every field at its use site -- is where
 * "renders slightly wrong" bugs live. Merging once, here, means a component
 * reading `style.captions.size.portrait` always gets a number.
 *
 * Deliberately NOT a deep merge of arbitrary depth: `null` on a furniture block
 * is meaningful (the brand had no asset, so the block is off) and a naive deep
 * merge would resurrect it from the defaults.
 */

export const DEFAULT_CAPTIONS: Required<
  Pick<CaptionStyle, "mode" | "family" | "weight" | "case" | "tracking" | "lineHeight" | "align" | "safeArea">
> = {
  mode: "word-highlight",
  family: "dm-sans",
  weight: 700,
  case: "as-written",
  tracking: 0,
  lineHeight: 1.15,
  align: "center",
  safeArea: "reels",
};

/** Platform chrome covers roughly the bottom 250px of a 1920-tall frame;
 *  captions sit clear of it. Carried over from PortraitFull. */
export const SAFE_BOTTOM = 430;

export function withDefaults(style: ResolvedStyle | undefined): ResolvedStyle {
  const input = style ?? {};
  const captions = input.captions ?? {};
  const animation = captions.animation ?? {};

  return {
    ...input,
    captions: {
      ...DEFAULT_CAPTIONS,
      ...captions,
      size: {portrait: 58, landscape: 44, ...(captions.size ?? {})},
      colors: {idle: "#ffffff", active: "#ffffff", idleOpacity: 1, ...(captions.colors ?? {})},
      box: {enabled: false, radius: 0, padX: 0, padY: 0, scope: "line", ...(captions.box ?? {})},
      stroke: {width: 0, color: "#000000", ...(captions.stroke ?? {})},
      // Passed through untouched: it may be a list, and spreading defaults over
      // an array would turn it into an object with numeric keys.
      shadow: captions.shadow,
      anchor: {edge: "bottom", offset: SAFE_BOTTOM, insetX: 54, ...(captions.anchor ?? {})},
      animation: {
        preset: "none",
        activeScale: 1,
        ...animation,
        enter: {preset: "none", durationMs: 0, ...(animation.enter ?? {})},
        exit: {preset: "none", durationMs: 0, ...(animation.exit ?? {})},
      },
    },
    scrim: {
      top: {mode: "none", ...(input.scrim?.top ?? {})},
      bottom: {mode: "none", ...(input.scrim?.bottom ?? {})},
    },
    // Spread rather than deep-merged: a null block means "switched off", and a
    // deep merge would bring it back from the defaults.
    furniture: input.furniture ?? {},
    render: {canvas: "portrait", width: 1080, height: 1920, ...(input.render ?? {})},
  };
}

// applyCase moved to ./css, beside every other decision the style makes about
// how a word looks -- it is one of the numbers the editor's preview has to
// agree with. Re-exported so existing importers do not have to care.
export {applyCase} from "./css";
