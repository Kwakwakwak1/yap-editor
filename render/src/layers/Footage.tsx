import React from "react";
import {OffthreadVideo, staticFile} from "remotion";

/**
 * The cut itself.
 *
 * `fit` comes from the SOURCE's orientation, not the canvas: portrait footage
 * fills a portrait frame, and landscape footage is shown as a band rather than
 * being cropped to a strip of somebody's face.
 */
export const Footage: React.FC<{
  clip: string;
  muted: boolean;
  width: number;
  height: number;
  fit?: string;
  /** 1 means no transform at all -- not a scale(1), which would still hand the
   *  frame to the compositor and can shift sub-pixel sampling. */
  scale?: number;
  origin?: string;
  /** Extra CSS from a transition. Empty when nothing is happening, so an
   *  un-punctuated style adds no properties at all. */
  transition?: React.CSSProperties;
}> = ({clip, muted, width, height, fit, scale = 1, origin = "50% 50%", transition}) => {
  const zoom =
    scale === 1
      ? undefined
      : {transform: `scale(${scale})`, transformOrigin: origin};

  if (fit === "letterbox-blur" || fit === "contain") {
    // 16:9 inside 9:16, centred, matching LandscapeOnBlack's geometry.
    const bandHeight = Math.round((width / 16) * 9);
    return (
      <div style={{position: "absolute", inset: 0, backgroundColor: "#000000"}}>
        <OffthreadVideo
          src={staticFile(clip)}
          muted={muted}
          style={{
            position: "absolute",
            top: Math.round((height - bandHeight) / 2),
            width,
            height: bandHeight,
            objectFit: "cover",
            display: "block",
            ...zoom,
            ...transition,
          }}
        />
      </div>
    );
  }

  return (
    <OffthreadVideo
      src={staticFile(clip)}
      muted={muted}
      style={{width, height, objectFit: "cover", display: "block", ...zoom, ...transition}}
    />
  );
};
