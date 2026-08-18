import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";

import {resolveFont} from "../fonts/registry";
import {applyCase} from "../style/defaults";
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

/** Where the caption block sits, from the style's anchor. */
function anchorStyle(captions: CaptionStyle): React.CSSProperties {
  const anchor = captions.anchor ?? {};
  const offset = typeof anchor.offset === "number" ? anchor.offset : (anchor.offset?.[1] ?? 0);
  const insetX = anchor.insetX ?? 54;
  const base: React.CSSProperties = {
    position: "absolute",
    left: insetX,
    right: insetX,
    textAlign: captions.align,
    pointerEvents: "none",
  };
  return anchor.edge === "top" ? {...base, top: offset} : {...base, bottom: offset};
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

  const size = (style.size?.portrait ?? 58) as number;
  const family = resolveFont(style.family);
  const words = wordsFor(active);
  const highlight = style.mode === "word-highlight";
  const box = style.box ?? {};
  // Layered back to front: a wide soft shadow lifts the glyph off the footage,
  // a tight dark one defines its edge. Rendering only the first was a visible
  // difference -- max channel delta 6 across the caption band -- when checked
  // against the treatment this app already shipped.
  const shadows = Array.isArray(style.shadow)
    ? style.shadow
    : style.shadow
      ? [style.shadow]
      : [];
  const shadowParts = shadows
    .filter((s) => (s.blur ?? 0) > 0 || (s.y ?? 0) !== 0)
    .map((s) => `0 ${s.y ?? 0}px ${s.blur ?? 0}px ${s.color}`);

  return (
    <div style={{...anchorStyle(style), opacity: cueOpacity}}>
      {words.map(({word, start, end}, index) => {
        const isActive = highlight && time >= start && time < end;
        // The active word carries the accent; inactive words stay legible
        // rather than dimming away, so the line remains readable as a line.
        const colour = isActive ? style.colors?.active : style.colors?.idle;
        const opacity = isActive || !highlight ? 1 : (style.colors?.idleOpacity ?? 1);

        // Scale is applied per word, and only ever to the active one, so an
        // un-animated style renders identical geometry to no animation at all.
        const scale =
          isActive && (style.animation?.activeScale ?? 1) !== 1
            ? style.animation!.activeScale!
            : 1;

        const boxed = box.enabled && (box.scope === "line" || isActive);

        return (
          <span
            key={`${start}-${index}`}
            style={{
              fontFamily: family,
              fontSize: size,
              fontWeight: style.weight,
              color: colour,
              opacity,
              lineHeight: style.lineHeight,
              letterSpacing: `${(style.tracking ?? 0) * size}px`,
              textShadow: shadowParts.join(", ") || undefined,
              WebkitTextStrokeWidth: style.stroke?.width || undefined,
              WebkitTextStrokeColor: style.stroke?.width ? style.stroke.color : undefined,
              backgroundColor: boxed ? box.fill : undefined,
              borderRadius: boxed ? box.radius : undefined,
              padding: boxed ? `${box.padY}px ${box.padX}px` : undefined,
              marginRight: 14,
              display: "inline-block",
              transform: scale === 1 ? undefined : `scale(${scale})`,
            }}
          >
            {applyCase(word, style.case)}
          </span>
        );
      })}
    </div>
  );
};
