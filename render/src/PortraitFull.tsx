// Full-bleed 9:16 variant: the take already fills the reel frame, so there is no
// band and no letterboxing. Headline and captions sit directly over the video,
// each behind a gradient scrim because — unlike LandscapeOnBlack — there is no
// black background to guarantee contrast.
//
// The caption timing logic is duplicated from LandscapeOnBlack rather than
// factored out on purpose: this file is a local addition to an upstream
// checkout, and keeping it self-contained means only Root.tsx has to be merged
// when pulling upstream changes.

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
export const TEMPLATE_DIMS = {width: W, height: H};

export const PortraitFull: React.FC<LandscapeProps> = ({
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
  // At or below 0.2s the four interpolation stops are not strictly increasing
  // and interpolate throws, so opacity stays at 1.

  return (
    <AbsoluteFill style={{backgroundColor: "#000000", fontFamily}}>
      <OffthreadVideo
        src={staticFile(clip)}
        muted={Boolean(audio)}
        style={{width: W, height: H, objectFit: "cover", display: "block"}}
      />
      {audio ? <Audio src={staticFile(audio)} /> : null}

      {/* Scrim so the headline stays legible over a bright frame. */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: W,
          height: 380,
          background: "linear-gradient(to bottom, rgba(0,0,0,0.72), rgba(0,0,0,0))",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 96,
          left: 60,
          right: 60,
          textAlign: "center",
          fontSize: 62,
          fontWeight: 700,
          color: "#ffffff",
          lineHeight: 1.16,
          letterSpacing: -1,
          textShadow: "0 2px 12px rgba(0,0,0,0.6)",
        }}
      >
        {headline}
      </div>

      {/* Scrim under the captions, in the lower third. */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          width: W,
          height: 620,
          background: "linear-gradient(to top, rgba(0,0,0,0.78), rgba(0,0,0,0))",
          pointerEvents: "none",
        }}
      />
      {activeCaption ? (
        <div
          style={{
            position: "absolute",
            left: 54,
            right: 54,
            bottom: 300,
            textAlign: "center",
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
    </AbsoluteFill>
  );
};
