from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class StageInfo:
    group: str
    stage: str
    label: str


_STAGE_MAPPINGS: tuple[tuple[tuple[str, ...], StageInfo], ...] = (
    (("character_portrait", "character_portraits"), StageInfo("characters", "portraits", "正在生成角色图")),
    (("extract_characters",), StageInfo("characters", "characters", "正在设计角色")),
    (("storyboard", "shot_description", "camera_tree", "load_storyboard", "load_shot"), StageInfo("storyboard", "storyboard", "正在规划分镜")),
    (("frame",), StageInfo("frames", "frames", "正在生成关键帧")),
    (("transition",), StageInfo("transitions", "clips", "正在生成转场")),
    (("video_clip", "video_"), StageInfo("clips", "clips", "正在生成视频")),
    (("render", "concatenate", "compose", "final_video"), StageInfo("compositing", "compositing", "正在合成视频")),
    (("starting", "initializing_llm", "chat_model_ready", "idea_pipeline", "script_pipeline", "planning", "narrative", "novel", "revising"), StageInfo("narrative", "narrative", "正在理解你的创作需求")),
)


def normalize_stage(raw_stage: str) -> StageInfo:
    normalized = raw_stage.strip().lower()
    for patterns, info in _STAGE_MAPPINGS:
        if any(pattern in normalized for pattern in patterns):
            return info
    return StageInfo("generic", raw_stage, "正在处理你的创作任务")


def utc_timestamp_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
