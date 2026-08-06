import base64
import cv2
from typing import List, Literal, Optional, Union
from PIL import Image

from utils.image import download_image



class ImageOutput:
    fmt: Literal["b64", "url", "pil", "np"]
    ext: str = "png"
    data: Union[str, Image.Image]

    def __init__(
        self,
        fmt: Literal["b64", "url", "pil", "np"],
        ext: str,
        data: Union[str, Image.Image],
    ):
        self.fmt = fmt
        self.ext = ext
        self.data = data


    def save_b64(self, path: str) -> None:
        """将 base64 编码的图片保存到指定路径。

        Args:
            path (str): 图片保存路径。
        """
        with open(path, 'wb') as f:
            f.write(base64.b64decode(self.data))

    def save_url(self, path: str) -> None:
        """从 URL 下载图片并保存到指定路径。

        Args:
            path (str): 图片保存路径。
        """
        download_image(self.data, path)

    def save_pil(self, path: str) -> None:
        """将 PIL Image 保存到指定路径。

        Args:
            path (str): 图片保存路径。
        """
        self.data.save(path)

    def save_np(self, path: str) -> None:
        """将 numpy 数组保存到指定路径。

        Args:
            path (str): 图片保存路径。
        """
        cv2.imencode('.png', self.data)[1].tofile(path)

    def save(self, path: str) -> None:
        save_func = getattr(self, f"save_{self.fmt}")
        save_func(path)