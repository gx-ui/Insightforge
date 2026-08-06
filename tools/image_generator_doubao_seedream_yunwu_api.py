"""doubao-seedream 图片生成器的云雾代理变体。

整合（阶段5）：ImageGeneratorDoubaoSeedreamArkAPI 的轻量子类，
使用云雾 base_url 和 sequential_image_generation 默认值。
负载/响应格式相同（见 ARK docstring）。
"""

from __future__ import annotations

from .image_generator_doubao_seedream_ark_api import ImageGeneratorDoubaoSeedreamArkAPI


class ImageGeneratorDoubaoSeedreamYunwuAPI(ImageGeneratorDoubaoSeedreamArkAPI):
    """通过云雾代理调用 doubao-seedream（格式与 Ark 相同，端点不同）。"""

    def __init__(
        self,
        api_key: str,
        model: str = "doubao-seedream-4-0-250828",
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url="https://yunwu.ai/v1",
            sequential_image_generation="disabled",
        )