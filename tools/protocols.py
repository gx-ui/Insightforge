"""渲染后端的结构化类型契约。

任何暴露了正确方法签名的类都满足这些协议——无需继承。
现有生成器（Google、云雾/豆包、云雾/Veo）已通过鸭子类型合规。
"""

from typing import List, Protocol, runtime_checkable

from interfaces.image_output import ImageOutput
from interfaces.video_output import VideoOutput


@runtime_checkable
class ImageGenerator(Protocol):
    """根据文本提示和可选的参考图片生成单张图片。"""

    async def generate_single_image(
        self,
        prompt: str,
        reference_image_paths: List[str],
        **kwargs,
    ) -> ImageOutput: ...


@runtime_checkable
class VideoGenerator(Protocol):
    """根据文本提示和可选的参考图片生成单个视频。"""

    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: List[str],
        **kwargs,
    ) -> VideoOutput: ...