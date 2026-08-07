from langchain_community.vectorstores import FAISS
from interfaces import Event, Scene
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Tuple, Dict
from langchain_core.output_parsers import PydanticOutputParser
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser as PydanticOutputParser
from tenacity import retry, stop_after_attempt
import logging

system_prompt_template_get_next_scene = \
"""
你是一名专业的编剧，专精于将文学作品改编为结构化的剧本场景。你的任务是分析小说中的事件描述，并将其转化为引人入胜的剧本场景，同时利用相关上下文并忽略无关信息。

**任务**
根据提供的输入，生成剧本改编的下一场戏。每个场景必须包含：
- 环境：场景标题和详细描述
- 角色：出现在场景中的角色列表，包括其静态特征（如面部特征、体型）、动态特征（如服装、配饰）和可见性状态
- 剧本：以标准剧本格式呈现的角色动作和对话

**输入**
- 事件描述：待改编事件的清晰、简洁摘要。事件描述被包裹在 <EVENT_DESCRIPTION_START> 和 <EVENT_DESCRIPTION_END> 标签之间。
- 上下文片段：通过 RAG 从小说中检索的多个摘录。这些可能包含不相关的段落。忽略任何与事件不直接相关的内容。上下文片段序列被包裹在 <CONTEXT_FRAGMENTS_START> 和 <CONTEXT_FRAGMENTS_END> 标签之间。序列中的每个片段被包裹在其自己的 <FRAGMENT_N_START> 和 <FRAGMENT_N_END> 标签内，其中 N 是片段编号。
- 前序场景（若有）：已改编的场景，用于提供上下文（可能为空）。前序场景序列被包裹在 <PREVIOUS_SCENES_START> 和 <PREVIOUS_SCENES_END> 标签之间。每个场景被包裹在其自己的 <SCENE_N_START> 和 <SCENE_N_END> 标签内，其中 N 是场景编号。

**输出**
{format_instructions}

**指导原则**
1. 基于提供的上下文片段提取场景。力求保留原文含义和对话，不做随意更改。改编时，确保每一句对话在原文中都有对应的或可推导的依据。
2. 关注相关性：仅使用与事件描述直接对齐的上下文片段。忽略任何不相关的段落。
3. 对话与动作：将描述性散文转化为可操作的台词和对话。如果上下文中隐含但未明确说明，可创造最少必要对话。
4. 简洁性：保持描述简短且视觉化。避免散文式的解释。
5. 格式一致性：确保行业标准的剧本结构。
6. 隐含推断：如果上下文片段缺乏确切细节，根据事件描述或更广泛的叙事上下文进行逻辑推断。
7. 无无关内容：不要包含与核心事件无关的场景、角色或对话。
8. 角色必须是个人，而非群体（如一群围观者或救援队）。
9. 当地点或时间发生变化时，应创建新的场景。场景总数不应超过 5 个！！！
10. 输出值中的语言应与输入语言一致。
"""


human_prompt_template_get_next_scene = \
"""
<EVENT_DESCRIPTION_START>
{event_description}
<EVENT_DESCRIPTION_END>

<CONTEXT_FRAGMENTS_START>
{context_fragments}
<CONTEXT_FRAGMENTS_END>

<PREVIOUS_SCENES_START>
{previous_scenes}
<PREVIOUS_SCENES_END>
"""




class SceneExtractor:
    def __init__(
        self,
        api_key,
        base_url,
        chat_model,
    ):
        self.chat_model = init_chat_model(
            model=chat_model,
            api_key=api_key,
            base_url=base_url,
            model_provider="openai",
        )

    @retry(
        stop=stop_after_attempt(5),
        after=lambda retry_state: logging.warning(f"因错误正在重试 SceneExtractor.get_next_scene: {retry_state.outcome.exception()}"),
    )
    async def get_next_scene(
        self,
        relevant_chunks: List[str],
        event: Event,
        previous_scenes: List[Scene]
    ) -> Scene:

        context_fragments_str = "\n".join([f"<FRAGMENT_{i}_START>\n{chunk}\n<FRAGMENT_{i}_END>" for i, chunk in enumerate(relevant_chunks)])

        previous_scenes_str = "\n".join([f"<SCENE_{i}_START>\n{scene}\n<SCENE_{i}_END>" for i, scene in enumerate(previous_scenes)])

        parser = PydanticOutputParser(pydantic_object=Scene)

        messages = [
            SystemMessage(
                content=system_prompt_template_get_next_scene.format(
                    format_instructions=parser.get_format_instructions(),
                ),
            ),
            HumanMessage(
                content=human_prompt_template_get_next_scene.format(
                    event_description=str(event),
                    context_fragments=context_fragments_str,
                    previous_scenes=previous_scenes_str,
                )
            )
        ]

        chain = self.chat_model | parser
        scene = await chain.ainvoke(messages)
        return scene