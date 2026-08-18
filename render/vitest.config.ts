import {defineConfig} from "vitest/config";

export default defineConfig({
  test: {
    // jsdom is deliberately NOT used. These cover the pure style functions --
    // case rules, defaults merging, word-timing selection -- which need no DOM
    // and are the parts a render is an expensive way to check.
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
