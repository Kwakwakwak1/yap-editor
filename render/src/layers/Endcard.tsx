import React from "react";
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig} from "remotion";

import type {Endcard as EndcardSpec} from "../style/types";

/**
 * The brand card held after the last word.
 *
 * It is the one furniture block that changes the reel's LENGTH, which is why
 * `endcardSeconds` is shared with Root's calculateMetadata and mirrored by
 * verify_reel's expected-duration check. Draw it without extending the
 * composition and it silently overwrites the payoff instead of following it.
 */
export const Endcard: React.FC<{spec?: EndcardSpec | null; cutSeconds: number}> = ({
  spec,
  cutSeconds,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  if (!spec || !spec.asset || !spec.durationSeconds) return null;
  if (frame / fps < cutSeconds) return null;

  const source = /^https?:\/\//.test(spec.asset) ? spec.asset : staticFile(spec.asset);

  return (
    <AbsoluteFill style={{backgroundColor: spec.background ?? "#000000"}}>
      <Img
        src={source}
        style={{width: "100%", height: "100%", objectFit: spec.fit ?? "contain"}}
      />
    </AbsoluteFill>
  );
};
