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
    """通过火山引擎 Ark API 生成视频 (doubao-seedance)。

    使用基于异步任务的流程：创建生成任务，然后轮询直至完成。

    根据参考图片数量选择模型：

    - 0 张图片 -> ``t2v_model``（文生视频）
    - 1 张图片 -> ``i2v_model``（首帧图生视频）
    - 2 张图片 -> ``i2v_model``（首尾帧图生视频）
    """

    def __init__(
        self,
        api_key: str,
        t2v_model: str = "doubao-seedance-1-0-lite-t2v-250428",
        i2v_model: str = "doubao-seedance-1-0-lite-i2v-250428",
        base_url: str = _DEFAULT_BASE_URL,
        max_create_attempts: int = 3,
        max_poll_attempts: int = 300,
        ff2v_model: str | None = None,
        flf2v_model: str | None = None,
        poll_interval: float | None = None,
    ) -> None:
        self.api_key = api_key
        self.t2v_model = t2v_model
        self.i2v_model = i2v_model
        self.ff2v_model = ff2v_model or i2v_model
        self.flf2v_model = flf2v_model or i2v_model
        self.base_url = base_url.rstrip("/")
        self.max_create_attempts = max_create_attempts
        self.max_poll_attempts = max_poll_attempts
        self._poll_interval = poll_interval

    def _select_model(self, reference_image_count: int) -> str:
        if reference_image_count == 0:
            return self.t2v_model
        elif reference_image_count == 1:
            return self.ff2v_model
        elif reference_image_count == 2:
            return self.flf2v_model
        else:
            raise ValueError("reference_image_paths 必须包含 0、1 或 2 张图片。")

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
        """创建视频生成任务并返回任务 ID。

        Args:
            prompt: 视频生成的文本提示。
            reference_image_paths: 0、1 或 2 张参考图片的列表。
            resolution: 视频分辨率。
            aspect_ratio: 视频宽高比。
            fps: 视频帧率。
            duration: 视频时长（秒）。
            progress: 可选的进度回调。

        Returns:
            任务 ID 字符串。
        """
        model = self._select_model(len(reference_image_paths))
        logging.info(f"正在调用 {model} 生成视频...")
        _emit_progress(
            progress,
            "video_create",
            f"正在使用 {model} 创建视频任务",
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
                logging.debug(f"响应: {response_json}")
            except Exception as e:
                last_error = e
                logging.error(
                    f"创建视频生成任务时出错 "
                    f"（第 {attempt}/{self.max_create_attempts} 次尝试）: {e}"
                )
                if attempt < self.max_create_attempts:
                    await asyncio.sleep(attempt)
                continue

            if http_status >= 400:
                message = f"视频生成任务创建失败，HTTP {http_status}: {response_json}"
                if http_status < 500:
                    raise RuntimeError(message)
                last_error = RuntimeError(message)
                logging.error(f"{message}（第 {attempt}/{self.max_create_attempts} 次尝试）")
                if attempt < self.max_create_attempts:
                    await asyncio.sleep(attempt)
                continue

            task_id = response_json.get("id")
            if not task_id:
                raise RuntimeError(
                    f"视频生成任务创建未返回任务 ID: {response_json}"
                )
            logging.info(f"视频生成任务创建成功。任务 ID: {task_id}")
            _emit_progress(
                progress,
                "video_task_created",
                "视频生成任务已创建",
                {"model": model, "task_id": task_id},
            )
            return task_id

        raise RuntimeError(
            f"经过 {self.max_create_attempts} 次尝试后仍未能创建视频生成任务。"
        ) from last_error

    async def query_video_generation_task(
        self,
        task_id: str,
        progress: Any = None,
    ) -> str:
        """轮询视频生成任务直至完成并返回视频 URL。

        Args:
            task_id: 要查询的任务 ID。
            progress: 可选的进度回调。

        Returns:
            视频 URL 字符串。
        """
        url = f"{self.base_url}/contents/generations/tasks/{task_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        poll_interval = self._poll_interval if self._poll_interval is not None else _env_float("INSIGHTFORGE_VIDEO_POLL_INTERVAL_SECONDS", 5.0)
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
                    f"视频生成在 {attempts} 次轮询后仍未完成；"
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
                        f"连续 {consecutive_errors} 次查询视频生成任务失败。"
                    ) from e
                logging.error(
                    f"查询视频生成任务时出错: {e}。"
                    f"将在 {poll_interval} 秒后重试..."
                )
                await asyncio.sleep(poll_interval)
                continue
            consecutive_errors = 0

            if http_status >= 400:
                raise RuntimeError(
                    f"查询视频生成任务失败，HTTP {http_status}: {response_json}"
                )

            status = response_json.get("status")
            last_status = status
            if status == "succeeded":
                video_url = response_json["content"]["video_url"]
                logging.info(f"视频生成成功完成。视频 URL: {video_url}")
                _emit_progress(
                    progress,
                    "video_completed",
                    "视频生成已完成",
                    {"task_id": task_id},
                )
                return video_url
            elif status == "failed":
                logging.error(f"视频生成失败。响应: {response_json}")
                raise ValueError(f"视频生成失败: {response_json}")
            else:
                logging.info(
                    f"视频生成仍在进行中。"
                    f"将在 {poll_interval} 秒后再次检查..."
                )
                _emit_progress(
                    progress,
                    "video_status",
                    f"视频生成状态: {status}",
                    {"task_id": task_id, "status": status},
                )
                await asyncio.sleep(poll_interval)

        raise RuntimeError(
            f"视频生成在 {query_timeout:g} 秒后超时（任务 {task_id}）；"
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
        """通过创建任务并等待完成来生成单个视频。

        Args:
            prompt: 视频生成的文本提示。
            reference_image_paths: 0、1 或 2 张参考图片的列表。
            resolution: 视频分辨率。
            aspect_ratio: 视频宽高比。
            fps: 视频帧率。
            duration: 视频时长（秒）。

        Returns:
            包含视频 URL 的 VideoOutput。
        """
        progress = kwargs.get("progress")
        task_id = await self.create_video_generation_task(
            prompt, reference_image_paths, resolution, aspect_ratio, fps, duration, progress
        )
        video_url = await self.query_video_generation_task(task_id, progress)
        return VideoOutput(fmt="url", ext="mp4", data=video_url)
