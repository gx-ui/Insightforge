from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Tuple



class Camera(BaseModel):
    idx: int = Field(
        description="相机在场景中的索引，从 0 开始。",
    )

    active_shot_idxs: List[int] = Field(
        description="该相机可以拍摄的镜头索引列表。",
    )

    parent_cam_idx: Optional[int] = Field(
        default=None,
        description="父相机的索引。若该相机没有父相机，则设为 None。",
    )

    parent_shot_idx: Optional[int] = Field(
        default=None,
        description="所依赖镜头的索引。若该相机没有父相机，则设为 None。",
    )

    reason: Optional[str] = Field(
        default=None,
        description="选择父相机的原因。若该相机没有父相机，则设为 None。",
    )

    parent_shot_idx: Optional[int] = Field(
        default=None,
        description="所依赖镜头的索引。若该相机没有父相机，则设为 None。",
    )

    is_parent_fully_covers_child: Optional[bool] = Field(
        default=None,
        description="父相机是否完全覆盖子相机的内容。若该相机没有父相机，则设为 None。",
    )

    missing_info: Optional[str] = Field(
        default=None,
        description="子镜头中未被父镜头覆盖的缺失信息。若父镜头完全覆盖子镜头，则设为 None。",
    )