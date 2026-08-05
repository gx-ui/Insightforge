"""Tests for Novel2MoviePipeline initialization."""

import ast
from pathlib import Path
import unittest


class TestNovel2MoviePipelineInit(unittest.TestCase):
    def _class_node(self):
        source = Path("pipelines/novel2movie_pipeline.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        return next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Novel2MoviePipeline"
        )

    def test_initializes_runtime_dependencies(self):
        class_node = self._class_node()
        init_node = next(
            node
            for node in class_node.body
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        assigned = {
            target.attr
            for node in ast.walk(init_node)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        }

        self.assertTrue(
            {
                "working_dir",
                "novel_compressor",
                "event_extractor",
                "embeddings",
                "rerank_model",
                "scene_extractor",
                "global_information_planner",
                "image_generator",
                "rewriter",
                "script2video_pipeline",
            }.issubset(assigned)
        )


if __name__ == "__main__":
    unittest.main()
