import {loadFont} from "@remotion/fonts";
import {staticFile} from "remotion";

loadFont({
  family: "DM Sans",
  url: staticFile("fonts/DMSans-Variable.woff2"),
  weight: "100 1000",
});

export const fontFamily = '"DM Sans", Arial, Helvetica, sans-serif';
