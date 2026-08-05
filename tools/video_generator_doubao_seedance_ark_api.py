# -*- coding: utf-8 -*-
"""火山引擎官方 Ark API 视频生成器 (doubao-seedance)。

API 文档: https://www.volcengine.com/docs/82379/1520757

与云雾代理 (VideoGeneratorDoubaoSeedanceYunwuAPI) 使用完全相同的
payload/response 格式，唯一区别是 base_url 可配置且默认指向官方 Ark API。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, List, Literal

import aiohttp

from interfaces.video_output import VideoOutput
from utils.image import image_path_to_b64

_DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _emit_progress(progress: Any, stage: str, message: str, metadata: dict | None = None) -> None:
    if progress is not None:
        progress(stage, message, metadata or {})


class VideoGeneratorDoubaoSeedanceArkAPI:
    """Generate videos through the Volcano Engine Ark API (doubao-seedance).

    Uses an async task-based flow: create a generation task, then poll
    until completion.

    Model selection based on reference image count:

    - 0 images -> ``t2v_model`` (text-to-video)
    - 1 image  -> ``i2v_model`` (first-frame image-to-video)
    - 2 images -> ``i2v_model`` (first-and-last-frame image-to-video)
    """

    def __init__(
        self,
        api_key: str,
        t2v_model: str = "doubao-seedance-1-0-lite-t2v-250428",
        i2v_model: str = "doubao-seedance-1-0-lite-i2v-250428",
        base_url: str = _DEFAULT_BASE_URL,
        max_create_attempts: int = 3,
        max_poll_attempts: int = 300,
    ) -> None:
        self.api_key = api_key
        self.t2v_model = t2v_model
        self.i2v_model = i2v_model
        self.base_url = base_url.rstrip("/")
        self.max_create_attempts = max_create_attempts
        self.max_poll_attempts = max_poll_attempts

    def _select_model(self, reference_image_count: int) -> str:
        if reference_image_count == 0:
            return self.t2v_model
        elif reference_image_count <= 2:
            return self.i2v_model
        else:
            raise ValueError("reference_image_paths must contain 0, 1, or 2 images.")

    async def create_video_generation_task(
        self,
        prompt: str,
        reference_image_paths: List[str],
        resolution: Literal["480p", "720p", "1080p"] = "720p",
        aspect_ratio: str = "16:9",
        fps: Literal[16, 24] = 16,
        duration: Literal[5, 10] = 5,
        progress: Any = None,
    ) -> str:
        """Create a video generation task and return the task ID.

        Args:
            prompt: Text prompt for video generation.
            reference_image_paths: List of 0, 1, or 2 reference images.
            resolution: Resolution of the video.
            aspect_ratio: Aspect ratio of the video.
            fps: Frames per second of the video.
            duration: Duration of the video in seconds.
            progress: Optional progress callback.

        Returns:
            Task ID string.
        """
        model = self._select_model(len(reference_image_paths))
        logging.info(f"Calling {model} to generate video...")
        _emit_progress(
            progress,
            "video_create",
            f"Creating video task with {model}",
            {"model": model},
        )

        url = f"{self.base_url}/contents/generations/tasks"

        content = [
            {
                "type": "text",
                "text": prompt
                + f" --rs {resolution} --rt {aspect_ratio} --dur {duration} --fps {fps} --wm false --seed -1 --cf false",
            }
        ]
        if len(reference_image_paths) >= 1:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_path_to_b64(reference_image_paths[0])},
                    "role": "first_frame",
                }
            )
        if len(reference_image_paths) >= 2:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image_path_to_b64(reference_image_paths[1])},
                    "role": "last_frame",
                }
            )

        payload = {"model": model, "content": content}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        request_timeout = _env_float("INSIGHTFORGE_VIDEO_REQUEST_TIMEOUT_SECONDS", 60.0)
        timeout = aiohttp.ClientTimeout(total=request_timeout)
        last_error: Exception | None = None

        for attempt in range(1, self.max_create_attempts + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers=headers, json=payload) as response:
                        response_json = await response.json()
                        http_status = response.status
                logging.debug(f"Response: {response_json}")
            except Exception as e:
                last_error = e
                logging.error(
                    f"Error occurred while creating video generation task "
                    f"(attempt {attempt}/{self.max_create_attempts}): {e}"
                )
                if attempt < self.max_create_attempts:
                    await asyncio.sleep(attempt)
                continue

            if http_status >= 400:
                message = f"Video generation task creation failed with HTTP {http_status}: {response_json}"
                if http_status < 500:
                    raise RuntimeError(message)
                last_error = RuntimeError(message)
                logging.error(f"{message} (attempt {attempt}/{self.max_create_attempts})")
                if attempt < self.max_create_attempts:
                    await asyncio.sleep(attempt)
                continue

            task_id = response_json.get("id")
            if not task_id:
                raise RuntimeError(
                    f"Video generation task creation returned no task id: {response_json}"
                )
            logging.info(f"Video generation task created successfully. Task ID: {task_id}")
            _emit_progress(
                progress,
                "video_task_created",
                "Video generation task created",
                {"model": model, "task_id": task_id},
            )
            return task_id

        raise RuntimeError(
            f"Failed to create video generation task after {self.max_create_attempts} attempts."
        ) from last_error

    async def query_video_generation_task(
        self,
        task_id: str,
        progress: Any = None,
    ) -> str:
        """Query the video generation task until completion and return the video URL.

        Args:
            task_id: Task ID to query.
            progress: Optional progress callback.

        Returns:
            Video URL string.
        """
        url = f"{self.base_url}/contents/generations/tasks/{task_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        poll_interval = _env_float("INSIGHTFORGE_VIDEO_POLL_INTERVAL_SECONDS", 5.0)
        query_timeout = _env_float("INSIGHTFORGE_VIDEO_QUERY_TIMEOUT_SECONDS", 600.0)
        max_query_errors = _env_int("INSIGHTFORGE_VIDEO_MAX_QUERY_ERRORS", 5)
        request_timeout = _env_float("INSIGHTFORGE_VIDEO_REQUEST_TIMEOUT_SECONDS", 60.0)
        timeout = aiohttp.ClientTimeout(total=request_timeout)

        deadline = (
            asyncio.get_running_loop().time() + query_timeout if query_timeout > 0 else None
        )
        attempts = 0
        consecutive_errors = 0
        last_status: str | None = None

        while deadline is None or asyncio.get_running_loop().time() < deadline:
            if attempts >= self.max_poll_attempts:
                raise TimeoutError(
                    f"Video generation did not complete after {attempts} polls; "
                    f"last_status={last_status}"
                )
            attempts += 1

            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=headers) as response:
                        response_json = await response.json()
                        http_status = response.status
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= max_query_errors:
                    raise RuntimeError(
                        f"Querying video generation task failed {consecutive_errors} times in a row."
                    ) from e
                logging.error(
                    f"Error occurred while querying video generation task: {e}. "
                    f"Retrying in {poll_interval} seconds..."
                )
                await asyncio.sleep(poll_interval)
                continue
            consecutive_errors = 0

            if http_status >= 400:
                raise RuntimeError(
                    f"Querying video generation task failed with HTTP {http_status}: {response_json}"
                )

            status = response_json.get("status")
            last_status = status
            if status == "succeeded":
                video_url = response_json["content"]["video_url"]
                logging.info(f"Video generation completed successfully. Video URL: {video_url}")
                _emit_progress(
                    progress,
                    "video_completed",
                    "Video generation completed",
                    {"task_id": task_id},
                )
                return video_url
            elif status == "failed":
                logging.error(f"Video generation failed. Response: {response_json}")
                raise ValueError(f"Video generation failed: {response_json}")
            else:
                logging.info(
                    f"Video generation is still in progress. "
                    f"Checking again in {poll_interval} seconds..."
                )
                _emit_progress(
                    progress,
                    "video_status",
                    f"Video generation status: {status}",
                    {"task_id": task_id, "status": status},
                )
                await asyncio.sleep(poll_interval)

        raise RuntimeError(
            f"Video generation timed out after {query_timeout:g}s for task {task_id}; "
            f"last_status={last_status}"
        )

    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: List[str] = [],
        resolution: Literal["480p", "720p", "1080p"] = "720p",
        aspect_ratio: str = "16:9",
        fps: Literal[16, 24] = 16,
        duration: Literal[5, 10] = 5,
        **kwargs: Any,
    ) -> VideoOutput:
        """Generate a single video by creating a task and waiting for completion.

        Args:
            prompt: Text prompt for video generation.
            reference_image_paths: List of 0, 1, or 2 reference images.
            resolution: Resolution of the video.
            aspect_ratio: Aspect ratio of the video.
            fps: Frames per second of the video.
            duration: Duration of the video in seconds.

        Returns:
            VideoOutput containing the video URL.
        """
        progress = kwargs.get("progress")
        task_id = await self.create_video_generation_task(
            prompt, reference_image_paths, resolution, aspect_ratio, fps, duration, progress
        )
        video_url = await self.query_video_generation_task(task_id, progress)
        return VideoOutput(fmt="url", ext="mp4", data=video_url)
