import {ARCHIVO_WOFF2} from "../assets/archivo";
import {CAVEAT_WOFF2} from "../assets/caveat";
import {DM_SANS_WOFF2} from "../assets/dmsans";
import {INSTRUMENT_SERIF_WOFF2} from "../assets/instrumentserif";
import {INTER_WOFF2} from "../assets/inter";
import {SPACE_GROTESK_WOFF2} from "../assets/spacegrotesk";

/**
 * The bundled typeface registry.
 *
 * A style pack names a font by KEY, never by family name or URL. That is the
 * whole reason the catalog can be data: a pack the API accepts is one this
 * bundle can actually draw, checked at save time rather than discovered four
 * minutes into a render on minik with nobody watching.
 *
 * Every face is injected eagerly, at module load, unconditionally -- not per
 * style, not lazily, not behind delayRender(). The comment in ../fonts.ts
 * records three attempts that each killed a cold render:
 *
 *   @remotion/fonts, served from public/   died at frame 258 of 528 (28s timeout)
 *   hand-rolled FontFace, 120s timeout     died at frame 518
 *   hand-rolled FontFace, data URI, 30s    died at frame 204
 *
 * All three shared one shape: something waited. A data URI has nothing to wait
 * on -- the bytes are in the bundle when the rule is parsed -- and
 * `font-display: swap` means the worst case is a fallback glyph rather than a
 * dead render. Loading only the families a given style asks for would
 * reintroduce exactly the race those three died to, so every family is always
 * present even though most renders use one.
 */
export type FontKey =
  | "dm-sans"
  | "archivo"
  | "instrument-serif"
  | "inter"
  | "space-grotesk"
  | "caveat";

interface BundledFont {
  /** The CSS family name, plus a fallback stack for the swap window. */
  stack: string;
  /** Data URI. Undefined means "not bundled yet" -- see resolveFont. */
  woff2?: string;
  /** Variable fonts take a range; single-weight faces take one number. */
  weight: string;
}

export const FONT_REGISTRY: Record<FontKey, BundledFont> = {
  "dm-sans": {
    stack: '"DM Sans", Arial, Helvetica, sans-serif',
    woff2: DM_SANS_WOFF2,
    weight: "100 1000",
  },
  archivo: {
    stack: '"Archivo", "Arial Narrow", Impact, sans-serif',
    woff2: ARCHIVO_WOFF2,
    weight: "100 900",
  },
  "instrument-serif": {
    stack: '"Instrument Serif", Georgia, "Times New Roman", serif',
    woff2: INSTRUMENT_SERIF_WOFF2,
    // One weight. A pack asking for bold gets a synthetic bold from the
    // browser, which on a high-contrast serif looks smeared -- which is why
    // the packs using it specify weight 400.
    weight: "400",
  },
  inter: {stack: '"Inter", system-ui, sans-serif', woff2: INTER_WOFF2, weight: "100 900"},
  "space-grotesk": {
    stack: '"Space Grotesk", "SF Mono", monospace',
    woff2: SPACE_GROTESK_WOFF2,
    weight: "300 700",
  },
  caveat: {stack: '"Caveat", "Comic Sans MS", cursive', woff2: CAVEAT_WOFF2, weight: "400 700"},
};

const STYLE_ID = "style-pack-fonts";

/** Inject every bundled face once, at module load. */
function injectFaces(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById(STYLE_ID)) return;

  const rules: string[] = [];
  for (const font of Object.values(FONT_REGISTRY)) {
    if (!font.woff2) continue;
    const family = font.stack.split(",")[0].trim();
    rules.push(
      "@font-face{",
      `font-family:${family};`,
      `src:url(${font.woff2}) format("woff2");`,
      `font-weight:${font.weight};`,
      "font-style:normal;",
      "font-display:swap;",
      "}",
    );
  }
  if (rules.length === 0) return;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = rules.join("");
  document.head.appendChild(style);
}

injectFaces();

/**
 * A font key to a CSS font-family stack.
 *
 * An unknown key falls back to dm-sans rather than throwing. The API rejects
 * unbundled keys at save time, so reaching here with one means a pack was
 * written before a family existed -- and an uglier reel beats a dead render.
 */
export function resolveFont(key: string | undefined): string {
  const font = FONT_REGISTRY[key as FontKey];
  return (font ?? FONT_REGISTRY["dm-sans"]).stack;
}
