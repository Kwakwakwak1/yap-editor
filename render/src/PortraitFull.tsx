// Full-bleed 9:16 variant: the take already fills the reel frame, so there is no
// band and no letterboxing.
//
// Three things differ from LandscapeOnBlack beyond the framing:
//
//   1. The headline is optional. Full-bleed footage rarely needs a second title
//      competing with the captions, so an empty headline renders nothing at all.
//   2. Captions highlight the active word, using the measured per-word timings
//      that assemble.py now writes into `captions[].words`. Props that predate
//      that field fall back to estimating word times from character length; see
//      `estimatedWords` for why that fallback is a last resort and not a peer.
//   3. Captions sit clear of the platform's own chrome. Instagram and TikTok
//      overlay the bottom ~250px of a 1920-tall frame with progress bar, handle,
//      and buttons; anything below SAFE_BOTTOM risks being covered.
//
// Caption timing logic is duplicated from LandscapeOnBlack rather than factored
// out on purpose: this file is a local addition to an upstream checkout, and
// keeping it self-contained means only Root.tsx has to be merged when pulling.

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
import {Caption, LandscapeProps} from "./types";

export const W = 1080;
export const H = 1920;
export const TEMPLATE_DIMS = {width: W, height: H};

/** Platform chrome occupies roughly the bottom 250px; keep text above it. */
const SAFE_BOTTOM = 430;

type PortraitProps = LandscapeProps & {
  /** Colour for the active caption word. Falls back to plain white. */
  accent?: string;
};

/**
 * Split a cue into words with estimated start times, weighting each word by its
 * length. Whitespace is preserved by returning words and rendering with gaps.
 *
 * FALLBACK ONLY. This exists for props staged before `captions[].words` existed
 * and for hand-written props; `wordsFor` prefers the measured timings.
 *
 * An earlier version of this comment claimed the drift was "well under a frame
 * or two and never accumulates across cues". That was measured against the real
 * sample and is false: the worst per-word error is ~370ms, or 11 frames at
 * 30fps. Character length is simply not a proxy for how long a word is spoken —
 * "why" is short and drawn out, "every" is long and fast. The estimate does not
 * accumulate *across* cues, because each cue re-anchors to its own `from`, but
 * within a cue it is more than enough to highlight the wrong word.
 */
function estimatedWords(caption: Caption) {
  const words = caption.text.split(/\s+/).filter(Boolean);
  const span = Math.max(caption.to - caption.from, 0.001);
  const totalWeight = words.reduce((sum, w) => sum + w.length + 1, 0);
  let elapsed = 0;
  return words.map((word) => {
    const share = ((word.length + 1) / totalWeight) * span;
    const start = caption.from + elapsed;
    elapsed += share;
    return {word, start, end: caption.from + elapsed};
  });
}

/** Measured word timings when the pipeline supplied them, else the estimate. */
function wordsFor(caption: Caption) {
  if (caption.words && caption.words.length > 0) {
    return caption.words.map((word) => ({
      word: word.text,
      start: word.from,
      end: word.to,
    }));
  }
  return estimatedWords(caption);
}

export const PortraitFull: React.FC<PortraitProps> = ({
  clip,
  audio,
  headline,
  captions,
  accent,
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

      {headline ? (
        <>
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
        </>
      ) : null}

      {/* Scrim under the captions, sized to sit above the platform chrome. */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          width: W,
          height: SAFE_BOTTOM + 320,
          background: "linear-gradient(to top, rgba(0,0,0,0.72), rgba(0,0,0,0))",
          pointerEvents: "none",
        }}
      />
      {activeCaption ? (
        <div
          style={{
            position: "absolute",
            left: 54,
            right: 54,
            bottom: SAFE_BOTTOM,
            textAlign: "center",
            opacity: captionOpacity,
            pointerEvents: "none",
          }}
        >
          {wordsFor(activeCaption).map(({word, start, end}, i) => {
            const isActive = time >= start && time < end;
            return (
              <span
                key={`${start}-${i}`}
                style={{
                  fontSize: 58,
                  fontWeight: 700,
                  // Inactive words stay legible rather than dimming away; the
                  // active word is picked out by colour, not by contrast.
                  color: isActive && accent ? accent : "#ffffff",
                  opacity: isActive || !accent ? 1 : 0.82,
                  lineHeight: 1.14,
                  letterSpacing: -0.5,
                  textShadow: "0 2px 10px rgba(0,0,0,0.55), 0 1px 3px rgba(0,0,0,0.7)",
                  marginRight: 14,
                  display: "inline-block",
                }}
              >
                {word.toLowerCase()}
              </span>
            );
          })}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
