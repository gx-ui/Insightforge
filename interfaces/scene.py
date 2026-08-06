from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Tuple
from interfaces.environment import EnvironmentInScene
from interfaces.character import CharacterInScene


class Scene(BaseModel):
    idx: int = Field(
        description="场景索引，从 0 开始",
        examples=[0, 1, 2],
    )
    is_last: bool = Field(
        description="指示该场景是否为最后一个场景",
        examples=[False, True],
    )
    environment: EnvironmentInScene = Field(
        description="详细的场景设置，包括地点和时间",
    )
    characters: List[CharacterInScene] = Field(
        description="场景中出现的角色列表，以及它们的动态特征如服装和配饰",
    )
    script: str = Field(
        description="该场景的剧本，包括角色动作和对话。剧本中的角色名应用 <> 包裹，对话中的角色名除外。",
        examples=[
            "<Jane> paces nervously, clutching a letter. She turns to <John>.\n<Jane>: John, we need to leave tonight.\n<John> shakes his head, stepping toward the window.\n<John>: It's too dangerous.",
            "<Alice> sits quietly, observing the chaos around her. She whispers to <Bob>.\n<Alice>: Bob, do you think they'll find us here?\n<Bob> nods slowly, his expression grim."
        ],
    )

    def __str__(self):
        s = f"场景 {self.idx}:"
        s += f"\n环境: {str(self.environment)}"
        s += f"\n角色: {', '.join([str(c) for c in self.characters])}"
        s += f"\n剧本: \n{self.script}"
        return s



# 注意：Scene 类已废弃，请使用 shot_description 中的结构
#     index: int = Field(
#         description="场景在事件中的索引，从 0 开始"
#     )
#     character_indices: List[int] = Field(
#         description="该场景中出现的角色索引列表，包括主角、配角和群演。",
#     )
#     environment_index: int = Field(
#         description="场景发生的环境索引。"
#     )
#     key_items_indices: List[int] = Field(
#         default=[],
#         description="该场景中涉及的关键物品索引列表（若有）。",
#     )
#     script: str = Field(
#         description="场景的剧本，包括动作和对话"
#     )