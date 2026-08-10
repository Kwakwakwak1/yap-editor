export type Caption = {
  from: number;
  to: number;
  text: string;
};

export type LandscapeProps = {
  clip: string;
  audio?: string;
  headline: string;
  captions: Caption[];
  durationInSeconds?: number;
  fps?: number;
};
