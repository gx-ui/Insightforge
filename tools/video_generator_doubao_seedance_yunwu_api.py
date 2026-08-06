"""doubao-seedance 视频生成器的云雾代理变体。

整合（阶段5）：VideoGeneratorDoubaoSeedanceArkAPI 的轻量子类，
使用云雾 base_url、3 模型选择（t2v/ff2v/flf2v）和 poll_interval。
负载/响应格式相同（见 ARK docstring）。
"""

from __future__ import annotations

from .video_generator_doubao_seedance_ark_api import VideoGeneratorDoubaoSeedanceArkAPI


class VideoGeneratorDoubaoSeedanceYunwuAPI(VideoGeneratorDoubaoSeedanceArkAPI):
    """通过云雾代理调用 doubao-seedance（格式与 Ark 相同，端点不同）。"""

    def __init__(
        self,
        api_key: str,
        t2v_model: str = "doubao-seedance-1-0-lite-t2v-250428",
        ff2v_model: str = "doubao-seedance-1-0-lite-i2v-250428",
        flf2v_model: str = "doubao-seedance-1-0-lite-i2v-250428",
        max_create_attempts: int = 3,
        poll_interval: int = 2,
        max_poll_attempts: int = 300,
    ) -> None:
        super().__init__(
            api_key=api_key,
            t2v_model=t2v_model,
            i2v_model=ff2v_model,
            base_url="https://yunwu.ai/volc/v1",
            max_create_attempts=max_create_attempts,
            max_poll_attempts=max_poll_attempts,
            ff2v_model=ff2v_model,
            flf2v_model=flf2v_model,
            poll_interval=poll_interval,
        )