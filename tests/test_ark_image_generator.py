# -*- coding: utf-8 -*-
"""火山引擎 Ark API 图片生成器的单元测试。"""

import unittest
from unittest.mock import patch

from agent_runtime.insightforge_adapters import _build_image_generator
from tools.image_generator_doubao_seedream_ark_api import ImageGeneratorDoubaoSeedreamArkAPI


class ArkImageGeneratorFactoryTests(unittest.TestCase):
    """测试 agent 运行时工厂是否为 volcengine URL 选择 Ark 生成器。"""

    def test_factory_selects_ark_from_volcengine_base_url(self):
        with patch("agent_runtime.insightforge_adapters.image_api_key", return_value="ark-key"), \
             patch("agent_runtime.insightforge_adapters.image_model",
                   return_value="doubao-seedream-3-0-t2i-250415"), \
             patch("agent_runtime.insightforge_adapters.image_base_url",
                   return_value="https://ark.cn-beijing.volces.com/api/v3"):
            generator = _build_image_generator()
        self.assertIsInstance(generator, ImageGeneratorDoubaoSeedreamArkAPI)
        self.assertEqual(generator.model, "doubao-seedream-3-0-t2i-250415")
        self.assertEqual(generator.base_url, "https://ark.cn-beijing.volces.com/api/v3")

    def test_factory_does_not_select_ark_for_non_volcengine_url(self):
        with patch("agent_runtime.insightforge_adapters.image_api_key", return_value="key"), \
             patch("agent_runtime.insightforge_adapters.image_model",
                   return_value="gemini-2.5-flash-image-preview"), \
             patch("agent_runtime.insightforge_adapters.image_base_url",
                   return_value="https://yunwu.ai"):
            generator = _build_image_generator()
        self.assertNotIsInstance(generator, ImageGeneratorDoubaoSeedreamArkAPI)


class ArkImageGeneratorInitTests(unittest.TestCase):
    """ImageGeneratorDoubaoSeedreamArkAPI 构造函数的测试。"""

    def test_default_base_url_is_ark_api(self):
        gen = ImageGeneratorDoubaoSeedreamArkAPI(api_key="key")
        self.assertEqual(gen.base_url, "https://ark.cn-beijing.volces.com/api/v3")

    def test_custom_base_url_strips_trailing_slash(self):
        gen = ImageGeneratorDoubaoSeedreamArkAPI(
            api_key="key", base_url="https://ark.cn-beijing.volces.com/api/v3/"
        )
        self.assertEqual(gen.base_url, "https://ark.cn-beijing.volces.com/api/v3")

    def test_custom_model_is_stored(self):
        gen = ImageGeneratorDoubaoSeedreamArkAPI(
            api_key="key", model="doubao-seedream-5-0-t2i"
        )
        self.assertEqual(gen.model, "doubao-seedream-5-0-t2i")


if __name__ == "__main__":
    unittest.main()
