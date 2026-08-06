from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict
from PIL import Image




class CharacterInScene(BaseModel):
    idx: int = Field(
        description="角色在场景中的索引，从 0 开始",
    )
    identifier_in_scene: str = Field(
        description="角色在该特定场景中的标识符，可能与基础标识符不同",
        examples=["Alice", "Bob the Builder"],
    )
    is_visible: bool = Field(
        description="指示该角色在该场景中是否可见",
        examples=[True, False],
    )
    static_features: str = Field(
        description="角色在该特定场景中的静态特征，如面部特征和体型等保持不变或很少改变的特征。若角色不可见，该字段可留空。",
        examples=[
            "Alice has long blonde hair and blue eyes, and is of slender build.",
            "Bob the Builder is a middle-aged man with a sturdy build.",
        ]
    )
    dynamic_features: Optional[str] = Field(
        default=None,
        description="角色在该特定场景中的动态特征，如服装和配饰等可能随场景变化的特征。若未提及，该字段可留空。若角色不可见，该字段应为 None。",
        examples=[
            "Wearing a red scarf and a black leather jacket",
        ]
    )

    def __str__(self):
        # Alice[可见]
        # 静态特征: Alice 有一头金色长发和蓝色眼睛，身材纤细。
        # 动态特征: 戴着红色围巾，穿着黑色皮夹克

        s = f"{self.identifier_in_scene}"
        s += "[可见]" if self.is_visible else "[不可见]"
        s += "\n"
        s += f"静态特征: {self.static_features}\n"
        s += f"动态特征: {self.dynamic_features}\n"

        return s



class CharacterInEvent(BaseModel):
    index: int = Field(
        description="角色在事件中的索引，从 0 开始",
    )
    identifier_in_event: str = Field(
        description="角色在该事件中的唯一标识符",
        examples=["Alice", "Bob the Builder"],
    )

    active_scenes: Dict[int, str] = Field(
        description="将场景索引映射到角色在特定场景中标识符的字典。",
        examples=[
            {0: "Alice", 2: "Alice in Wonderland", 5: "Alice"},
            {1: "Bob the Builder", 3: "Bob", 4: "Bob"},
        ]
    )

    static_features: str = Field(
        description="角色在事件中的静态特征，如面部特征和体型等保持不变或很少改变的特征。",
        examples=[
            "Alice has long blonde hair and blue eyes, and is of slender build. She often wears casual, comfortable clothing.",
            "Bob the Builder is a middle-aged man with a sturdy build. He typically wears a hard hat and work overalls.",
        ]
    )



class CharacterInNovel(BaseModel):
    index: int = Field(
        description="角色在小说中的索引，从 0 开始",
    )
    identifier_in_novel: str = Field(
        description="角色在小说中的唯一标识符",
        examples=["Alice", "Bob the Builder"],
    )

    active_events: Dict[int, str] = Field(
        description="将事件索引映射到角色在特定事件中标识符的字典。",
        examples=[
            {0: "Alice", 2: "Alice in Wonderland", 5: "Alice"},
            {1: "Bob the Builder", 3: "Bob", 4: "Bob"},
        ]
    )

    static_features: str = Field(
        description="角色在小说中的静态特征，如面部特征和体型等保持不变或很少改变的特征。",
        examples=[
            "Alice has long blonde hair and blue eyes, and is of slender build. She often wears casual, comfortable clothing.",
            "Bob the Builder is a middle-aged man with a sturdy build. He typically wears a hard hat and work overalls.",
        ]
    )