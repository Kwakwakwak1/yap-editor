import {continueRender, delayRender} from "remotion";

import {DM_SANS_WOFF2} from "./assets/dmsans";

/**
 * DM Sans (SIL OFL, licence in public/fonts/OFL.txt) is inlined as a data URI in
 * ./assets/dmsans.ts, so loading it involves no network and no server.
 *
 * That is not premature optimisation, it is the fix for a real failure. Loaded
 * from public/ through @remotion/fonts, the font is an HTTP request against the
 * same server that streams OffthreadVideo frames. At the default concurrency that
 * request can hang indefinitely rather than fail, and because the helper holds a
 * delayRender() handle until the FontFace settles, the hang takes the whole render
 * with it. Measured on a cold clone: the render died at frame 258 of 528 with a
 * 28s timeout, and raising the timeout to 120s only moved the death to frame 518.
 *
 * A data URI cannot be starved. The handle below is belt and braces: it is
 * released on success, on failure, and on timeout, so a font problem costs you
 * DM Sans and falls back to the system stack. It never costs you the render.
 */

export const fontFamily = '"DM Sans", Arial, Helvetica, sans-serif';

const handle = delayRender("Registering DM Sans", {timeoutInMilliseconds: 30000});

// DM Sans is variable; the weight range keeps real weights instead of faux bold.
const face = new FontFace("DM Sans", `url(${DM_SANS_WOFF2}) format("woff2")`, {
  weight: "100 1000",
});

face
  .load()
  .then((loaded) => {
    document.fonts.add(loaded);
  })
  .catch((error) => {
    // eslint-disable-next-line no-console
    console.warn("DM Sans failed to register, falling back to the system stack:", error);
  })
  .finally(() => {
    continueRender(handle);
  });
