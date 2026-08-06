import logging
from typing import List, Optional
import asyncio
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from interfaces.video_output import VideoOutput
from utils.rate_limiter import RateLimiter

# https://ai.google.dev/gemini-api/docs/video-generation?hl=zh-cn


class VideoGeneratorVeoGoogleAPI:
    def __init__(
        self,
        api_key: str,
        t2v_model: str = "veo-3.1-generate-preview",
        ff2v_model: str = "veo-3.1-generate-preview",
        flf2v_model: str = "veo-3.1-generate-preview",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.api_key = api_key
        self.t2v_model = t2v_model
        self.ff2v_model = ff2v_model
        self.flf2v_model = flf2v_model
        self.rate_limiter = rate_limiter

        self.client = genai.Client(
            api_key=api_key,
        )

    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: List[str],
        resolution: str = "1080p",
        aspect_ratio: str = "16:9",
        duration: int = 8,
        **kwargs,
    ) -> VideoOutput:

        params = {
            "prompt": prompt,
        }
        config_params = {
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "duration_seconds": duration,
        }
        if len(reference_image_paths) == 0:
            params["model"] = self.t2v_model
        elif len(reference_image_paths) == 1:
            params["model"] = self.ff2v_model
            params["image"] = types.Image.from_file(location=reference_image_paths[0])
        elif len(reference_image_paths) == 2:
            # 首尾帧（"flf2v"）插值会返回 400
            # INVALID_ARGUMENT（"Your use case is currently not supported"）
            # 错误（在公共 Gemini Developer API 上，该功能似乎需要
            # Vertex AI / 白名单）。回退为仅首帧，使镜头仍能渲染
            # 而非导致整条流水线失败；只是片段不会被锚定到生成的末帧。
            logging.warning(
                "提供了两张参考图片，但该 API key 不支持首尾帧视频生成；"
                "回退为仅首帧生成。"
            )
            params["model"] = self.ff2v_model
            params["image"] = types.Image.from_file(location=reference_image_paths[0])
        else:
            raise ValueError("参考图片数量不得超过 2 张")

        logging.info(f"正在调用 {params['model']} 生成视频...")

        # 若配置了速率限制则应用
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        # 速率限制错误的重试逻辑
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                operation = self.client.models.generate_videos(
                    **params,
                    config=types.GenerateVideosConfig(**config_params),
                )
                break
            except ClientError as e:
                # google.genai.errors.ClientError 通过 `.code` 暴露 HTTP 状态码；
                # `.status_code` 不存在，因此这一行
                # 曾抛出 AttributeError 并掩盖了所有真正的 ClientError。
                if e.code == 429 and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logging.warning(f"触发速率限制 (429)，{wait_time} 秒后重试...（第 {attempt + 1}/{max_retries} 次尝试）")
                    await asyncio.sleep(wait_time)
                else:
                    raise

        while not operation.done:
            await asyncio.sleep(2)
            operation = self.client.operations.get(operation)
            logging.info(f"视频生成尚未完成，等待 2 秒...")

        # 检查操作是否成功完成
        if operation.error:
            error_msg = f"视频生成失败: {operation.error}"
            logging.error(error_msg)
            raise RuntimeError(error_msg)

        if not operation.response:
            error_msg = "视频生成完成但未收到响应"
            logging.error(error_msg)
            raise RuntimeError(error_msg)

        if not hasattr(operation.response, 'generated_videos') or not operation.response.generated_videos:
            error_msg = "视频生成完成但未生成任何视频"
            logging.error(error_msg)
            raise RuntimeError(error_msg)

        generated_video = operation.response.generated_videos[0]
        self.client.files.download(file=generated_video.video)

        video_output = VideoOutput(
            fmt="bytes",
            ext="mp4",
            data=generated_video.video.video_bytes,
        )
        return video_output
