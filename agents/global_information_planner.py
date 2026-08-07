import os
import logging
import asyncio
from typing import List, Tuple, Dict, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from langchain.output_parsers import PydanticOutputParser
from interfaces import Event, Scene
from interfaces import CharacterInScene, CharacterInEvent, CharacterInNovel
from tenacity import retry, stop_after_attempt


system_prompt_template_merge_characters_across_scenes_in_event = \
"""
你是一名专业的剧本分析和角色融合专家。你的角色是智能分析多个剧本场景，识别不同场景中代表同一实体的角色，并将它们合并为具有一致标识符的统一角色列表。

**任务**
处理输入的场景，每个场景包含一个剧本和角色及其名称和特征。识别并合并不同场景中逻辑上相同的角色，即使它们有不同的名称或描述上的细微差异。输出整个事件的合并角色列表。列表中的每个角色必须有唯一的标识符，以及他们出现的场景编号和每个场景中使用的名称。你还需要将相同角色的静态特征聚合在一起。

**输入**
一系列场景。每个场景被包裹在 <SCENE_N_START> 和 <SCENE_N_END> 标签之间，其中 N 是场景编号（从 0 开始）。
每个场景包含一个剧本脚本和一个角色名称序列。
剧本脚本被包裹在 <SCRIPT_START> 和 <SCRIPT_END> 标签之间。
角色序列被包裹在 <CHARACTERS_START> 和 <CHARACTERS_END> 标签之间。列表中的每个角色被包裹在 <CHARACTER_M_START> 和 <CHARACTER_M_END> 标签之间，其中 M 是角色编号（从 0 开始）。

以下是一个场景的示例：

<SCENE_0_START>

<SCRIPT_START>
John 进入房间，看到了 Mary。
John：嗨 Mary，你好吗？
Mary：我很好，John。谢谢关心！
<SCRIPT_END>

<CHARACTERS_START>

<CHARACTER_0_START>
John [visible]
static features: John 是一个高个子男人，黑色短发，棕色眼睛。
dynamic features: 穿着蓝色衬衫和黑色裤子。
<CHARACTER_0_END>

<CHARACTER_1_START>
Mary [visible]
static features: Mary 是一个年轻女性，棕色长发，绿色眼睛。
dynamic features: 穿着花卉连衣裙和牛仔夹克。
<CHARACTER_1_END>

<CHARACTERS_END>

<SCENE_0_END>



**输出**
{format_instructions}

**指导原则**
1. 角色融合：分析上下文线索（如对话风格、角色在情节中的作用、关系、描述）来判断不同场景中的角色是否为同一个人，即使名称不同。
2. 唯一标识符：为每个合并后的角色分配一个一致的唯一 ID（例如主要/规范名称）。如果可能，使用最频繁或上下文最合适的名称作为标识符。
3. 场景映射：对于每个角色，列出他们出现的所有场景以及每个场景中使用的确切名称。
4. 完整性：确保所有场景中的所有角色都包含在最终列表中。没有重复、遗漏或多出的角色。
5. 如果某个角色在不同场景中发生显著变化，则需要将其拆分为不同的角色。例如，如果角色 A 在场景 0 中是儿童，但在场景 1 中是成人，则应将他们分为两个不同的角色（意味着需要两个不同的演员来扮演他们）。
6. 输出值中的语言应与输入文本一致。
"""


human_prompt_template_merge_characters_across_scenes_in_event = \
"""
{scenes_sequence}
"""

class MergeCharactersAcrossScenesInEventResponse(BaseModel):
    characters: List[CharacterInEvent] = Field(
        description="合并后的角色列表，包含其标识符",
    )




system_prompt_template_merge_characters_to_existing_characters_in_novel = \
"""
你是一名信息整合专家，擅长准确识别、匹配和合并角色信息。你的职责是确保角色属性的一致性，并高效维护和更新全局角色列表。

**任务**
将当前事件中提取的角色列表（可能包含新角色或现有角色）合并到全局角色列表中。对于现有角色，确保其特征描述保持一致；对于新角色，将其添加到全局列表中。

**输入**
1. 小说中的现有角色：小说中已存在的角色列表，每个角色有唯一的索引、标识符和静态特征。列表被包裹在 <EXISTING_CHARACTERS_START> 和 <EXISTING_CHARACTERS_END> 标签之间。列表中的每个角色被包裹在 <CHARACTER_P_START> 和 <CHARACTER_P_END> 标签之间，其中 P 是角色编号（从 0 开始）。
2. 当前事件中的角色：当前事件中识别的角色列表，每个角色有索引、标识符、活跃场景和静态特征。列表被包裹在 <EVENT_CHARACTERS_START> 和 <EVENT_CHARACTERS_END> 标签之间。列表中的每个角色被包裹在 <CHARACTER_Q_START> 和 <CHARACTER_Q_END> 标签之间，其中 Q 是角色编号（从 0 开始）。


**输出**
{format_instructions}

**指导原则**
1. 特征一致性：严格比较当前事件角色与现有角色的特征。有些角色的标识符可能与现有角色标识符相同，但特征不同，例如年轻和年老。你需要将它们区分为两个独立的角色。
2. 高效合并：避免重复角色，确保列表保持简洁。
3. 特征更新：如果基于当前事件的新信息，现有角色的特征被扩展或修改，则相应地更新其描述。
"""

human_prompt_template_merge_characters_to_existing_characters_in_novel = \
"""
<EXISTING_CHARACTERS_START>
{existing_characters_in_novel}
<EXISTING_CHARACTERS_END>

<EVENT_CHARACTERS_START>
{characters_in_event}
<EVENT_CHARACTERS_END>
"""


class CharacterForMergingToNovel(BaseModel):
    index_in_event: int = Field(
        description="当前事件角色列表中角色的索引。",
        examples=[0, 1, 2],
    )
    index_in_novel: int = Field(
        description="小说现有角色列表中角色的索引。如果是新角色，则设为 -1。",
        examples=[0, 7, -1],
    )
    identifier_in_novel: str = Field(
        description="该角色在小说中的唯一标识符。如果是新角色，确保名称不与现有角色冲突。如果不是新角色，则应与现有角色列表中的标识符匹配。",
        examples=["Alice", "Bob the Builder"],
    )
    modified_features: str = Field(
        description="合并后角色的修改静态特征。如果是新角色，则为完整的静态特征。如果是现有角色且其特征被扩展或修改，则填写完整的修改后特征。如果是现有角色且其特征保持不变，则与现有角色的静态特征相同。",
    )

class MergeCharactersToExistingCharactersInNovelResponse(BaseModel):
    characters: List[CharacterForMergingToNovel] = Field(
        description="事件中角色及其对应小说现有角色索引的列表。如果是新角色，index_in_novel 应为 -1。此列表中的角色数量应与事件中的角色数量相同。",
    )



class GlobalInformationPlanner:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        chat_model: str,
    ):
        self.chat_model = init_chat_model(
            model=chat_model,
            model_provider="openai",
            api_key=api_key,
            base_url=base_url,
        )

    @retry(
        stop=stop_after_attempt(3),
        after=lambda retry_state: logging.warning(f"因 {retry_state.outcome.exception()} 正在重试"),
    )
    async def merge_characters_across_scenes_in_event(
        self,
        event_idx: int,
        scenes: List[Scene],  # Scene.characters is List[CharacterInScene]
    ) -> List[CharacterInEvent]:
        scenes_sequence_str = ""
        for scene in scenes:
            scene_str = f"<SCENE_{scene.idx}_START>\n"
            scene_str += "<SCRIPT_START>\n"
            scene_str += scene.script + "\n"
            scene_str += "<SCRIPT_END>\n\n"
            scene_str += "<CHARACTERS_START>\n"
            for character in scene.characters:
                scene_str += f"<CHARACTER_{character.idx}_START>\n"
                scene_str += str(character)
                scene_str += f"<CHARACTER_{character.idx}_END>\n"
            scene_str += "<CHARACTERS_END>\n"
            scene_str += f"<SCENE_{scene.idx}_END>\n"
            scenes_sequence_str += scene_str

        parser = PydanticOutputParser(pydantic_object=MergeCharactersAcrossScenesInEventResponse)

        messages = [
            SystemMessage(
                content=system_prompt_template_merge_characters_across_scenes_in_event.format(
                    format_instructions=parser.get_format_instructions(),
                ),
            ),
            HumanMessage(
                content=human_prompt_template_merge_characters_across_scenes_in_event.format(
                    scenes_sequence=scenes_sequence_str,
                )
            )
        ]

        chain = self.chat_model | parser
        response: MergeCharactersAcrossScenesInEventResponse = await chain.ainvoke(messages)
        characters_in_event = response.characters

        # 检查输出是否有效
        flags = [{c.identifier_in_scene: False for c in s.characters} for s in scenes]

        # 检查所有角色标识符是否能在场景中找到
        for character in characters_in_event:
            for scene_idx, identifier_in_scene in character.active_scenes.items():
                if identifier_in_scene not in [c.identifier_in_scene for c in scenes[scene_idx].characters]:
                    raise ValueError(f"在事件 {event_idx} 的场景 {scene_idx} 中未找到角色 {identifier_in_scene}")
                else:
                    flags[scene_idx][identifier_in_scene] = True

        # 检查是否包含所有角色
        for scene_idx, flag in enumerate(flags):
            for identifier_in_scene, included in flag.items():
                if not included:
                    raise ValueError(f"事件 {event_idx} 场景 {scene_idx} 中的角色 {identifier_in_scene} 未包含在合并后的角色中")

        return characters_in_event

    @retry(
        stop=stop_after_attempt(3),
        after=lambda retry_state: logging.warning(f"因 {retry_state.outcome.exception()} 正在重试"),
    )
    def merge_characters_to_existing_characters_in_novel(
        self,
        event_idx: int,
        existing_characters_in_novel: List[CharacterInNovel],
        characters_in_event: List[CharacterInEvent],
    ) -> List[CharacterInNovel]:
        existing_characters_str = ""
        for character in existing_characters_in_novel:
            existing_characters_str += f"<CHARACTER_{character.index}_START>\n"
            existing_characters_str += str(character)
            existing_characters_str += f"<CHARACTER_{character.index}_END>\n"

        characters_in_event_str = ""
        for character in characters_in_event:
            characters_in_event_str += f"<CHARACTER_{character.index}_START>\n"
            characters_in_event_str += character.identifier_in_event + "\n"
            characters_in_event_str += "Static features: " + character.static_features + "\n"
            characters_in_event_str += f"<CHARACTER_{character.index}_END>\n"

        parser = PydanticOutputParser(pydantic_object=MergeCharactersToExistingCharactersInNovelResponse)

        messages = [
            SystemMessage(
                content=system_prompt_template_merge_characters_to_existing_characters_in_novel.format(
                    format_instructions=parser.get_format_instructions(),
                ),
            ),
            HumanMessage(
                content=human_prompt_template_merge_characters_to_existing_characters_in_novel.format(
                    existing_characters_in_novel=existing_characters_str,
                    characters_in_event=characters_in_event_str,
                )
            )
        ]

        chain = self.chat_model | parser
        response: MergeCharactersToExistingCharactersInNovelResponse = chain.invoke(messages)

        for character in response.characters:
            if character.index_in_novel == -1:
                # 新角色，添加到现有角色列表
                new_character = CharacterInNovel(
                    index=len(existing_characters_in_novel),
                    identifier_in_novel=character.identifier_in_novel,
                    static_features=character.modified_features,
                    active_events={event_idx: characters_in_event[character.index_in_event].identifier_in_event},
                )
                existing_characters_in_novel.append(new_character)
            else:
                existing_characters_in_novel[character.index_in_novel].static_features = character.modified_features
                existing_characters_in_novel[character.index_in_novel].active_events.update({event_idx: characters_in_event[character.index_in_event].identifier_in_event})

        return existing_characters_in_novel