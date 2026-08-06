import asyncio
from typing import List, Literal, Optional, Union
from PIL import Image

from utils.video import download_video


class VideoOutput:
    fmt: Literal["url", "bytes"]
    ext: str = "mp4"
    data: Union[str, bytes]

    def __init__(
        self,
        fmt: Literal["url", "bytes"],
        ext: str,
        data: Union[str, bytes],
    ):
        self.fmt = fmt
        self.ext = ext
        self.data = data

    def save_url(self, path: str) -> None:
        """从 URL 下载视频并保存到指定路径。

        Args:
            path (str): 视频保存路径。
        """
        download_video(self.data, path)

    def save_bytes(self, path: str) -> None:
        """将 bytes 对象保存到指定路径。

        Args:
            path (str): 视频保存路径。
        """
        with open(path, 'wb') as f:
            f.write(self.data)

    def save(self, path: str) -> None:
        save_func = getattr(self, f"save_{self.fmt}")
        save_func(path)