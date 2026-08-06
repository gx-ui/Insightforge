"""RenderBackend：基于配置的图片和视频生成器工厂。"""

从 InsightForge YAML 配置中读取 ``image_generator`` 和 ``video_generator`` 部分，
通过 *class_path* 实例化具体类，并接入速率限制器。

用法::

    backend = RenderBackend.from_config(config)
    image = await backend.image_generator.generate_single_image(...)
    video = await backend.video_generator.generate_single_video(...)
"""

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Dict

from utils.rate_limiter import RateLimiter


@dataclass
class RenderBackend:
    """将一个图片生成器和一个视频生成器打包在一起。"""

    image_generator: Any
    video_generator: Any

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "RenderBackend":
        """从已解析的 YAML 配置字典构建 RenderBackend。

        若各生成器配置部分中存在 ``max_requests_per_minute`` /
        ``max_requests_per_day``，则据此创建速率限制器。
        """
        img_cfg = config["image_generator"]
        vid_cfg = config["video_generator"]

        image_gen = _instantiate(img_cfg, _build_rate_limiter(img_cfg))
        video_gen = _instantiate(vid_cfg, _build_rate_limiter(vid_cfg))

        logging.info("渲染后端: image=%s, video=%s",
                     img_cfg["class_path"], vid_cfg["class_path"])

        return cls(image_generator=image_gen, video_generator=video_gen)


def _build_rate_limiter(section: Dict[str, Any]) -> RateLimiter | None:
    rpm = section.get("max_requests_per_minute")
    rpd = section.get("max_requests_per_day")
    if rpm or rpd:
        return RateLimiter(max_requests_per_minute=rpm, max_requests_per_day=rpd)
    return None


def _instantiate(section: Dict[str, Any], rate_limiter: RateLimiter | None) -> Any:
    module_path, cls_name = section["class_path"].rsplit(".", 1)
    cls = getattr(importlib.import_module(module_path), cls_name)
    init_args = dict(section.get("init_args", {}))
    if rate_limiter is not None:
        init_args["rate_limiter"] = rate_limiter
    return cls(**init_args)