#!/usr/bin/env python3
"""Putting one proxy on R2 and reporting where it landed.

Run with:  python3 -m unittest discover -s tests

claim.py reads this script's stdout to learn the URL it stores on the job, so
the output contract is load-bearing: the URL, alone, and nothing else.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "review"))

from upload_proxy import public_url, upload  # noqa: E402


class FakeClient:
    def __init__(self):
        self.uploads = []

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):  # noqa: N803
        self.uploads.append((Filename, Bucket, Key, ExtraArgs))


SETTINGS = {
    "S3_BUCKET": "kwakbucket",
    "S3_KEY_PREFIX": "",
    "PUBLIC_BASE_URL": "https://reels.kwakwakwak.com",
}


class PublicUrl(unittest.TestCase):
    def test_joins_the_base_and_the_key(self):
        self.assertEqual(
            public_url("https://reels.kwakwakwak.com", "", "proxies/s/A.mp4"),
            "https://reels.kwakwakwak.com/proxies/s/A.mp4",
        )

    def test_tolerates_a_trailing_slash_on_the_base(self):
        self.assertEqual(
            public_url("https://reels.kwakwakwak.com/", "", "proxies/s/A.mp4"),
            "https://reels.kwakwakwak.com/proxies/s/A.mp4",
        )

    def test_includes_the_key_prefix_when_one_is_set(self):
        # S3_KEY_PREFIX is blank today and the reels worker depends on that --
        # but publish.py composes its URL ignoring the prefix, which is exactly
        # the bug the skill documents. This one does not.
        self.assertEqual(
            public_url("https://reels.kwakwakwak.com", "media", "proxies/s/A.mp4"),
            "https://reels.kwakwakwak.com/media/proxies/s/A.mp4",
        )


class Upload(unittest.TestCase):
    def test_uploads_at_the_key_it_was_given_and_returns_the_url(self):
        client = FakeClient()

        url = upload(Path("/tmp/A.proxy.mp4"), "proxies/s/A.mp4", SETTINGS, client=client)

        self.assertEqual(url, "https://reels.kwakwakwak.com/proxies/s/A.mp4")
        self.assertEqual(client.uploads[0][1], "kwakbucket")
        self.assertEqual(client.uploads[0][2], "proxies/s/A.mp4")

    def test_sends_a_video_content_type(self):
        # Without it the browser is handed application/octet-stream and will
        # download the proxy rather than play it, which makes the editor a
        # download button.
        client = FakeClient()

        upload(Path("/tmp/A.proxy.mp4"), "proxies/s/A.mp4", SETTINGS, client=client)

        self.assertEqual(client.uploads[0][3], {"ContentType": "video/mp4"})

    def test_puts_the_prefix_on_the_object_key_as_well_as_the_url(self):
        # Both, or neither. A URL carrying the prefix while the object landed
        # without it is the same 404 from the other direction.
        client = FakeClient()
        settings = dict(SETTINGS, S3_KEY_PREFIX="media")

        url = upload(Path("/tmp/A.proxy.mp4"), "proxies/s/A.mp4", settings, client=client)

        self.assertEqual(client.uploads[0][2], "media/proxies/s/A.mp4")
        self.assertEqual(url, "https://reels.kwakwakwak.com/media/proxies/s/A.mp4")


if __name__ == "__main__":
    unittest.main()
