import React from "react";
import {interpolate, useCurrentFrame, useVideoConfig} from "remotion";

import {resolveFont} from "../fonts/registry";
import type {LowerThird as LowerThirdSpec} from "../style/types";

const FADE = 0.3;

/**
 * A name strap over the opening of the reel.
 *
 * `source` in the PACK is a dotted path -- "job.speaker" -- and the API
 * resolves it to `text` before the spec is frozen onto the job, exactly as it
 * resolves an @token to an asset URL. The renderer never resolves a path
 * itself; it draws what it was given, and draws nothing when the field came
 * back empty.
 */
export const LowerThird: React.FC<{spec?: LowerThirdSpec | null}> = ({spec}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  if (!spec || spec.enabled === false || !spec.text) return null;

  const [from = 1.0, to = 5.0] = spec.showSeconds ?? [];
  if (!(to > from)) return null;
  const time = frame / fps;
  if (time < from - FADE || time > to) return null;

  const opacity = interpolate(
    time,
    [from - FADE, from, to - FADE, to],
    [0, 1, 1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
  );
  if (opacity <= 0) return null;

  const size = spec.size ?? 34;
  const rule = spec.rule ?? {};

  return (
    <div
      style={{
        position: "absolute",
        left: 64,
        bottom: 560,
        maxWidth: 760,
        opacity,
        pointerEvents: "none",
      }}
    >
      {rule.width ? (
        <div
          style={{
            width: size * 1.8,
            height: rule.width,
            backgroundColor: rule.color ?? spec.color ?? "#ffffff",
            marginBottom: size * 0.42,
          }}
        />
      ) : null}
      <div
        style={{
          fontFamily: resolveFont(spec.family),
          fontSize: size,
          fontWeight: 600,
          lineHeight: 1.2,
          color: spec.color ?? "#ffffff",
          textShadow: "0 2px 10px rgba(0,0,0,0.55)",
        }}
      >
        {spec.text}
      </div>
    </div>
  );
};
