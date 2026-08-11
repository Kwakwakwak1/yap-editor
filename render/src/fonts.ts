import {DM_SANS_WOFF2} from "./assets/dmsans";

/**
 * DM Sans (SIL OFL, licence in public/fonts/OFL.txt) is inlined as a data URI in
 * ./assets/dmsans.ts and registered with a plain @font-face rule.
 *
 * There is deliberately no delayRender() here. Every version of this file that
 * held a render handle open until the font settled eventually killed a cold-clone
 * render, because a handle that never clears is fatal while a font that never
 * loads is merely ugly:
 *
 *   @remotion/fonts, served from public/   died at frame 258 of 528 (28s timeout)
 *   hand-rolled FontFace, 120s timeout     died at frame 518
 *   hand-rolled FontFace, data URI, 30s    died at frame 204
 *
 * The font is a data URI, so there is no request to wait on and nothing to
 * starve: the bytes are already in the bundle when the style rule is parsed.
 * font-display: swap guarantees text is painted either way, so the worst case is
 * a fallback glyph rather than a dead render or an empty frame.
 */

export const fontFamily = '"DM Sans", Arial, Helvetica, sans-serif';

const STYLE_ID = "dm-sans-face";

if (typeof document !== "undefined" && !document.getElementById(STYLE_ID)) {
  const style = document.createElement("style");
  style.id = STYLE_ID;
  // DM Sans is variable; the weight range keeps real weights instead of faux bold.
  style.textContent = [
    "@font-face{",
    'font-family:"DM Sans";',
    `src:url(${DM_SANS_WOFF2}) format("woff2");`,
    "font-weight:100 1000;",
    "font-style:normal;",
    "font-display:swap;",
    "}",
  ].join("");
  document.head.appendChild(style);
}
