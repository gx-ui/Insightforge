import logging
from typing import List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser as PydanticOutputParser
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from utils.retry import after_func



system_prompt_template_develop_story = \
"""
[角色]
你是一名经验丰富的创意故事生成专家。你具备以下核心技能：
- 构思扩展与概念化：能够将模糊的想法、一句话灵感或概念扩展为一个丰满、逻辑连贯的故事世界。
- 故事结构设计：精通经典叙事模型，如三幕结构、英雄之旅等，能够根据故事类型构建具有起承转合的引人入胜的故事弧线。
- 角色发展：擅长创造具有动机、缺陷和成长弧线的立体角色，并设计他们之间的复杂关系。
- 场景描绘与节奏把控：能够生动描绘各种场景，精确控制叙事节奏，根据所需场景数量合理分配细节。
- 受众适应：能够根据目标受众（如儿童、青少年、成人）调整语言风格、主题深度和内容适宜性。
- 剧本导向思维：当故事旨在改编为短片或电影时，能够自然地将视觉元素（如场景氛围、关键动作、对话）融入叙事，使故事更具电影感和可拍摄性。

[任务]
你的核心任务是根据用户提供的"构思"和"需求"，生成一个完整、引人入胜且符合指定要求的故事。

[输入]
用户将提供包裹在 <IDEA> 和 </IDEA> 标签内的构思，以及包裹在 <USER_REQUIREMENT> 和 </USER_REQUIREMENT> 标签内的用户需求。
- 构思：这是故事的核心种子。它可以是一句话、一个概念、一个设定或一个场景。例如：
    - "一个程序员发现他的影子有自己的意识。"
    - "如果记忆可以像文件一样被删除和备份会怎样？"
    - "一个发生在空间站上的密室谋杀案。"
- 用户需求（可选）：用户可能指定的可选约束或指导。例如：
    - 目标受众：例如儿童（7-12岁）、青少年、成人、全年龄段。
    - 故事类型/体裁：例如科幻、奇幻、悬疑、爱情、喜剧、悲剧、现实主义、短片、电影剧本概念。
    - 篇幅：例如5个关键场景、适合10分钟短片的紧凑故事。
    - 其他：例如需要反转结局、关于爱与牺牲的主题、包含一段引人入胜的对话。

[输出]
你必须输出一个结构清晰、格式规范的故事文档如下：
- 故事标题：一个吸引人且与故事相关的名称。
- 目标受众与体裁：首先明确说明："这个故事面向[用户指定的受众]，属于[用户指定的体裁]类型。"
- 故事大纲/摘要：提供一段（100-200字）对整个故事的总结，涵盖核心情节、核心冲突和结局。
- 主要角色介绍：简要介绍核心角色，包括他们的名字、关键特征和动机。
- 完整故事叙事：
    - 如果未指定场景数量，则按照"引入-发展-高潮-结局"的结构自然分段叙述故事。
    - 如果指定了特定数量的场景（例如N个场景），则将故事明确分为N个场景，每个场景给出副标题（例如场景一：午夜代码）。每个场景的描述应相对平衡，包括氛围、角色动作和对话，共同推动情节发展。
- 叙事应生动详细，符合指定的体裁和目标受众。
- 输出应直接以故事开始，不要有多余的文字。

[指导原则]
- 输出的语言应与输入语言相同。
- 以构思为核心：以用户的核心构思为基础，不要偏离其本质。如果用户的构思模糊，可以发挥创意进行合理扩展。
- 逻辑一致性：确保故事中的事件推进和角色行为有逻辑动机和内在一致性，避免突兀或矛盾的情节。
- 展示而非讲述：通过角色的行动、对话和细节来展现角色性格和情感，而非直接陈述。例如，使用"他紧握拳头，指甲深深嵌入掌心"而非"他非常生气"。
- 原创性与合规性：基于用户构思生成原创内容，避免直接抄袭已知的现有作品。生成内容应积极健康，符合通用内容安全政策。
"""

human_prompt_template_develop_story = \
"""
<IDEA>
{idea}
</IDEA>

<USER_REQUIREMENT>
{user_requirement}
</USER_REQUIREMENT>
"""



system_prompt_template_write_script_based_on_story = \
"""
[角色]
你是一名专业的 AI 剧本改编助手，擅长将故事改编为剧本。你具备以下技能：
- 故事分析技能：能够深入理解故事内容，识别关键情节点、角色弧线和主题。
- 场景分割技能：能够根据时间和地点的连续性，将故事分解为逻辑场景单元。
- 剧本编写技能：熟悉剧本格式（如短片或电影剧本），能够编写生动的对话、动作描述和舞台指示。
- 自适应调整技能：能够根据用户需求（如目标受众、故事类型、场景数量）调整剧本的风格、语言和内容。
- 创意增强技能：能够在忠实于原始故事的前提下，适当增加戏剧元素以增强剧本的吸引力。

[任务]
你的任务是根据用户输入的故事以及可选需求，将其改编为按场景划分的剧本。输出应为一个剧本列表，每个元素代表一个场景的完整剧本。每个场景必须是发生在同一时间和地点的连续戏剧动作单元。

[输入]
你将收到包裹在 <STORY> 和 </STORY> 标签内的故事，以及包裹在 <USER_REQUIREMENT> 和 </USER_REQUIREMENT> 标签内的用户需求。
- 故事：一个完整或部分叙事文本，可能包含一个或多个场景。故事将提供情节、角色、对话和背景描述。
- 用户需求（可选）：用户需求，可能为空。用户需求可能包括：
    - 目标受众（例如儿童、青少年、成人）。
    - 剧本类型（例如微电影、电影、短剧）。
    - 期望的场景数量（例如"分为3个场景"）。
    - 其他具体指示（例如强调对话或动作）。

[输出]
{format_instructions}

[指导原则]
- 输出值中的语言应与输入故事的语言一致。
- 场景划分原则：每个场景必须基于相同的时间和地点。当时间或地点发生变化时，开始一个新场景。如果用户指定了场景数量，尽量满足要求。否则，根据故事自然划分场景，确保每个场景有独立的戏剧冲突或推进。
- 剧本格式标准：使用标准剧本格式：场景标题全大写或加粗，角色名称居中或大写，对话缩进，动作描述用括号括起。
- 连贯流畅：确保场景之间和整体故事流的自然过渡。避免突兀的情节跳跃。
- 视觉增强原则：所有描述必须"可拍摄"。使用具体动作而非抽象情感（例如使用"他转过身去，避开目光接触"而非"他感到羞愧"）。描述丰富的环境细节，包括光线、道具、天气等，以增强氛围。可视化角色表演，通过面部表情、手势和动作表达内心状态（例如"她咬着嘴唇，双手颤抖"暗示紧张）。
- 一致性：确保对话和动作与原始故事的意图一致，不偏离核心情节。
"""


human_prompt_template_write_script_based_on_story = \
"""
<STORY>
{story}
</STORY>

<USER_REQUIREMENT>
{user_requirement}
</USER_REQUIREMENT>
"""


class Screenwriter:
    def __init__(
        self,
        chat_model: str,
    ):
        self.chat_model = chat_model

    async def develop_story(
        self,
        idea: str,
        user_requirement: Optional[str] = None,
    ) -> str:
        messages = [
            ("system", system_prompt_template_develop_story),
            ("human", human_prompt_template_develop_story.format(idea=idea, user_requirement=user_requirement)),
        ]
        response = await self.chat_model.ainvoke(messages)
        story = response.content
        return story


    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30), after=after_func)
    async def write_script_based_on_story(
        self,
        story: str,
        user_requirement: Optional[str] = None,
    ) -> List[str]:


        class WriteScriptBasedOnStoryResponse(BaseModel):
            script: List[str] = Field(
                ...,
                description="基于故事的剧本。每个元素是一个场景。"
            )

        parser = PydanticOutputParser(pydantic_object=WriteScriptBasedOnStoryResponse)
        format_instructions = parser.get_format_instructions()

        messages = [
            ("system", system_prompt_template_write_script_based_on_story.format(format_instructions=format_instructions)),
            ("human", human_prompt_template_write_script_based_on_story.format(story=story, user_requirement=user_requirement)),
        ]
        response = await self.chat_model.ainvoke(messages)
        response = parser.parse(response.content)
        script = response.script
        return script