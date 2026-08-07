import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser as PydanticOutputParser
from langchain.chat_models.base import BaseChatModel
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from typing import List
from tenacity import retry, stop_after_attempt
from interfaces import CharacterInScene
from langchain_core.messages import HumanMessage, SystemMessage

from utils.retry import after_func


system_prompt_template_extract_characters = \
"""
[角色]
你是一名顶尖的电影剧本分析专家。

[任务]
你的任务是分析提供的剧本，提取所有相关的角色信息。

[输入]
你将收到一个包裹在 <SCRIPT> 和 </SCRIPT> 标签内的剧本。

以下是输入的一个简单示例：

<SCRIPT>
一位年轻女性独自坐在桌旁，凝视着窗外。她啜饮了一口咖啡，叹了口气。液体已经不再温热，只是对流逝时光的苦涩提醒。窗外，世界在匆忙的脚步和遥远的汽车喇叭声中模糊一片，但在安静的咖啡馆内，时间仿佛变得厚重而凝滞。
她的手指沿着陶瓷杯沿画着圈，一遍又一遍地追随着那并不完美的圆。她必须做出的决定本该很简单——只是她人生表格上的一个复选框。是或否。留下或离开。然而，它却扎根在她的胸口，成了一团由恐惧和渴望交织而成的纠结。
</SCRIPT>

[输出]
{format_instructions}


[指导原则]
- 确保所有输出值（不含键）的语言与剧本使用的语言一致。
- 将所有指代同一实体的名称归并到同一个角色下。选择最合适的名字作为该角色的标识符。如果该人物是现实中的知名人物，应保留其真实姓名（例如 埃隆·马斯克、比尔·盖茨）。
- 如果角色的名字未被提及，可以使用合理的称呼来指代他们，包括使用他们的职业或显著的身体特征。例如"年轻女性"或"咖啡师"。
- 对于剧本中的背景角色，不需要将他们视为独立角色。
- 如果角色的特征在剧本中未被描述或仅部分描述，你需要根据上下文设计合理的特征，使其更完整和详细，确保生动且富有表现力。
- 在静态特征中，你需要描述角色的外貌、体型等相对不变的特征。在动态特征中，你需要描述角色的着装、配饰、携带的关键物品等容易变化的特征。
- 静态特征和动态特征中都不应包含任何关于角色性格、角色或与他人关系的信息。
- 在设计角色特征时，在合理范围内，应使不同角色的外观尽可能有区分度。
- 对角色的描述应详细，避免使用抽象术语，而应采用可视觉化的描述——例如具体的服装颜色和具体的身体特征（如大眼睛、高鼻梁）。
"""

human_prompt_template_extract_characters = \
"""
<SCRIPT>
{script}
</SCRIPT>
"""


class ExtractCharactersResponse(BaseModel):
    characters: List[CharacterInScene] = Field(
        ..., description="从剧本中提取的角色列表。"
    )



class CharacterExtractor:
    def __init__(
        self,
        chat_model,
    ):
        self.chat_model = chat_model

    @retry(
        stop=stop_after_attempt(3),
        after=after_func,
    )
    async def extract_characters(self, script: str) -> List[CharacterInScene]:

        parser = PydanticOutputParser(pydantic_object=ExtractCharactersResponse)

        messages = [
            SystemMessage(content=system_prompt_template_extract_characters.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=human_prompt_template_extract_characters.format(script=script)),
        ]

        chain = self.chat_model | parser

        response: ExtractCharactersResponse = await chain.ainvoke(messages)

        return response.characters