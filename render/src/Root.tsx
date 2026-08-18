import React from "react";
import {Composition} from "remotion";

import {LandscapeOnBlack} from "./LandscapeOnBlack";
import {PortraitFull} from "./PortraitFull";
import {StyledReel} from "./StyledReel";
import {LandscapeProps} from "./types";

const defaultProps: LandscapeProps = {
  clip: "reels/sample/clip.mp4",
  headline: "the edit is not the hard part",
  captions: [
    {from: 0.0, to: 0.8, text: "Why does every edit take 3 hours"},
    {from: 0.8, to: 1.7, text: "when the talking part took 90 seconds?"},
  ],
  durationInSeconds: 17.61,
  fps: 30,
};

const calculateMetadata = ({props}: {props: LandscapeProps}) => {
  const fps = props.fps ?? 30;
  const durationInSeconds = props.durationInSeconds ?? 10;
  return {
    fps,
    durationInFrames: Math.max(1, Math.round(durationInSeconds * fps)),
  };
};

export const Root: React.FC = () => {
  return (
    <>
      <Composition<any, LandscapeProps>
        id="LandscapeOnBlack"
        component={LandscapeOnBlack}
        width={1080}
        height={1920}
        fps={30}
        durationInFrames={Math.round((defaultProps.durationInSeconds ?? 10) * 30)}
        defaultProps={defaultProps}
        calculateMetadata={calculateMetadata}
      />
      {/* The parametric composition. The two above are kept until the legacy
          packs are proven frame-identical against them, and are then dead. */}
      <Composition<any, LandscapeProps>
        id="StyledReel"
        component={StyledReel as never}
        width={1080}
        height={1920}
        fps={30}
        durationInFrames={Math.round((defaultProps.durationInSeconds ?? 10) * 30)}
        defaultProps={defaultProps}
        calculateMetadata={calculateMetadata}
      />
      {/* Local addition: full-bleed variant for takes shot vertically. */}
      <Composition<any, LandscapeProps>
        id="PortraitFull"
        component={PortraitFull}
        width={1080}
        height={1920}
        fps={30}
        durationInFrames={Math.round((defaultProps.durationInSeconds ?? 10) * 30)}
        defaultProps={defaultProps}
        calculateMetadata={calculateMetadata}
      />
    </>
  );
};
