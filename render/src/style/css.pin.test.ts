import {createHash} from "node:crypto";
import {readFileSync} from "node:fs";
import {join} from "node:path";

import {describe, expect, it} from "vitest";

/**
 * css.ts is vendored into socialmedia-web, which pins the same digest.
 *
 * Editing it therefore has to be a deliberate act with a visible diff, exactly
 * as re-vendoring style-pack.schema.json into the API is -- otherwise the
 * editor's preview and the render drift apart silently, which is the failure
 * mode this whole arrangement exists to prevent.
 *
 * If this fails: copy src/style/css.ts to socialmedia-web's src/lib/style-css.ts,
 * update STYLE_CSS_SHA256 on both sides, and check the editor still looks like
 * the render.
 */
describe("the vendored style CSS", () => {
  it("has not changed without the copy in socialmedia-web changing too", () => {
    const source = readFileSync(join(__dirname, "css.ts"));
    expect(createHash("sha256").update(source).digest("hex")).toBe(
      "826eaf28815f14c444ceec81fb2a83160fc510b8ad5fe864272e241bd921360f",
    );
  });
});
