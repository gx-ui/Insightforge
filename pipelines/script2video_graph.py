"""Phase 6: 基于 LangGraph StateGraph 的 script2video 文本规划。"""

Replaces the inline orchestration in Script2VideoPipeline.plan_text_artifacts
with a stateful graph. Each node delegates to the pipeline's existing methods
(which handle file caching); the graph adds progress emission, the
provided-characters branch, and the camera_tree retry. The public
plan_text_artifacts signature is unchanged; a feature flag falls back to the
legacy inline path.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, TypedDict

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
    progress: Any
    quiet: bool


def _emit(progress, stage, message, metadata=None):
    if progress is not None:
        progress(stage, message, metadata or {})


def build_planning_graph(pipeline: Any):
    async def extract_characters_node(state: PlanningState) -> dict:
        progress = state.get("progress")
        quiet = state.get("quiet", False)
        characters = state.get("characters")
        if characters is None:
            _emit(progress, "extract_characters", "Extracting characters from script")
            characters = await pipeline.extract_characters(script=state["script"], quiet=quiet)
        else:
            from pipelines.script2video_pipeline import _normalize_model_list
            characters = _normalize_model_list(characters, CharacterInScene, "characters")
            _emit(progress, "extract_characters", "Using provided characters", {"provided": True, "count": len(characters)})
            characters_path = os.path.join(pipeline.working_dir, "characters.json")
            if not os.path.exists(characters_path):
                with open(characters_path, "w", encoding="utf-8") as f:
                    json.dump([c.model_dump() for c in characters], f, ensure_ascii=False, indent=4)
            for character in characters:
                pipeline.character_portrait_events[character.idx] = asyncio.Event()
        return {"characters": characters}

    async def design_storyboard_node(state: PlanningState) -> dict:
        _emit(state.get("progress"), "design_storyboard", "Designing storyboard")
        storyboard = await pipeline.design_storyboard(
            script=state["script"],
            characters=state["characters"],
            user_requirement=state["user_requirement"],
            quiet=state.get("quiet", False),
        )
        return {"storyboard": storyboard}

    async def decompose_shots_node(state: PlanningState) -> dict:
        _emit(state.get("progress"), "decompose_shots", "Decomposing shot visual descriptions", {"shot_count": len(state["storyboard"])})
        shot_descriptions = await pipeline.decompose_visual_descriptions(
            shot_brief_descriptions=state["storyboard"],
            characters=state["characters"],
            quiet=state.get("quiet", False),
        )
        return {"shot_descriptions": shot_descriptions}

    async def construct_camera_tree_node(state: PlanningState) -> dict:
        progress = state.get("progress")
        quiet = state.get("quiet", False)
        camera_tree = None
        for attempt in range(2):
            try:
                stage = "construct_camera_tree" if attempt == 0 else "construct_camera_tree_retry"
                message = "Constructing camera tree" if attempt == 0 else "Retrying camera tree construction after schema/type failure"
                _emit(progress, stage, message, {"shot_count": len(state["shot_descriptions"]), "attempt": attempt + 1})
                camera_tree = await pipeline.construct_camera_tree(shot_descriptions=state["shot_descriptions"], quiet=quiet)
                break
            except Exception:
                camera_tree_path = os.path.join(pipeline.working_dir, "camera_tree.json")
                if os.path.exists(camera_tree_path):
                    os.remove(camera_tree_path)
                if attempt == 1:
                    raise
        return {"camera_tree": camera_tree}

    g = StateGraph(PlanningState)
    g.add_node("extract_characters", extract_characters_node)
    g.add_node("design_storyboard", design_storyboard_node)
    g.add_node("decompose_shots", decompose_shots_node)
    g.add_node("construct_camera_tree", construct_camera_tree_node)
    g.add_edge(START, "extract_characters")
    g.add_edge("extract_characters", "design_storyboard")
    g.add_edge("design_storyboard", "decompose_shots")
    g.add_edge("decompose_shots", "construct_camera_tree")
    g.add_edge("construct_camera_tree", END)
    return g.compile()


async def run_planning_graph(pipeline: Any, **kwargs) -> dict:
    """构建并运行规划图，返回产物字典。"""
    app = build_planning_graph(pipeline)
    result = await app.ainvoke(kwargs)
    return {
        "characters": result.get("characters"),
        "storyboard": result.get("storyboard"),
        "shot_descriptions": result.get("shot_descriptions"),
        "camera_tree": result.get("camera_tree"),
    }
