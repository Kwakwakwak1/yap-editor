# Landscape on black renderer

This is a standalone Remotion app. From the repository root:

```bash
cd render
npm install
npm run studio
```

The sample clip is staged by `pipeline/assemble.py`. To render it directly with
the staged props:

```bash
npx remotion render src/index.ts LandscapeOnBlack ../out/sample-reel.mp4 \
  --props=public/reels/sample/props.json
```

The renderer loads the bundled DM Sans variable font from `public/fonts`, so
rendering does not need a network font request.

## Geometry

| Element | Value |
| --- | ---: |
| Canvas | 1080 x 1920 |
| Video band | 1080 x 608 |
| Video band share | 31.7% of frame height |
| Video top | 656 |
| Headline | persistent, centered in the top black bar |
| Captions | lowercase, inside the video band at 60% of its height |
