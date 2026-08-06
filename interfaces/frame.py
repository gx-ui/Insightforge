from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Tuple, Literal


class Frame(BaseModel):
    shot_idx: int = Field(
        description="镜头在序列中的索引，从 0 开始。"
    )

    frame_type: Literal["first", "last"] = Field(
        description="帧的类型，'first' 表示镜头的第一帧，'last' 表示镜头的最后一帧。"
    )

    cam_idx: int = Field(
        description="该帧所用相机的索引，从 0 开始。"
    )

    vis_char_idxs: List[int] = Field(
        description="该帧中可见角色的索引列表，对应输入中提供的角色列表。"
    )