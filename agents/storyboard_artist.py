from typing import List, Optional, Literal
import asyncio
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt

from langchain.chat_models.base import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from interfaces import CharacterInScene, ShotDescription, ShotBriefDescription

from utils.retry import after_func



system_prompt_template_design_storyboard = \
"""
[角色]
你是一名专业的故事板艺术家，具备以下核心技能：
- 剧本分析：能够快速解读剧本文本，识别场景设置、角色动作、对话、情感和叙事节奏。
- 视觉化：擅长将文字描述转化为视觉画面，包括构图、光线和空间安排。
- 故事板制作：精通电影语言，如镜头类型（例如特写、中景、远景）、摄影机角度（例如俯视、平视）、摄影机运动（例如推拉、摇移）和转场。
- 叙事连续性：能够确保故事板序列在逻辑上流畅，突出关键情节点，并保持情感一致性。
- 技术知识：了解基本故事板格式和行业标准，例如使用编号镜头和简洁描述。

[任务]
你的任务是根据用户提供的剧本（仅包含一个场景）设计完整的故事板。故事板应以文本形式呈现，清晰展示每个镜头的视觉元素和叙事流程，帮助用户可视化场景。

[输入]
用户将提供以下输入。
- 剧本：包含对话、动作描述和场景设置的完整场景剧本。剧本仅聚焦于一个场景；无需处理多个场景转场。剧本输入被包裹在 <SCRIPT> 和 </SCRIPT> 之间。
- 角色列表：描述每个角色基本信息的列表，如姓名、性格特征、外貌（如果相关）。角色列表被包裹在 <CHARACTERS> 和 </CHARACTERS> 之间。
- 用户需求：用户需求（可选）被包裹在 <USER_REQUIREMENT> 和 </USER_REQUIREMENT> 之间，可能包括：
    - 目标受众（例如儿童、青少年、成人）。
    - 故事板风格（例如写实、卡通、抽象）。
    - 期望的镜头数量（例如"不超过 10 个镜头"）。
    - 其他具体指示（例如强调角色的动作）。

[输出]
{format_instructions}

[指导原则]
- 确保所有输出值（除键外）的语言与剧本使用的语言一致。
- 每个镜头必须有清晰的叙事目的——例如建立场景、展示角色关系或突出反应。
- 有意识地使用电影语言：特写用于情感，广角用于上下文，不同的角度用于引导观众的注意力。
- 设计新镜头时，首先考虑是否可以使用现有的机位拍摄。只有当景别、角度和焦点有显著差异时，才引入新机位。如果摄影机有显著移动，则之后不能再使用该机位。
- 保持视觉描述和说话者字段中的角色名称与角色列表一致。在视觉描述中，将名称括在尖括号中（例如 <Alice>），但在对话或说话者字段中不要使用。
- 描述视觉元素时，需要指明元素在画面中的位置。例如，角色 A 在画面左侧，面向右侧，前面有一张桌子。桌子位于画面中央偏左的位置。确保不包含不可见的元素。例如，如果某人无法被看到，不要描述关着的门后面的人。
- 避免在视觉描述中出现不安全内容（暴力、歧视等）。在必要时使用声音或暗示性意象等间接方法，并用敏感元素替代（例如用番茄酱代替血迹）。
- 每个镜头每个角色最多分配一句对话。每句对话应对应一个镜头。
- 每个镜头需要独立的描述，不相互引用。
- 当镜头聚焦于角色时，描述具体关注哪个身体部位。
- 描述角色时，需要指明他们面对的方向。
"""


human_prompt_template_design_storyboard = \
"""
<SCRIPT>
{script_str}
</SCRIPT>

<CHARACTERS>
{characters_str}
</CHARACTERS>

<USER_REQUIREMENT>
{user_requirement_str}
</USER_REQUIREMENT>
"""



system_prompt_template_decompose_visual_description = \
"""
[角色]
你是一名专业的视觉文本分析师，精通电影语言和镜头叙事。你的专长在于将完整的镜头描述准确地分解为三个核心组成部分：静态首帧、静态末帧和连接它们的动态运动。

[任务]
你的任务是严格且富有洞察力地将用户提供的镜头视觉文本描述分解为三个不同的部分：
- 首帧描述：描述镜头最开始时的静态图像。聚焦于构图元素、初始角色姿势、环境布局、光线、颜色等静态视觉方面。
- 末帧描述：描述镜头最末尾时的静态图像。同样聚焦于静态构图，但必须反映由摄影机运动或内部元素运动引起的最终状态变化。
- 运动描述：描述首帧和末帧之间发生的所有运动。这包括摄影机运动（例如静态、推近、拉远、摇移、跟踪、跟随、俯仰等）和镜头内元素的运动（例如角色移动、物体位移、光线变化等）。这是整个描述中最动态的部分。对于角色的运动和变化，你不能直接使用角色名称来指代，而要使用角色的外部特征，尤其是显眼的服装特征来指代。

[输入]
你将收到一个镜头的单一视觉文本描述，该描述通常隐含或明确包含起始状态、运动过程和结束状态的信息。
此外，你将收到一个可能的角色序列，每个角色包含标识符和特征。
- 描述被包裹在 <VISUAL_DESC> 和 </VISUAL_DESC> 之间。
- 角色列表被包裹在 <CHARACTERS> 和 </CHARACTERS> 之间。


[输出]
{format_instructions}

[指导原则]
- 确保所有输出值（除键外）的语言与剧本使用的语言一致。
- 确保首帧和末帧描述是纯粹的"快照"，不包含进行中的动作（例如"他正准备站起来"是不可接受的；应为"他坐在椅子上，身体微微前倾"）。
- 在运动描述中，必须明确区分摄影机运动和画面内运动。尽可能使用专业的电影术语（如移动车镜头、摇摄、变焦等）来描述摄影机运动。
- 在运动描述中，不能直接使用角色名称来指代角色，而应使用角色的可见特征来指代。例如，"Alice 正在走路"是不可接受的；应为"Alice（短发，穿着绿色连衣裙）正在走路"。
- 末帧描述必须在逻辑上与首帧描述和运动描述一致。运动部分描述的所有动作都应反映在末帧的静态图像中。
- 如果输入描述在某个细节上模糊不清，你可以根据上下文做出合理的推断和补充，使三个部分都完整流畅。但核心要素必须严格遵循输入文本。
- 使用准确、简洁、专业的描述性语言。避免过于文学化的修辞，如隐喻或情感渲染；专注于提供可视觉化的信息。
- 与输入的视觉描述类似，首帧和末帧描述应包括景别、角度、构图等细节。
- 以下是镜头内三种变化类型（非镜头间变化）：
（1）'large'情况通常涉及夸张的过渡镜头，意味着构图和焦点发生显著变化，例如从广角镜头平滑过渡到特写。通常伴随显著的摄影机运动（例如无人机视角穿越城市）。
（2）'medium'情况通常涉及新角色的引入以及角色从背面转向正面（面向摄影机）。
（3）'small'情况通常涉及微小变化，如表情变化、现有角色的运动和姿势变化（例如走路、坐下、站起）、适度的摄影机运动（例如摇摄、俯仰、跟踪）。
- 描述角色时，需要指明他们面对的方向。
- 第一个镜头必须建立整体场景环境，使用尽可能宽的景别。
- 尽可能使用少数机位。
"""


human_prompt_template_decompose_visual_description = \
"""
<VISUAL_DESC>
{visual_desc}
</VISUAL_DESC>

<CHARACTERS>
{characters_str}
</CHARACTERS>
"""


class VisDescDecompositionResponse(BaseModel):
    ff_desc: str = Field(
        description="镜头首帧的详细描述，捕捉初始视觉元素和构图。",
    )
    ff_vis_char_idxs: List[int] = Field(
        description="在镜头首帧中可见的字符索引列表，对应输入中提供的角色列表。",
        examples=[[0], [1], [0, 1], []]
    )
    lf_desc: str = Field(
        description="镜头末帧的详细描述，捕捉结束时的视觉元素和构图。",
    )
    lf_vis_char_idxs: List[int] = Field(
        description="在镜头末帧中可见的字符索引列表，对应输入中提供的角色列表。",
        examples=[[0], [1], [0, 1], []]
    )
    motion_desc: str = Field(
        description="镜头的运动描述。描述镜头内的动态视觉变化（摄影机运动和画面内元素的运动）",
        examples=[
            "静态摄影机。Alice（短发，穿着绿色连衣裙）正走向摄影机。",
            "从中景推近到特写。Bob（有胡须，穿着白色T恤）对着摄影机微笑。",
        ]
    )
    variation_type: Literal["large", "medium", "small"] = Field(
        description="表示首帧与末帧之间的变化程度。",
    )
    variation_reason: str = Field(
        description="镜头变化类型的原因。",
        examples=[
            "这是一个从天空到地面的平滑过渡镜头。镜头内容发生显著变化，因此变化类型为 large。",
            "与首帧相比，末帧出现了一个新角色，构图没有显著变化。因此变化类型为 medium。",
            "与首帧相比，构图只有微小变化。因此变化类型为 small。",
            "这个镜头只展示了 Alice 说话和她面部表情的变化，因此变化类型为 small。",
        ],
    )



class StoryboardArtist:
    def __init__(
        self,
        chat_model: BaseChatModel,
    ):
        self.chat_model = chat_model


    @retry(stop=stop_after_attempt(3), after=after_func)
    async def design_storyboard(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: Optional[str] = None,
        retry_timeout: int = 150,
    ) -> List[ShotBriefDescription]:

        class StoryboardResponse(BaseModel):
            storyboard: List[ShotBriefDescription] = Field(
                description="场景的完整故事板，包括每个镜头的视觉和音频描述。",
            )

        script_str = script.strip()
        characters_str = "\n".join([f"Character {index}: {char}" for index, char in enumerate(characters)])
        user_requirement_str = user_requirement.strip() if user_requirement else ""

        parser = PydanticOutputParser(pydantic_object=StoryboardResponse)
        messages = [
            ('system', system_prompt_template_design_storyboard.format(format_instructions=parser.get_format_instructions())),
            ('human', human_prompt_template_design_storyboard.format(script_str=script_str, characters_str=characters_str, user_requirement_str=user_requirement_str)),
        ]
        chain = self.chat_model | parser
        response: StoryboardResponse = await asyncio.wait_for(
            chain.ainvoke(messages),
            timeout=retry_timeout,
        )
        storyboard = response.storyboard

        return storyboard




    @retry(stop=stop_after_attempt(3), after=after_func)
    async def decompose_visual_description(
        self,
        shot_brief_desc: ShotBriefDescription,
        characters: List[CharacterInScene],
        retry_timeout: int = 150,
    ) -> ShotDescription:
        parser = PydanticOutputParser(pydantic_object=VisDescDecompositionResponse)
        prompt_template = ChatPromptTemplate.from_messages(
            [
                ('system', system_prompt_template_decompose_visual_description),
                ('human', human_prompt_template_decompose_visual_description),
            ]
        )
        chain = prompt_template | self.chat_model | parser

        visual_desc = shot_brief_desc.visual_desc.strip()

        characters_str = "\n".join([f"{char.identifier_in_scene}: (static) {char.static_features}; (dynamic) {char.dynamic_features}" for char in characters])

        decomposition: VisDescDecompositionResponse = await asyncio.wait_for(
            chain.ainvoke(
                input={
                    "format_instructions": parser.get_format_instructions(),
                    "visual_desc": visual_desc,
                    "characters_str": characters_str,
                },
            ),
            timeout=retry_timeout,
        )

        validate_char_idxs(decomposition.ff_vis_char_idxs, len(characters), "ff_vis_char_idxs")
        validate_char_idxs(decomposition.lf_vis_char_idxs, len(characters), "lf_vis_char_idxs")

        return ShotDescription(
            idx=shot_brief_desc.idx,
            is_last=shot_brief_desc.is_last,
            cam_idx=shot_brief_desc.cam_idx,
            visual_desc=shot_brief_desc.visual_desc,
            variation_type=decomposition.variation_type,
            variation_reason=decomposition.variation_reason,
            ff_desc=decomposition.ff_desc,
            ff_vis_char_idxs=decomposition.ff_vis_char_idxs,
            lf_desc=decomposition.lf_desc,
            lf_vis_char_idxs=decomposition.lf_vis_char_idxs,
            motion_desc=decomposition.motion_desc,
            audio_desc=shot_brief_desc.audio_desc,
        )


def validate_char_idxs(idxs, num_characters, field_name):
    """拒绝 LLM 发的超出 [0, num_characters) 范围的角色索引。
    Negative values would silently select the wrong character via Python
    indexing; out-of-range values would crash deep inside the render gather.
    在此处抛出异常会让 decompose_visual_description 上的 @retry 重新请求。"""
    invalid = [idx for idx in idxs if idx < 0 or idx >= num_characters]
    if invalid:
        raise ValueError(
            f"{field_name} 包含无效的角色索引 {invalid}；"
            f"有效范围为 0..{num_characters - 1}"
        )