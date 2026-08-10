import {continueRender, delayRender, staticFile} from "remotion";

/**
 * DM Sans is bundled in public/fonts (SIL OFL, licence alongside it), so a render
 * never depends on the network.
 *
 * The font is loaded by hand rather than through @remotion/fonts on purpose. That
 * helper opens a delayRender() handle that is only cleared when the FontFace
 * resolves, so a font that is slow or fails takes the whole render with it. At the
 * default concurrency the font request competes with the OffthreadVideo frame
 * server, and a starved request killed a 528-frame render at frame 258 with
 * "delayRender() was called but not cleared after 28000ms".
 *
 * Here the handle is always released: on success, on failure, and on timeout. A
 * font problem costs you DM Sans and falls back to the system stack. It does not
 * cost you the render.
 */

export const fontFamily = '"DM Sans", Arial, Helvetica, sans-serif';

const handle = delayRender("Loading DM Sans", {timeoutInMilliseconds: 120000});

const face = new FontFace(
  "DM Sans",
  `url(${staticFile("fonts/DMSans-Variable.woff2")}) format("woff2")`,
  // DM Sans is a variable font; the range keeps real weights instead of faux bold
  {weight: "100 1000"},
);

face
  .load()
  .then((loaded) => {
    document.fonts.add(loaded);
  })
  .catch((error) => {
    // eslint-disable-next-line no-console
    console.warn("DM Sans failed to load, falling back to the system stack:", error);
  })
  .finally(() => {
    continueRender(handle);
  });
