import os
import logging
import cv2
from typing import List, Tuple, Union, Optional
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser as PydanticOutputParser
from scenedetect import open_video, SceneManager, split_video_ffmpeg
from scenedetect.detectors import ContentDetector

from interfaces import ShotDescription, ShotBriefDescription, Camera, ImageOutput, VideoOutput


from moviepy import VideoFileClip
from PIL import Image


system_prompt_template_select_reference_camera = \
"""
[角色]
你是一名专业的视频剪辑专家，专精于多机位镜头分析及场景结构建模。你拥有深厚的镜头语言知识，能够理解景别（如远景、中景、特写）和内容包含关系。你可以根据相应的镜头描述推断机位之间的层级结构。

[任务]
你的任务是分析输入的机位数据，构建一个"机位树"。该树结构表示父级机位的内容包含子级机位的内容。具体来说，你需要为每个机位找出其父级机位（若存在），并确定依赖的镜头索引（即父级机位素材中包含了子级机位内容的具体镜头）。如果某个机位没有父级，则输出 None。

[输入]
输入是一个机位序列。该序列被包裹在 <CAMERA_SEQ> 和 </CAMERA_SEQ> 之间。
每个机位包含该机位拍摄的一系列镜头，这些镜头被包裹在 <CAMERA_N> 和 </CAMERA_N> 之间，其中 N 是机位的索引。

以下是输入格式示例：

<CAMERA_SEQ>
<CAMERA_0>
Shot 0: 街道中景。Alice 和 Bob 正朝彼此走去。
Shot 2: 街道中景。Alice 和 Bob 拥抱。
</CAMERA_0>
<CAMERA_1>
Shot 1: Alice 面部特写。她认出 Bob 时，表情从惊讶转为欣喜。
</CAMERA_1>
</CAMERA_SEQ>


[输出]
{format_instructions}

[指导原则]
- 所有输出值（不含键）的语言应与输入语言保持一致。
- 内容包含检查：父级机位应尽可能完整地包含子级机位的内容（例如，父级中景双人镜头包含了子级过肩反打镜头）。通过比较关键词（如角色、动作、场景）分析镜头描述，确保父级镜头的视野覆盖了子级镜头的内容。
- 过渡平滑优先：优先选择景别较大的机位作为父机位，例如远景→中景或中景→特写。相邻父子节点的景别应尽可能相似。除非必要，不允许从远景直接跳到特写。
- 时间邻近性：每个机位以其对应的第一个镜头描述，根据第一个镜头的描述定位父机位。父机位的镜头索引应尽可能接近子机位的第一个镜头索引。
- 逻辑一致性：机位树应无环，避免循环依赖。如果某个机位被多个潜在父级包含，选择最佳匹配（基于景别和内容）。如果没有合适的父级机位，则输出 None。
- 当没有更广的视角时，选择视野重叠最大的镜头作为父级（信息重叠最多的那个），或者一个镜头也可以作为反打镜头的父级。当两个机位可以互为父级时，选择索引较小的作为索引较大的机位的父级。
- 只能有一个机位没有父级。
- 描述镜头中丢失的元素时，仔细比较父级镜头和子级镜头的细节。例如，父级镜头是角色 A 和角色 B 面对面的中景（两者都侧对镜头），而子级镜头是角色 A 的特写（角色 A 正对镜头）。在这种情况下，子级镜头缺少角色 A 的正面信息。
- 第一个机位必须是机位树的根节点。
"""


human_prompt_template_select_reference_camera = \
"""
<CAMERA_SEQ>
{camera_seq_str}
</CAMERA_SEQ>
"""


class CameraParentItem(BaseModel):
    parent_cam_idx: Optional[int] = Field(
        default=None,
        description="父级机位的索引。如果该机位没有父级（例如根机位），则设为 None。",
        examples=[0, 1, None],
    )
    parent_shot_idx: Optional[int] = Field(
        default=None,
        description="依赖的镜头索引。如果该机位没有父级（例如根机位），则设为 None。",
        examples=[0, 3, None],
    )
    reason: str = Field(
        description="选择父级机位的原因。如果该机位没有父级，则说明其为何是根机位。",
        examples=[
            "父级镜头的视野覆盖了子级镜头的视野（从中景到特写）",
            "父级镜头和子级镜头具有正反打关系。",
            "CAMERA_0（Shot 0）建立了整个场景，包含所有角色和场景设置。它是根机位。",
        ],
    )
    is_parent_fully_covers_child: Optional[bool] = Field(
        default=None,
        description="父级机位是否完全覆盖了子级机位的内容。如果该机位没有父级，则设为 None。",
        examples=[True, False, None],
    )
    missing_info: Optional[str] = Field(
        default=None,
        description="子级镜头中未被父级镜头覆盖的缺失元素。如果父级镜头完全覆盖子级镜头，则设为 None。",
        examples=[
            "Alice 的正面视角。",
            None,
        ],
    )

class CameraTreeResponse(BaseModel):
    camera_parent_items: List[Optional[CameraParentItem]] = Field(
        description="每个机位的父级机位项。如果某个机位没有父级，则设为 None。列表长度应与机位数量相同。",
    )



class CameraImageGenerator:

    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
    ):
        self.chat_model = chat_model
        self.image_generator = image_generator
        self.video_generator = video_generator


    async def construct_camera_tree(
        self,
        cameras: List[Camera],
        shot_descs: List[Union[ShotDescription, ShotBriefDescription]],
    ) -> List[Camera]:
        parser = PydanticOutputParser(pydantic_object=CameraTreeResponse)
        shot_desc_by_idx = {shot.idx: shot for shot in shot_descs}

        camera_seq_str = "<CAMERA_SEQ>\n"
        for cam in cameras:
            camera_seq_str += f"<CAMERA_{cam.idx}>\n"
            for shot_idx in cam.active_shot_idxs:
                shot_desc = shot_desc_by_idx.get(shot_idx)
                if shot_desc is None:
                    raise ValueError(f"相机 {cam.idx} 引用了不存在的镜头 {shot_idx}")
                camera_seq_str += f"Shot {shot_idx}: {shot_desc.visual_desc}\n"
            camera_seq_str += f"</CAMERA_{cam.idx}>\n"
        camera_seq_str += "</CAMERA_SEQ>"

        messages = [
            SystemMessage(content=system_prompt_template_select_reference_camera.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=human_prompt_template_select_reference_camera.format(camera_seq_str=camera_seq_str)),
        ]

        chain = self.chat_model | parser
        response: CameraTreeResponse = await chain.ainvoke(messages)
        parent_items = response.camera_parent_items
        if len(parent_items) != len(cameras):
            raise ValueError(f"相机树响应长度不匹配：期望 {len(cameras)}，实际 {len(parent_items)}")

        valid_camera_idxs = {cam.idx for cam in cameras}
        valid_shot_idxs = set(shot_desc_by_idx)
        parent_by_camera = {}
        for cam, parent_cam_item in zip(cameras, parent_items):
            parent_cam_idx = parent_cam_item.parent_cam_idx if parent_cam_item is not None else None
            parent_shot_idx = parent_cam_item.parent_shot_idx if parent_cam_item is not None else None
            if parent_cam_idx is not None and parent_cam_idx not in valid_camera_idxs:
                raise ValueError(f"相机 {cam.idx} 的父相机 {parent_cam_idx} 无效")
            if parent_cam_idx == cam.idx:
                raise ValueError(f"相机 {cam.idx} 不能是自己的父相机")
            if parent_shot_idx is not None and parent_shot_idx not in valid_shot_idxs:
                raise ValueError(f"相机 {cam.idx} 的父镜头 {parent_shot_idx} 无效")
            parent_by_camera[cam.idx] = parent_cam_idx

        for cam in cameras:
            seen = set()
            current = cam.idx
            while parent_by_camera.get(current) is not None:
                current = parent_by_camera[current]
                if current in seen:
                    raise ValueError(f"相机树包含涉及相机 {cam.idx} 的环")
                seen.add(current)

        for cam, parent_cam_item in zip(cameras, parent_items):
            cam.parent_cam_idx = parent_cam_item.parent_cam_idx if parent_cam_item is not None else None
            cam.parent_shot_idx = parent_cam_item.parent_shot_idx if parent_cam_item is not None else None
            cam.reason = parent_cam_item.reason if parent_cam_item is not None else None
            cam.is_parent_fully_covers_child = parent_cam_item.is_parent_fully_covers_child if parent_cam_item is not None else None
            cam.missing_info = parent_cam_item.missing_info if parent_cam_item is not None else None
        return cameras


    async def generate_transition_video(
        self,
        first_shot_visual_desc: str,
        second_shot_visual_desc: str,
        first_shot_ff_path: str,
        progress=None,
    ) -> VideoOutput:

        prompt = f"两个镜头。两个镜头之间的转场是直接切换。两个镜头的风格应保持一致。"
        prompt += f"\n第一个镜头描述：{first_shot_visual_desc}。"
        prompt += f"\n第二个镜头描述：{second_shot_visual_desc}。"
        reference_image_paths = [first_shot_ff_path]
        video_output = await self.video_generator.generate_single_video(
            prompt=prompt,
            reference_image_paths=reference_image_paths,
            progress=progress,
        )
        return video_output


    def get_new_camera_image(
        self,
        transition_video_path: str,
    ) -> ImageOutput:
        video = open_video(transition_video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector())
        scene_manager.detect_scenes(video, show_progress=False)
        scene_list = scene_manager.get_scene_list()
        output_dir = os.path.join(os.path.dirname(transition_video_path), "cache")
        os.makedirs(output_dir, exist_ok=True)
        split_video_ffmpeg(transition_video_path, scene_list, output_dir, show_progress=True)


        video_name = os.path.basename(transition_video_path).split('.')[0]
        second_video_path = os.path.join(output_dir, f"{video_name}-Scene-002.mp4")
        if os.path.exists(second_video_path):
            # 使用第二个镜头的第一帧作为新相机图片
            clip = VideoFileClip(second_video_path)
            ff = clip.get_frame(0)
            ff = Image.fromarray(ff.astype('uint8'), 'RGB')
            return ImageOutput(fmt="pil", ext="png", data=ff)
        else:
            # 改用转场视频的最后一帧
            clip = VideoFileClip(transition_video_path)
            lf_time = clip.duration - (1 / clip.fps)
            lf_time = max(0, lf_time)
            lf = clip.get_frame(lf_time)
            lf = Image.fromarray(lf.astype('uint8'), 'RGB')
            return ImageOutput(fmt="pil", ext="png", data=lf)


    async def generate_first_frame(
        self,
        shot_desc: ShotDescription,
        character_portrait_path_and_text_pairs: List[Tuple[str, str]],
    ) -> ImageOutput:
        prompt = ""
        reference_image_paths = []
        for i,(path, text )in enumerate(character_portrait_path_and_text_pairs):
            prompt += f"Image {i}: {text}\n"
            reference_image_paths.append(path)
        prompt += f"根据以下描述生成图片：{shot_desc.ff_desc}。"
        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            reference_image_paths=reference_image_paths,
            size="1600x900",
        )
        return image_output



def _validate_camera_tree(cameras: List[Camera]) -> None:
    """拒绝会导致帧生成死锁的父级分配。"""
    by_idx = {cam.idx: cam for cam in cameras}
    for cam in cameras:
        if cam.parent_cam_idx is None:
            continue
        if cam.parent_cam_idx == cam.idx:
            raise ValueError(f"相机 {cam.idx} 将自己列为父相机。")
        if cam.parent_cam_idx not in by_idx:
            raise ValueError(f"相机 {cam.idx} 引用了未知的父相机 {cam.parent_cam_idx}。")
    for cam in cameras:
        seen = set()
        current = cam
        while current.parent_cam_idx is not None:
            if current.idx in seen:
                raise ValueError(f"在相机父图中检测到涉及相机 {current.idx} 的环。")
            seen.add(current.idx)
            current = by_idx[current.parent_cam_idx]