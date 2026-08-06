"""Yunwu proxy variant of the doubao-seedream image generator.

Consolidated (Phase 5): thin subclass of ImageGeneratorDoubaoSeedreamArkAPI
with the Yunwu base_url and sequential_image_generation default. Same
payload/response format (see ARK docstring).
"""

from __future__ import annotations

from .image_generator_doubao_seedream_ark_api import ImageGeneratorDoubaoSeedreamArkAPI


class ImageGeneratorDoubaoSeedreamYunwuAPI(ImageGeneratorDoubaoSeedreamArkAPI):
    """doubao-seedream via the Yunwu proxy (same format as Ark, different endpoint)."""

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
