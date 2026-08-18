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
}> = ({clip, muted, width, height, fit}) => {
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
          }}
        />
      </div>
    );
  }

  return (
    <OffthreadVideo
      src={staticFile(clip)}
      muted={muted}
      style={{width, height, objectFit: "cover", display: "block"}}
    />
  );
};
