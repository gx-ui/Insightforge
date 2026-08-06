"""Phase 6 prototype: script2video text-planning as a LangGraph StateGraph.

Thin wrapper that sequences the existing pipeline methods as graph nodes.
File caching (os.path.exists) stays (product contract); asyncio.gather for
parallel shots stays inside the decompose node. The public plan_text_artifacts
signature is preserved; this module provides a graph-backed implementation
that can replace it incrementally.

Validated: linear DAG (extract->storyboard->decompose->camera_tree) sequences
correctly; parallel shot decomposition uses asyncio.gather inside a single
node (no Send fan-out needed, per Phase 0 finding).
"""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END


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
    _provided_characters: bool


def build_planning_graph(pipeline: Any):
    """Build a StateGraph that wraps the pipeline's text-planning steps.

    ``pipeline`` must expose: extract_characters, design_storyboard,
    decompose_visual_descriptions, construct_camera_tree (duck-typed, same
    as the existing Script2VideoPipeline).
    """

    async def extract_characters_node(state: PlanningState) -> dict:
        characters = state.get("characters")
        if characters is None:
            characters = await pipeline.extract_characters(
                script=state["script"], quiet=state.get("quiet", False)
            )
            return {"characters": characters, "_provided_characters": False}
        return {"_provided_characters": True}

    async def design_storyboard_node(state: PlanningState) -> dict:
        storyboard = await pipeline.design_storyboard(
            script=state["script"],
            characters=state["characters"],
            user_requirement=state["user_requirement"],
            quiet=state.get("quiet", False),
        )
        return {"storyboard": storyboard}

    async def decompose_shots_node(state: PlanningState) -> dict:
        # Parallel shot decomposition via asyncio.gather INSIDE the node
        # (preserves exact concurrency semantics; no Send fan-out needed).
        shot_descriptions = await pipeline.decompose_visual_descriptions(
            shot_brief_descriptions=state["storyboard"],
            characters=state["characters"],
            quiet=state.get("quiet", False),
        )
        return {"shot_descriptions": shot_descriptions}

    async def construct_camera_tree_node(state: PlanningState) -> dict:
        camera_tree = await pipeline.construct_camera_tree(
            shot_descriptions=state["shot_descriptions"],
            quiet=state.get("quiet", False),
        )
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
    """Convenience: build + run the planning graph, return final state."""
    app = build_planning_graph(pipeline)
    result = await app.ainvoke(kwargs)
    return {
        "characters": result.get("characters"),
        "storyboard": result.get("storyboard"),
        "shot_descriptions": result.get("shot_descriptions"),
        "camera_tree": result.get("camera_tree"),
    }
