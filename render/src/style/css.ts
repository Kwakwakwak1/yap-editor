/**
 * Every layout decision a style makes, as plain CSS objects.
 *
 * VENDORED. socialmedia-web carries a byte-identical copy at
 * src/lib/style-css.ts so its style editor can draw a live preview, and both
 * sides pin the file's sha256 in a test. The same arrangement the API uses for
 * style-pack.schema.json, and for the same reason: a second implementation of
 * these numbers would drift, and this project's history is a list of drifts
 * that looked right and measured wrong -- a self-referential font variable, a
 * shadow layered once instead of twice, a vignette ten times too dark. None of
 * those were visible by looking.
 *
 * So: no React, no Remotion, no imports at all. Pure functions from a resolved
 * style to CSSProperties. The renderer's layers arrange them into a Remotion
 * tree; the editor arranges them into a DOM preview; neither owns the numbers.
 *
 * What is deliberately NOT here: the grade. It is an ffmpeg filtergraph applied
 * before the frame ever reaches a browser, so there is nothing for CSS to say
 * about it truthfully. The editor approximates it and labels the approximation.
 */

export interface CSSProperties {
  [key: string]: string | number | undefined;
}

/** The bundled roster, family stacks only -- the renderer holds the bytes. */
export const FONT_STACKS: Record<string, string> = {
  "dm-sans": '"DM Sans", Arial, Helvetica, sans-serif',
  archivo: '"Archivo", "Arial Narrow", Impact, sans-serif',
  "instrument-serif": '"Instrument Serif", Georgia, "Times New Roman", serif',
  inter: '"Inter", system-ui, sans-serif',
  "space-grotesk": '"Space Grotesk", "SF Mono", monospace',
  caveat: '"Caveat", "Comic Sans MS", cursive',
};

/**
 * A font key to a CSS font-family stack.
 *
 * An unknown key falls back to dm-sans rather than throwing. The API rejects
 * unbundled keys at save time, so reaching here with one means a pack written
 * before a family existed -- and an uglier reel beats a dead render.
 */
export function resolveFontStack(key: string | undefined): string {
  return FONT_STACKS[key ?? ""] ?? FONT_STACKS["dm-sans"];
}

/**
 * `case` applied to one word. `as-written` is the identity, and is the default,
 * so a style must opt in to shouting.
 *
 * `isFirst` exists because captions are rendered word by word -- each one is its
 * own element so the active one can be coloured and scaled. Sentence case
 * applied to every word in that loop produces Title Case: "Why Does Every Edit"
 * instead of "Why does every edit". Only the first word of a cue is capitalised.
 */
export function applyCase(text: string, textCase: string | undefined, isFirst = true): string {
  switch (textCase) {
    case "upper":
      return text.toUpperCase();
    case "lower":
      return text.toLowerCase();
    case "sentence":
      return isFirst ? text.charAt(0).toUpperCase() + text.slice(1) : text;
    default:
      return text;
  }
}

/**
 * A box fill at the opacity the style asked for.
 *
 * Applied to the COLOUR, not as a CSS `opacity` on the element -- that would
 * fade the text sitting on the box along with the box, which is the opposite of
 * what a scrim behind text is for.
 */
export function boxFill(fill: string | undefined, opacity: number | undefined): string | undefined {
  if (!fill) return undefined;
  if (opacity === undefined || opacity >= 1) return fill;
  const digits = fill.replace("#", "");
  if (!/^([0-9a-f]{3}|[0-9a-f]{6})$/i.test(digits)) return fill;
  const full = digits.length === 3 ? digits.split("").map((c) => c + c).join("") : digits;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${Math.max(opacity, 0)})`;
}

/** One number for the anchored edge, or [x, y]. */
function offsetPair(anchor: any, fallbackX: number, fallbackY: number): [number, number] {
  const offset = anchor?.offset;
  if (Array.isArray(offset)) return [offset[0] ?? fallbackX, offset[1] ?? fallbackY];
  return [anchor?.insetX ?? fallbackX, typeof offset === "number" ? offset : fallbackY];
}

/** Where the caption block sits, from the style's anchor. */
export function captionAnchorStyle(captions: any): CSSProperties {
  const anchor = captions?.anchor ?? {};
  const offset = typeof anchor.offset === "number" ? anchor.offset : (anchor.offset?.[1] ?? 0);
  const insetX = anchor.insetX ?? 54;
  const base: CSSProperties = {
    position: "absolute",
    left: insetX,
    right: insetX,
    textAlign: captions?.align,
    pointerEvents: "none",
  };
  return anchor.edge === "top" ? {...base, top: offset} : {...base, bottom: offset};
}

/** True when the box is one plate behind the line rather than one per word. */
export function isLineBoxed(captions: any): boolean {
  const box = captions?.box ?? {};
  return Boolean(box.enabled && box.scope === "line");
}

/**
 * The plate behind a whole caption line, or null.
 *
 * `display: inline` with box-decoration-break: clone is what gives a wrapped
 * caption a box per VISUAL line -- an inline-block would draw a single
 * rectangle around the ragged block, which reads as a card and is a different
 * design.
 */
export function captionLineBoxStyle(captions: any): CSSProperties | null {
  if (!isLineBoxed(captions)) return null;
  const box = captions.box;
  return {
    backgroundColor: boxFill(box.fill, box.opacity),
    borderRadius: box.radius,
    padding: `${box.padY}px ${box.padX}px`,
    boxDecorationBreak: "clone",
    WebkitBoxDecorationBreak: "clone",
  };
}

/** One word of a caption, in whichever state it is in right now. */
export function captionWordStyle(
  captions: any,
  state: {isActive: boolean; isLast: boolean},
): CSSProperties {
  const size = (captions?.size?.portrait ?? 58) as number;
  const highlight = captions?.mode === "word-highlight";
  const box = captions?.box ?? {};
  const isActive = state.isActive && highlight;

  const shadows = Array.isArray(captions?.shadow)
    ? captions.shadow
    : captions?.shadow
      ? [captions.shadow]
      : [];
  // Layered back to front: a wide soft shadow lifts the glyph off the footage,
  // a tight dark one defines its edge. Rendering only the first was a visible
  // difference -- max channel delta 6 across the caption band -- against the
  // treatment this app already shipped.
  const shadowParts = shadows
    .filter((s: any) => (s.blur ?? 0) > 0 || (s.y ?? 0) !== 0)
    .map((s: any) => `0 ${s.y ?? 0}px ${s.blur ?? 0}px ${s.color}`);

  // `line` scope draws ONE box behind the whole line, so it is not drawn here:
  // a background on each word gives a row of separate rectangles with gaps.
  const boxed = Boolean(box.enabled && box.scope !== "line" && isActive);

  // Scale is applied per word, and only ever to the active one, so an
  // un-animated style renders identical geometry to no animation at all.
  const scale =
    isActive && (captions?.animation?.activeScale ?? 1) !== 1
      ? captions.animation.activeScale
      : 1;

  return {
    fontFamily: resolveFontStack(captions?.family),
    fontSize: size,
    fontWeight: captions?.weight,
    color: isActive ? captions?.colors?.active : captions?.colors?.idle,
    opacity: isActive || !highlight ? 1 : (captions?.colors?.idleOpacity ?? 1),
    lineHeight: captions?.lineHeight,
    letterSpacing: `${(captions?.tracking ?? 0) * size}px`,
    textShadow: shadowParts.join(", ") || undefined,
    WebkitTextStrokeWidth: captions?.stroke?.width || undefined,
    WebkitTextStrokeColor: captions?.stroke?.width ? captions.stroke.color : undefined,
    backgroundColor: boxed ? boxFill(box.fill, box.opacity) : undefined,
    borderRadius: boxed ? box.radius : undefined,
    padding: boxed ? `${box.padY}px ${box.padX}px` : undefined,
    // Words are spaced by margin, not by a space character: a text node between
    // them inherits the WRAPPER's font size, not the caption's, and collapses
    // to a ~4px gap. The last word drops its margin only inside a line box,
    // where it would otherwise pad the right edge 14px further than the left.
    marginRight: isLineBoxed(captions) && state.isLast ? 0 : 14,
    display: "inline-block",
    transform: scale === 1 ? undefined : `scale(${scale})`,
  };
}

/**
 * The gradient behind the captions and the headline, or null.
 *
 * Its job is contrast: white text over arbitrary footage is unreadable without
 * something between them, and a scrim keeps the footage visible where a solid
 * bar would not.
 */
export function scrimStyle(edge: "top" | "bottom", spec: any, width: number): CSSProperties | null {
  if (!spec || spec.mode === "none" || !spec.height) return null;
  const direction = edge === "top" ? "to bottom" : "to top";
  return {
    position: "absolute",
    [edge]: 0,
    left: 0,
    width,
    height: spec.height,
    background:
      spec.mode === "solid"
        ? spec.from
        : `linear-gradient(${direction}, ${spec.from}, ${spec.to})`,
    pointerEvents: "none",
  };
}

/** The optional title over the opening of the reel. */
export function headlineStyle(spec: any, width: number, opacity: number): CSSProperties {
  const anchor = spec?.anchor ?? {};
  const offset = typeof anchor.offset === "number" ? anchor.offset : (anchor.offset?.[1] ?? 96);
  return {
    position: "absolute",
    [anchor.edge === "bottom" ? "bottom" : "top"]: offset,
    left: 60,
    right: 60,
    width: width - 120,
    textAlign: "center",
    fontFamily: resolveFontStack(spec?.family),
    fontSize: spec?.size ?? 62,
    fontWeight: spec?.weight ?? 700,
    color: spec?.color ?? "#ffffff",
    lineHeight: 1.16,
    letterSpacing: -1,
    textShadow: "0 2px 12px rgba(0,0,0,0.6)",
    opacity,
    pointerEvents: "none",
  };
}

/**
 * The numbered step badge.
 *
 * A pill rather than plain text: it sits over moving footage for the whole of a
 * step, and text alone becomes unreadable the moment the shot brightens.
 */
export function stepBadgeStyle(spec: any): CSSProperties {
  const anchor = spec?.anchor ?? {};
  const edge = anchor.edge ?? "top-left";
  const [insetX, insetY] = offsetPair(anchor, 64, 220);
  const size = spec?.size ?? 34;
  return {
    position: "absolute",
    [edge.startsWith("bottom") ? "bottom" : "top"]: insetY,
    left: insetX,
    display: "inline-flex",
    alignItems: "center",
    gap: size * 0.4,
    padding: `${size * 0.42}px ${size * 0.72}px`,
    borderRadius: size * 0.34,
    backgroundColor: "rgba(0,0,0,0.62)",
    // The hairline is what keeps the pill legible over a bright shot without
    // making the fill opaque enough to read as a graphic.
    boxShadow: `inset 0 0 0 1.5px ${spec?.color ?? "#ffffff"}`,
    fontFamily: resolveFontStack(spec?.family),
    fontSize: size,
    fontWeight: 700,
    letterSpacing: size * 0.02,
    color: spec?.color ?? "#ffffff",
    whiteSpace: "nowrap",
    pointerEvents: "none",
  };
}

/** The name strap: its container, its rule and its text. */
export function lowerThirdStyle(spec: any, opacity: number): CSSProperties {
  return {
    position: "absolute",
    left: 64,
    bottom: 560,
    maxWidth: 760,
    opacity,
    pointerEvents: "none",
  };
}

export function lowerThirdRuleStyle(spec: any): CSSProperties | null {
  const rule = spec?.rule ?? {};
  if (!rule.width) return null;
  const size = spec?.size ?? 34;
  return {
    width: size * 1.8,
    height: rule.width,
    backgroundColor: rule.color ?? spec?.color ?? "#ffffff",
    marginBottom: size * 0.42,
  };
}

export function lowerThirdTextStyle(spec: any): CSSProperties {
  return {
    fontFamily: resolveFontStack(spec?.family),
    fontSize: spec?.size ?? 34,
    fontWeight: 600,
    lineHeight: 1.2,
    color: spec?.color ?? "#ffffff",
    textShadow: "0 2px 10px rgba(0,0,0,0.55)",
  };
}

/** The brand mark in a corner. */
export function logoBugStyle(spec: any): CSSProperties {
  const [insetX = 44, insetY = 44] = spec?.inset ?? [];
  const corner = spec?.corner ?? "top-right";
  return {
    position: "absolute",
    ...(corner.startsWith("top") ? {top: insetY} : {bottom: insetY}),
    ...(corner.endsWith("left") ? {left: insetX} : {right: insetX}),
    width: spec?.size ?? 84,
    height: "auto",
    opacity: spec?.opacity ?? 1,
    pointerEvents: "none",
  };
}
