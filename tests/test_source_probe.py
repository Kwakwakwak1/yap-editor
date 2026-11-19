"""Orientation and dynamic range of a source take.

Phones store portrait video as 3840x2160 with rotation=-90 in the stream's side
data, so width and height alone report landscape for portrait footage. The
2026-11-19 take is exactly that. Getting it wrong frames the whole reel wrong.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from common import framing_from_probe, is_hdr_transfer, source_framing, video_transfer  # noqa: E402


def probe(width, height, rotation=None, codec_type="video"):
    stream = {"codec_type": codec_type, "width": width, "height": height}
    if rotation is not None:
        stream["side_data_list"] = [{"rotation": rotation}]
    return {"streams": [{"codec_type": "audio"}, stream]}


class FramingFromProbeTest(unittest.TestCase):
    def test_rotated_landscape_storage_is_portrait(self):
        self.assertEqual(framing_from_probe(probe(3840, 2160, -90)), "portrait")
        self.assertEqual(framing_from_probe(probe(3840, 2160, 90)), "portrait")
        self.assertEqual(framing_from_probe(probe(3840, 2160, 270)), "portrait")

    def test_unrotated_and_upside_down_keep_their_axes(self):
        self.assertEqual(framing_from_probe(probe(1920, 1080)), "landscape")
        self.assertEqual(framing_from_probe(probe(1920, 1080, 180)), "landscape")
        self.assertEqual(framing_from_probe(probe(1080, 1920)), "portrait")

    def test_no_video_stream_is_an_error(self):
        with self.assertRaises(ValueError):
            framing_from_probe({"streams": [{"codec_type": "audio"}]})


class HdrTransferTest(unittest.TestCase):
    def test_hlg_and_pq_are_hdr(self):
        self.assertTrue(is_hdr_transfer("arib-std-b67"))
        self.assertTrue(is_hdr_transfer("smpte2084"))

    def test_sdr_and_unknown_are_not(self):
        for value in ("bt709", "", "unknown", "smpte170m"):
            self.assertFalse(is_hdr_transfer(value), value)


class OnRealFilesTest(unittest.TestCase):
    """The ffprobe wiring, on files ffmpeg makes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, name, extra_args):
        out = self.dir / name
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=d=0.5:s=64x36:r=30",
             *extra_args, str(out)],
            check=True,
        )
        return out

    def test_a_rotated_file_reads_as_portrait(self):
        plain = self.make("plain.mp4", ["-c:v", "libx264"])
        rotated = self.dir / "rotated.mp4"
        # Tag a display rotation without re-encoding. On ffmpeg 8.1 this is an
        # INPUT option (before -i): `-display_rotation:v:0 90`. Placed after -i
        # ffmpeg rejects it as an input option applied to an output. It writes
        # side data rotation=90 (counter-clockwise), which ffprobe reports via
        # stream_side_data.
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-display_rotation:v:0", "90", "-i", str(plain),
             "-c", "copy", str(rotated)],
            check=True,
        )
        self.assertEqual(source_framing(plain), "landscape")
        self.assertEqual(source_framing(rotated), "portrait")

    def test_transfer_is_read_from_the_stream(self):
        # `-color_trc` alone does not tag the stream on ffmpeg 8.1 with libx264;
        # the transfer has to go through x264's own params.
        sdr = self.make("sdr.mp4", ["-c:v", "libx264", "-x264-params", "transfer=bt709"])
        hlg = self.make("hlg.mp4", ["-c:v", "libx264", "-x264-params", "transfer=arib-std-b67"])
        self.assertEqual(video_transfer(sdr), "bt709")
        self.assertEqual(video_transfer(hlg), "arib-std-b67")
        self.assertFalse(is_hdr_transfer(video_transfer(sdr)))
        self.assertTrue(is_hdr_transfer(video_transfer(hlg)))
