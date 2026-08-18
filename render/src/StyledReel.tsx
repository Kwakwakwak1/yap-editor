import React from "react";
import {AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig} from "remotion";

import {Captions} from "./layers/Captions";
import {Footage} from "./layers/Footage";
import {Headline} from "./layers/Headline";
import {LogoBug} from "./layers/LogoBug";
import {Scrim} from "./layers/Scrim";
import {originFor, scaleAt} from "./layers/zoom";
import {withDefaults} from "./style/defaults";
import type {StyledReelProps} from "./types";

/**
 * One composition, driven by a resolved style spec.
 *
 * This replaces the two hardcoded compositions. Ten styles cannot mean ten more
 * .tsx files, and the composition was never the right axis anyway: PortraitFull
 * and LandscapeOnBlack both render 1080x1920 and differ only in how the source
 * sits inside that frame. What looked like two templates was one template and
 * two fits.
 *
 * The spec arrives already resolved -- every @token replaced with the brand's
 * real accent, a bundled font key, an asset URL -- so nothing here knows what a
 * brand is. `withDefaults` fills any field a older pack version omitted, so the
 * layers can read `style.captions.size.portrait` without guarding each access.
 *
 * Grade is deliberately NOT here: it belongs in ffmpeg, in assemble's existing
 * re-encode, rather than as a per-frame CSS filter in headless Chrome -- and
 * putting it there means the preview shows it too.
 *
 * Still to come: transitions, music and b-roll.
 */
export const StyledReel: React.FC<StyledReelProps> = (props) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const style = withDefaults(props.style);
  const width = style.render?.width ?? 1080;
  const height = style.render?.height ?? 1920;
  const canvas = style.render?.canvas ?? "portrait";
  const fit = props.sourceOrientation
    ? style.sourceFit?.[props.sourceOrientation]
    : style.sourceFit?.[canvas];

  const furniture = style.furniture ?? {};

  return (
    <AbsoluteFill style={{backgroundColor: "#000000"}}>
      <Footage
        clip={props.clip}
        muted={Boolean(props.audio)}
        width={width}
        height={height}
        fit={fit}
        scale={scaleAt(style, props.segments, frame / fps)}
        origin={originFor(style)}
      />
      {props.audio ? <Audio src={staticFile(props.audio)} /> : null}

      {/* Scrims sit above the footage and below every piece of text, which is
          the only ordering that makes them do their job. */}
      <Scrim edge="top" spec={style.scrim?.top} width={width} />
      <Scrim edge="bottom" spec={style.scrim?.bottom} width={width} />

      <Headline text={props.headline} spec={furniture.headline} width={width} />
      <Captions captions={props.captions} style={style.captions ?? {}} />
      <LogoBug spec={furniture.logoBug} />
    </AbsoluteFill>
  );
};
