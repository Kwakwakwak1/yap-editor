import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";

import {
  applyCase,
  captionAnchorStyle,
  captionLineBoxStyle,
  captionWordStyle,
} from "../style/css";
import type {CaptionStyle} from "../style/types";
import type {Caption} from "../types";

/**
 * Split a cue into words with ESTIMATED start times.
 *
 * Fallback only. assemble.py writes measured per-word timings into
 * `caption.words`; this exists for props staged before that field, and for
 * hand-written props.
 *
 * Measured against the real sample, the estimate is wrong by up to 373ms --
 * 11.2 frames at 30fps -- so it is genuinely a last resort, not a peer.
 * Character length is not a proxy for spoken duration: "why" is short and drawn
 * out, "every" is long and fast.
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

function wordsFor(caption: Caption) {
  if (caption.words && caption.words.length > 0) {
    return caption.words.map((w) => ({word: w.text, start: w.from, end: w.to}));
  }
  return estimatedWords(caption);
}

export const Captions: React.FC<{captions: Caption[]; style: CaptionStyle}> = ({
  captions,
  style,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const time = frame / fps;

  if (style.mode === "off") return null;

  const active = captions.find((cue) => time >= cue.from && time <= cue.to);
  if (!active) return null;

  // Four interpolation stops must be strictly increasing or interpolate throws,
  // which is why a very short cue skips the fade entirely rather than being
  // clamped into a degenerate range.
  let cueOpacity = 1;
  if (active.to - active.from > 0.2) {
    cueOpacity = interpolate(
      time,
      [active.from, active.from + 0.08, active.to - 0.05, active.to],
      [0, 1, 1, 0],
      {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
    );
  }

  const words = wordsFor(active);
  const lineBox = captionLineBoxStyle(style);

  // Every number below comes from ../style/css. This component decides WHICH
  // word is active and nothing else about how it looks -- the editor in
  // socialmedia-web draws the same words from the same functions, so a preview
  // cannot quietly disagree with a render.
  const rendered = words.map(({word, start, end}, index) => (
    <span
      key={`${start}-${index}`}
      style={captionWordStyle(style, {
        // The active word carries the accent; inactive words stay legible
        // rather than dimming away, so the line remains readable as a line.
        isActive: time >= start && time < end,
        isLast: index === words.length - 1,
      })}
    >
      {applyCase(word, style.case, index === 0)}
    </span>
  ));

  return (
    <div style={{...captionAnchorStyle(style), opacity: cueOpacity}}>
      {lineBox ? <span style={lineBox}>{rendered}</span> : rendered}
    </div>
  );
};
