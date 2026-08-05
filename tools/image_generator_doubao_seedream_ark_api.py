# -*- coding: utf-8 -*-
"""火山引擎官方 Ark API 图片生成器 (doubao-seedream)。

API 文档: https://www.volcengine.com/docs/6791/1347777

与云雾代理 (ImageGeneratorDoubaoSeedreamYunwuAPI) 使用完全相同的
payload/response 格式，唯一区别是 base_url 可配置且默认指向官方 Ark API。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, List, Optional

import aiohttp
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from interfaces.image_output import ImageOutput
from utils.image import image_path_to_b64
from utils.retry import after_func

_DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def _request_timeout_seconds() -> float:
    raw = os.environ.get("INSIGHTFORGE_IMAGE_REQUEST_TIMEOUT_SECONDS", "300")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 300.0


def _emit_progress(progress: Any, stage: str, message: str, metadata: dict | None = None) -> None:
    if progress is not None:
        progress(stage, message, metadata or {})


class ImageGeneratorDoubaoSeedreamArkAPI:
    """Generate images through the Volcano Engine Ark API (doubao-seedream).

    Uses the same payload/response format as the Yunwu proxy variant, but
    targets the official Ark API endpoint with a configurable *base_url*.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "doubao-seedream-3-0-t2i-250415",
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
        after=after_func,
    )
    async def generate_single_image(
        self,
        prompt: str,
        reference_image_paths: List[str] = [],
        size: Optional[str] = None,
        **kwargs: Any,
    ) -> ImageOutput:
        """Generate a single image from a text prompt and optional reference images.

        Args:
            prompt: Text prompt for image generation.
            reference_image_paths: List of reference image file paths.
            size: Image size, e.g. ``"1024x1024"`` or ``"4096x4096"``.
        """
        progress = kwargs.get("progress")
        _emit_progress(
            progress,
            "image_generation",
            f"Generating image with {self.model}",
            {"model": self.model, "reference_count": len(reference_image_paths)},
        )

        logging.info(f"Calling {self.model} to generate image...")

        images = [
            image_path_to_b64(path, mime=True) for path in reference_image_paths
        ]

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "response_format": "url",
            "size": size if size is not None else "1024x1024",
        }
        if images:
            payload["image"] = images

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/images/generations"
        timeout = aiohttp.ClientTimeout(total=_request_timeout_seconds())

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                response_json = await response.json()
                if response.status >= 400:
                    raise RuntimeError(
                        f"Ark image generation failed with HTTP {response.status}: {response_json}"
                    )

        data = response_json["data"][0]["url"]
        _emit_progress(
            progress,
            "image_completed",
            "Ark image generation completed",
            {"model": self.model},
        )
        return ImageOutput(fmt="url", ext="png", data=data)
