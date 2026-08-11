import {Config} from "@remotion/cli/config";

// PNG frames, not JPEG. With jpeg the encoder marks the stream full-range and
// ffprobe reports yuvj420p, which no --pixel-format flag overrides. Some players
// shift contrast on full-range h264, and this repo's rule is that every output is
// yuv420p, so the slower-but-correct frame format wins.
Config.setVideoImageFormat("png");
Config.setCodec("h264");
Config.setPixelFormat("yuv420p");
