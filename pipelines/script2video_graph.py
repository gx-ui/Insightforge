"""Phase 6: 基于 LangGraph StateGraph 的 script2video 文本规划。

将 Script2VideoPipeline.plan_text_artifacts 中的内联编排替换为有状态图。
每个节点委托给管道现有的方法（这些方法负责文件缓存）；该图新增了进度上报、provided-characters 分支以及 camera_tree 重试逻辑。
对外暴露的 plan_text_artifacts 签名保持不变；通过特性开关（feature flag）可回退到旧的内联实现路径。
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Callable, TypedDict

from langgraph.graph import StateGraph, START, END

from interfaces import CharacterInScene


class PlanningState(TypedDict, total=False):
    script: str
    user_requirement: str
    style: str
    characters: Any
    storyboard: Any
    shot_descriptions: Any
    camera_tree: Any


def _emit(progress, stage, message, metadata=None):
    if progress is not None:
        progress(stage, message, metadata or {})


class _PlanningGraphBuilder:
    """将不可序列化的 progress 回调挂在实例上，避免混入图状态。"""

    def __init__(self, pipeline: Any, progress: Callable | None, quiet: bool):
        self.pipeline = pipeline
        self.progress = progress
        self.quiet = quiet

    async def extract_characters_node(self, state: PlanningState) -> dict:
        characters = state.get("characters")
        if characters is None:
            _emit(self.progress, "extract_characters", "Extracting characters from script")
            characters = await self.pipeline.extract_characters(
                script=state["script"], quiet=self.quiet,
            )
        else:
            from pipelines.script2video_pipeline import _normalize_model_list
            characters = _normalize_model_list(characters, CharacterInScene, "characters")
            _emit(self.progress, "extract_characters", "Using provided characters",
                  {"provided": True, "count": len(characters)})
            characters_path = os.path.join(self.pipeline.working_dir, "characters.json")
            if not os.path.exists(characters_path):
                with open(characters_path, "w", encoding="utf-8") as f:
                    json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=4)
            for character in characters:
                self.pipeline.character_portrait_events[character.idx] = asyncio.Event()
        return {"characters": characters}

    async def design_storyboard_node(self, state: PlanningState) -> dict:
        _emit(self.progress, "design_storyboard", "Designing storyboard")
        storyboard = await self.pipeline.design_storyboard(
            script=state["script"],
            characters=state["characters"],
            user_requirement=state["user_requirement"],
            quiet=self.quiet,
        )
        return {"storyboard": storyboard}

    async def decompose_shots_node(self, state: PlanningState) -> dict:
        _emit(self.progress, "decompose_shots", "Decomposing shot visual descriptions",
              {"shot_count": len(state["storyboard"])})
        shot_descriptions = await self.pipeline.decompose_visual_descriptions(
            shot_brief_descriptions=state["storyboard"],
            characters=state["characters"],
            quiet=self.quiet,
        )
        return {"shot_descriptions": shot_descriptions}

    async def construct_camera_tree_node(self, state: PlanningState) -> dict:
        camera_tree = None
        for attempt in range(2):
            try:
                stage = "construct_camera_tree" if attempt == 0 else "construct_camera_tree_retry"
                message = "Constructing camera tree" if attempt == 0 else "Retrying camera tree construction after schema/type failure"
                _emit(self.progress, stage, message,
                      {"shot_count": len(state["shot_descriptions"]), "attempt": attempt + 1})
                camera_tree = await self.pipeline.construct_camera_tree(
                    shot_descriptions=state["shot_descriptions"], quiet=self.quiet,
                )
                break
            except Exception:
                camera_tree_path = os.path.join(self.pipeline.working_dir, "camera_tree.json")
                if os.path.exists(camera_tree_path):
                    os.remove(camera_tree_path)
                if attempt == 1:
                    raise
        return {"camera_tree": camera_tree}


def build_planning_graph(pipeline: Any, progress: Callable | None = None, quiet: bool = False):
    builder = _PlanningGraphBuilder(pipeline, progress, quiet)

    g = StateGraph(PlanningState)
    g.add_node("extract_characters", builder.extract_characters_node)
    g.add_node("design_storyboard", builder.design_storyboard_node)
    g.add_node("decompose_shots", builder.decompose_shots_node)
    g.add_node("construct_camera_tree", builder.construct_camera_tree_node)
    g.add_edge(START, "extract_characters")
    g.add_edge("extract_characters", "design_storyboard")
    g.add_edge("design_storyboard", "decompose_shots")
    g.add_edge("decompose_shots", "construct_camera_tree")
    g.add_edge("construct_camera_tree", END)
    return g.compile()


async def run_planning_graph(pipeline: Any, **kwargs) -> dict:
    """构建并运行规划图，返回产物字典。

    只将可序列化字段传入图状态；progress / quiet 通过 _PlanningGraphBuilder 注入。
    """
    progress = kwargs.pop("progress", None)
    quiet = kwargs.pop("quiet", False)
    app = build_planning_graph(pipeline, progress=progress, quiet=quiet)
    result = await app.ainvoke(kwargs)
    return {
        "characters": result.get("characters"),
        "storyboard": result.get("storyboard"),
        "shot_descriptions": result.get("shot_descriptions"),
        "camera_tree": result.get("camera_tree"),
    }