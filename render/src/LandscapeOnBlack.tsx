// Geometry measured from the reference reel's frames: 31.7% band, persistent
// headline, and lowercase lower-third captions.

import React from "react";
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import {fontFamily} from "./fonts";
import {LandscapeProps} from "./types";

export const W = 1080;
export const H = 1920;
export const VID_W = W;
export const VID_H = Math.round((W / 16) * 9);
export const VID_TOP = Math.round((H - VID_H) / 2);
export const TEMPLATE_DIMS = {width: W, height: H};

export const LandscapeOnBlack: React.FC<LandscapeProps> = ({
  clip,
  audio,
  headline,
  captions,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const time = frame / fps;
  const activeCaption = captions.find((caption) => time >= caption.from && time <= caption.to);

  let captionOpacity = 1;
  if (activeCaption && activeCaption.to - activeCaption.from > 0.2) {
    captionOpacity = interpolate(
      time,
      [activeCaption.from, activeCaption.from + 0.08, activeCaption.to - 0.05, activeCaption.to],
      [0, 1, 1, 0],
      {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
    );
  }
  // For cues at or below 0.2s, four strictly-increasing interpolation stops do
  // not exist in the window and interpolate throws, so opacity stays at 1.

  return (
    <AbsoluteFill style={{backgroundColor: "#000000", fontFamily}}>
      <div
        style={{
          position: "absolute",
          top: VID_TOP,
          left: 0,
          width: VID_W,
          height: VID_H,
          overflow: "hidden",
        }}
      >
        <OffthreadVideo
          src={staticFile(clip)}
          muted={Boolean(audio)}
          style={{
            width: VID_W,
            height: VID_H,
            objectFit: "cover",
            display: "block",
          }}
        />
        {audio ? <Audio src={staticFile(audio)} /> : null}
        {activeCaption ? (
          <div
            style={{
              position: "absolute",
              left: 54,
              right: 54,
              top: Math.round(VID_H * 0.6),
              pointerEvents: "none",
            }}
          >
            <span
              style={{
                opacity: captionOpacity,
                fontSize: 58,
                fontWeight: 700,
                color: "#ffffff",
                lineHeight: 1.14,
                letterSpacing: -0.5,
                display: "inline",
                textShadow: "0 2px 10px rgba(0,0,0,0.55), 0 1px 3px rgba(0,0,0,0.7)",
              }}
            >
              {activeCaption.text.toLowerCase()}
            </span>
          </div>
        ) : null}
      </div>
      <div
        style={{
          position: "absolute",
          left: 60,
          right: 60,
          bottom: H - VID_TOP + 26,
          textAlign: "center",
          fontSize: 62,
          fontWeight: 700,
          color: "#ffffff",
          lineHeight: 1.16,
          letterSpacing: -1,
        }}
      >
        {headline}
      </div>
    </AbsoluteFill>
  );
};
