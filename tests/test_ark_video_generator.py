# -*- coding: utf-8 -*-
"""火山引擎 Ark API 视频生成器的单元测试。"""

import unittest
from unittest.mock import patch

from agent_runtime.insightforge_adapters import _build_video_generator
from tools.video_generator_doubao_seedance_ark_api import VideoGeneratorDoubaoSeedanceArkAPI


class ArkVideoGeneratorFactoryTests(unittest.TestCase):
    """测试 agent 运行时工厂是否为 volcengine URL 选择 Ark 生成器。"""

    def test_factory_selects_ark_from_volcengine_base_url(self):
        with patch("agent_runtime.insightforge_adapters.video_api_key", return_value="ark-key"), \
             patch("agent_runtime.insightforge_adapters.video_model",
                   return_value="doubao-seedance-1-0-lite-t2v-250428"), \
             patch("agent_runtime.insightforge_adapters.video_t2v_model",
                   return_value="doubao-seedance-1-0-lite-t2v-250428"), \
             patch("agent_runtime.insightforge_adapters.video_i2v_model",
                   return_value="doubao-seedance-1-0-lite-i2v-250428"), \
             patch("agent_runtime.insightforge_adapters.video_base_url",
                   return_value="https://ark.cn-beijing.volces.com/api/v3"):
            generator = _build_video_generator()
        self.assertIsInstance(generator, VideoGeneratorDoubaoSeedanceArkAPI)
        self.assertEqual(generator.t2v_model, "doubao-seedance-1-0-lite-t2v-250428")
        self.assertEqual(generator.i2v_model, "doubao-seedance-1-0-lite-i2v-250428")
        self.assertEqual(generator.base_url, "https://ark.cn-beijing.volces.com/api/v3")

    def test_factory_falls_back_to_model_when_t2v_i2v_not_set(self):
        """当未配置 t2v_model/i2v_model 时，应回退到 video.model。"""
        with patch("agent_runtime.insightforge_adapters.video_api_key", return_value="ark-key"), \
             patch("agent_runtime.insightforge_adapters.video_model",
                   return_value="ep-2024xxx"), \
             patch("agent_runtime.insightforge_adapters.video_t2v_model",
                   return_value="ep-2024xxx"), \
             patch("agent_runtime.insightforge_adapters.video_i2v_model",
                   return_value="ep-2024xxx"), \
             patch("agent_runtime.insightforge_adapters.video_base_url",
                   return_value="https://ark.cn-beijing.volces.com/api/v3"):
            generator = _build_video_generator()
        self.assertIsInstance(generator, VideoGeneratorDoubaoSeedanceArkAPI)
        self.assertEqual(generator.t2v_model, "ep-2024xxx")
        self.assertEqual(generator.i2v_model, "ep-2024xxx")


class ArkVideoGeneratorModelSelectionTests(unittest.TestCase):
    """基于参考图片数量测试 _select_model。"""

    def setUp(self):
        self.gen = VideoGeneratorDoubaoSeedanceArkAPI(
            api_key="k", t2v_model="t2v-xxx", i2v_model="i2v-xxx"
        )

    def test_t2v_model_when_no_reference_images(self):
        self.assertEqual(self.gen._select_model(0), "t2v-xxx")

    def test_i2v_model_when_one_reference_image(self):
        self.assertEqual(self.gen._select_model(1), "i2v-xxx")

    def test_i2v_model_when_two_reference_images(self):
        self.assertEqual(self.gen._select_model(2), "i2v-xxx")

    def test_raises_when_more_than_two_reference_images(self):
        with self.assertRaises(ValueError):
            self.gen._select_model(3)


class ArkVideoGeneratorInitTests(unittest.TestCase):
    """VideoGeneratorDoubaoSeedanceArkAPI 构造函数的测试。"""

    def test_default_base_url_is_ark_api(self):
        gen = VideoGeneratorDoubaoSeedanceArkAPI(api_key="key")
        self.assertEqual(gen.base_url, "https://ark.cn-beijing.volces.com/api/v3")

    def test_default_models(self):
        gen = VideoGeneratorDoubaoSeedanceArkAPI(api_key="key")
        self.assertEqual(gen.t2v_model, "doubao-seedance-1-0-lite-t2v-250428")
        self.assertEqual(gen.i2v_model, "doubao-seedance-1-0-lite-i2v-250428")

    def test_custom_base_url_strips_trailing_slash(self):
        gen = VideoGeneratorDoubaoSeedanceArkAPI(
            api_key="key", base_url="https://ark.cn-beijing.volces.com/api/v3/"
        )
        self.assertEqual(gen.base_url, "https://ark.cn-beijing.volces.com/api/v3")


if __name__ == "__main__":
    unittest.main()
