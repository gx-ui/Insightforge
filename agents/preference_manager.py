from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

import yaml

DEFAULT_IMAGE_PREFERENCES: dict[str, Any] = {
    "aspect_ratio": "16:9",
    "model": "follow_config",
    "quality": "2k",
}

DEFAULT_VIDEO_PREFERENCES: dict[str, Any] = {
    "aspect_ratio": "16:9",
    "model": "follow_config",
    "resolution": "1080p",
}

IMAGE_MODEL_MAP: dict[str, Optional[str]] = {
    "follow_config": None,
    "seedream_5_0_pro": "doubao-seedream-5-0-pro-260628",
}

VIDEO_MODEL_MAP: dict[str, Optional[str]] = {
    "follow_config": None,
    "seedance_2_0_fast": "doubao-seedance-2-0-fast-260128",
}

ASPECT_RATIO_MAP: dict[str, tuple[int, int]] = {
    "1:1": (1, 1),
    "3:4": (3, 4),
    "4:3": (4, 3),
    "9:16": (9, 16),
    "16:9": (16, 9),
    "21:9": (21, 9),
    "2:3": (2, 3),
}


class PreferenceMgr:
    """偏好管理器：只读 yaml、永不写。

    前端（Web UI）是唯一的写者（原子 tmp+rename），Agent 侧只读。
    偏好通过 preference_updated 事件在运行期更新内存对象。
    """

    def __init__(self, workspace_root: str | Path, session_index: Any, global_prefs_path: Path | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.session_index = session_index
        self._global_prefs_path = global_prefs_path or (Path.home() / '.insightforge' / 'preferences.yaml')
        self._version = 0
        self._preferences: dict[str, Any] = {
            "image": dict(DEFAULT_IMAGE_PREFERENCES),
            "video": dict(DEFAULT_VIDEO_PREFERENCES),
        }
        self._load()

    # -- 加载 --

    def _load(self) -> None:
        """启动时加载全局 + 会话 yaml 合并。"""
        global_path = self._global_prefs_path
        global_data = self._read_yaml(global_path)

        session_data: dict[str, Any] = {}
        session = self.session_index.active()
        if session:
            try:
                working_dir = self.session_index.working_dir(session["session_id"])
                session_path = working_dir / "preferences.yaml"
                session_data = self._read_yaml(session_path)
            except Exception:
                session_data = {}

        self._preferences = self._merge_preferences(global_data, session_data)

        # D5: 有会话文件时取会话 version，无会话文件时为 0（不取全局 version，
        # 避免首个 preference_updated 事件被 version<= 判定丢弃）
        if session_data:
            self._version = int(session_data.get("version", 0))
        else:
            self._version = 0


    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _extract_prefs(yaml_data: dict[str, Any]) -> dict[str, Any]:
        image = dict(DEFAULT_IMAGE_PREFERENCES)
        video = dict(DEFAULT_VIDEO_PREFERENCES)
        if isinstance(yaml_data.get("image"), dict):
            image.update(yaml_data["image"])
        if isinstance(yaml_data.get("video"), dict):
            video.update(yaml_data["video"])
        return {"image": image, "video": video}

    @staticmethod
    def _merge_preferences(global_data: dict[str, Any], session_data: dict[str, Any]) -> dict[str, Any]:
        """字段级合并：默认 <- 全局 <- 会话逐字段覆盖。"""
        merged = {
            "image": dict(DEFAULT_IMAGE_PREFERENCES),
            "video": dict(DEFAULT_VIDEO_PREFERENCES),
        }
        for section in ("image", "video"):
            g = global_data.get(section)
            if isinstance(g, dict):
                merged[section].update(g)
            s = session_data.get(section)
            if isinstance(s, dict):
                merged[section].update(s)
        return merged

    # -- 事件驱动更新 --

    def apply_preference_updated(self, event: dict[str, Any]) -> None:
        """应用前端发来的 preference_updated 事件。

        D5: 仅当 event.version > self._version 时接受。
        """
        event_version = int(event.get("version", 0))
        if event_version <= self._version:
            return
        prefs = event.get("preferences")
        if not isinstance(prefs, dict):
            return
        self._version = event_version
        self._preferences = self._extract_prefs(prefs)

    # -- 查询 --

    def snapshot(self) -> dict[str, Any]:
        return {
            "image": dict(self._preferences.get("image", DEFAULT_IMAGE_PREFERENCES)),
            "video": dict(self._preferences.get("video", DEFAULT_VIDEO_PREFERENCES)),
        }

    @property
    def version(self) -> int:
        return self._version

    def get_image_prefs(self) -> dict[str, Any]:
        return dict(self._preferences.get("image", DEFAULT_IMAGE_PREFERENCES))

    def get_video_prefs(self) -> dict[str, Any]:
        return dict(self._preferences.get("video", DEFAULT_VIDEO_PREFERENCES))

    def is_ratio_fixed(self, kind: Literal["image", "video"]) -> bool:
        prefs = self.get_image_prefs() if kind == "image" else self.get_video_prefs()
        return prefs.get("aspect_ratio", "auto") != "auto"

    def format_for_generator(self, kind: Literal["image", "video"]) -> Any:
        """为生成器格式化偏好。

        图片: 返回 "WxH" 字符串，auto 时返回 None。
        视频: 返回 (resolution, aspect_ratio) 元组，auto 时 aspect_ratio 为 None。
        """
        if kind == "image":
            return self._compute_image_size()
        if kind == "video":
            vprefs = self.get_video_prefs()
            resolution = vprefs.get("resolution", "1080p")
            aspect_ratio = vprefs.get("aspect_ratio", "16:9")
            if aspect_ratio == "auto":
                return (resolution, None)
            return (resolution, aspect_ratio)
        return None

    def _compute_image_size(self) -> Optional[str]:
        """从 aspect_ratio + quality 计算图片尺寸。

        long_edge = 1920 (1080) / 2560 (2k)。
        返回 "WxH"，auto 返回 None。
        """
        iprefs = self.get_image_prefs()
        aspect_ratio = iprefs.get("aspect_ratio", "auto")
        quality = iprefs.get("quality", "2k")

        if aspect_ratio == "auto":
            return None

        ratio = ASPECT_RATIO_MAP.get(aspect_ratio)
        if ratio is None:
            return None

        long_edge = 1920 if quality == "1080" else 2560
        w_ratio, h_ratio = ratio

        if w_ratio >= h_ratio:
            w = long_edge
            h = round(long_edge * h_ratio / w_ratio)
        else:
            h = long_edge
            w = round(long_edge * w_ratio / h_ratio)

        w -= w % 2
        h -= h % 2
        return f"{w}x{h}"

    def resolve_image_model(self, config_model: str) -> str:
        """从偏好解析图片模型，follow_config 则回退到 config。"""
        model_key = self.get_image_prefs().get("model", "follow_config")
        mapped = IMAGE_MODEL_MAP.get(model_key)
        return mapped if mapped else config_model

    def resolve_video_model(self, config_model: str) -> str:
        """从偏好解析视频模型，follow_config 则回退到 config。

        仅覆盖 t2v_model；i2v/ff2v/flf2v 沿用 config（E5）。
        """
        model_key = self.get_video_prefs().get("model", "follow_config")
        mapped = VIDEO_MODEL_MAP.get(model_key)
        return mapped if mapped else config_model