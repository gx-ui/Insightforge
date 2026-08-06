
import logging
import asyncio
from PIL import Image
from typing import List, Optional
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential
from interfaces.image_output import ImageOutput
from tools.image_orientation import ensure_not_portrait, landscape_guard_requested
from tools.image_response import image_from_response_part
from utils.retry import after_func
from utils.rate_limiter import RateLimiter


class ImageGeneratorNanobananaGoogleAPI:
    def __init__(
        self,
        api_key: str,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.model = "gemini-2.5-flash-image"
        self.rate_limiter = rate_limiter
        self.client = genai.Client(
            api_key=api_key,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), after=after_func, reraise=True)
    async def generate_single_image(
        self,
        prompt: str,
        reference_image_paths: List[str] = [],
        aspect_ratio: Optional[str] = "16:9",
        **kwargs,
    ) -> ImageOutput:

        """
            aspect_ratio: 图片的宽高比。
        """

        logging.info(f"正在调用 {self.model} 生成图片...")

        # 若配置了速率限制则应用
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        reference_images = [Image.open(path) for path in reference_image_paths]

        # 速率限制错误的重试逻辑
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=reference_images + [prompt],
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(
                            aspect_ratio=aspect_ratio,
                        ),
                    ),
                )
                break
            except ClientError as e:
                if e.status_code == 429 and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logging.warning(f"触发速率限制 (429)，{wait_time} 秒后重试...（第 {attempt + 1}/{max_retries} 次尝试）")
                    await asyncio.sleep(wait_time)
                else:
                    raise

        image = None
        text = ""
        for part in response.candidates[0].content.parts:
            if part.text is not None:
                text += part.text
            elif part.inline_data is not None:
                image = image_from_response_part(part)

        if image is None:
            logging.error(f"未生成图片。响应文本为: {text}")
            raise ValueError("未生成图片")

        if landscape_guard_requested(
            size=kwargs.get("size"),
            aspect_ratio=aspect_ratio,
            enforce_landscape=kwargs.get("enforce_landscape", True),
            allow_portrait=kwargs.get("allow_portrait", False),
        ):
            ensure_not_portrait(image)

        return ImageOutput(fmt="pil", ext="png", data=image)