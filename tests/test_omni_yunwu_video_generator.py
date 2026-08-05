import unittest
from unittest.mock import patch

from tools.video_generator_omni_yunwu_api import (
    VideoGeneratorOmniYunwuAPI,
    VideoGeneratorOminiYunwuAPI,
)


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return _FakeResponse(self.payload)


class TestVideoGeneratorOmniYunwuAPI(unittest.IsolatedAsyncioTestCase):
    def test_text_to_video_payload(self):
        generator = VideoGeneratorOmniYunwuAPI(api_key="test-key")

        payload = generator._build_payload(
            prompt="hello world",
            reference_image_paths=[],
            aspect_ratio="16:9",
            seconds=8,
            size=None,
            enable_upsample=False,
            enable_sample=None,
        )

        self.assertEqual(payload["model"], "omni-flash")
        self.assertEqual(payload["type"], 1)
        self.assertEqual(payload["seconds"], "8")
        self.assertEqual(payload["aspect_ratio"], "16:9")
        self.assertFalse(payload["enable_upsample"])
        self.assertNotIn("images", payload)

    def test_first_last_frame_payload(self):
        generator = VideoGeneratorOmniYunwuAPI(api_key="test-key")

        payload = generator._build_payload(
            prompt="transition",
            reference_image_paths=["https://example.com/first.png", "https://example.com/last.png"],
            aspect_ratio="9:16",
            seconds=6,
            size=None,
            enable_upsample=None,
            enable_sample=True,
        )

        self.assertEqual(payload["type"], 2)
        self.assertEqual(payload["images"], ["https://example.com/first.png", "https://example.com/last.png"])
        self.assertEqual(payload["seconds"], "6")
        self.assertTrue(payload["enable_sample"])

    def test_three_reference_images_use_reference_mode(self):
        generator = VideoGeneratorOmniYunwuAPI(api_key="test-key")

        payload = generator._build_payload(
            prompt="blend references",
            reference_image_paths=[
                "https://example.com/1.png",
                "https://example.com/2.png",
                "https://example.com/3.png",
            ],
            aspect_ratio="16:9",
            seconds=None,
            size=None,
            enable_upsample=None,
            enable_sample=None,
        )

        self.assertEqual(payload["type"], 3)
        self.assertEqual(len(payload["images"]), 3)

    def test_too_many_reference_images_raise(self):
        generator = VideoGeneratorOmniYunwuAPI(api_key="test-key")

        with self.assertRaises(ValueError):
            generator._build_payload(
                prompt="too many",
                reference_image_paths=["1", "2", "3", "4"],
                aspect_ratio="16:9",
                seconds=None,
                size=None,
                enable_upsample=None,
                enable_sample=None,
            )

    async def test_query_completed_uses_top_level_video_url(self):
        generator = VideoGeneratorOmniYunwuAPI(api_key="test-key", poll_interval=0, max_poll_attempts=1)
        session = _FakeSession({"status": "completed", "video_url": "https://example.com/out.mp4"})

        with patch("tools.video_generator_omni_yunwu_api.aiohttp.ClientSession", return_value=session):
            video_url = await generator.query_video_generation_task("task-1", "omni-flash")

        self.assertEqual(video_url, "https://example.com/out.mp4")
        self.assertEqual(session.calls[0][2]["params"], {"id": "task-1", "model": "omni-flash"})

    async def test_query_failed_raises(self):
        generator = VideoGeneratorOmniYunwuAPI(api_key="test-key", poll_interval=0, max_poll_attempts=1)
        session = _FakeSession({"status": "failed", "error": "视频生成失败"})

        with patch("tools.video_generator_omni_yunwu_api.aiohttp.ClientSession", return_value=session):
            with self.assertRaises(RuntimeError):
                await generator.query_video_generation_task("task-1", "omni-flash")

    def test_omini_alias(self):
        self.assertTrue(issubclass(VideoGeneratorOminiYunwuAPI, VideoGeneratorOmniYunwuAPI))


if __name__ == "__main__":
    unittest.main()
