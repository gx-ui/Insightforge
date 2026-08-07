import os
import logging
import asyncio
from typing import List
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from utils.robust_json_parser import TrailingCommaTolerantPydanticOutputParser as PydanticOutputParser
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt

from interfaces import Event

system_prompt_template_extract_events = \
"""
你是一名高技能的文学分析师 AI。你的专长是叙事结构、情节解构和主题分析。你细致阅读和解读散文，将故事分解为基本的连续事件。

**任务**
根据提供的文本，按照故事顺序，在已提取的部分事件基础上，提取小说的下一个事件。

**输入**
1. 小说的完整文本，被包裹在 <NOVEL_TEXT_START> 和 <NOVEL_TEXT_END> 标签之间
2. 已提取事件的序列（按顺序），被包裹在 <EXTRACTED_EVENTS_START> 和 <EXTRACTED_EVENTS_END> 标签之间。该序列可能为空。每个事件包含多个过程，构成一个完整的因果链。

以下是输入示例：

<NOVEL_TEXT_START>
夜色如墨，城市博物馆刺耳的警报声突然划破寂静。一个行动如鬼魅般敏捷的小偷刚刚撬开展示柜，盗走了名为"海洋之心"的蓝色宝石，警报声在大厅中回荡。
...（更多小说文本）...
<NOVEL_TEXT_END>

<EXTRACTED_EVENTS_START>
<Event 0>
Description: 一个小偷从博物馆偷走宝石，在屋顶追逐中被警卫抓获，宝石被追回。
Process Chain:
- 小偷偷走博物馆宝石，触发警报。警卫发现并开始追捕。
- 小偷冲出博物馆后门，冲过狭窄小巷，警卫紧追不舍并呼叫支援。
- ...（更多过程）...

<Event 1>
Description: ...（更多描述）...
Process Chain:
- ...（更多过程）...

<EXTRACTED_EVENTS_END>


**输出**
{format_instructions}

**指导原则**
1. 关注对情节、角色发展或主题深度至关重要的事件。
2. 确保事件在逻辑上与前序和后序事件区分开来。
3. 如果事件跨越多个场景，将其统一在一个单一的戏剧目标下。例如，追逐序列可能开始于城市市场，继续穿过后巷，并在屋顶上结束——所有这些构成一个单一事件，因为它们共同实现了"主角逃避追捕"的戏剧目的。
4. 保持客观：基于文本描述事件，不做解读或判断。
5. 对于过程字段，提供事件进展的详细、逐步描述，包括关键动作、决策和转折点。每一步应清晰简洁，说明事件如何随时间展开。
以下是一个示例：
时间范围：第二天早上，获取了关于神庙的信息之后。
角色：Elara（主角）和 Kaelen（她的寻宝对手）。
原因：两人寻找同一件神器，并决心先到达。
过程：事件开始于 Elara 在港口小镇匆忙购买补给（场景1），在那里她发现 Kaelen 已经在雇佣船员，增加了 stakes。然后她争分夺秒地争取自己的船只和船长，在时间压力下激烈谈判（场景2）。事件在码头上的直接对峙中达到高潮（场景3），Kaelen 试图破坏她的船，导致两人之间短暂但激烈的剑斗。
结果：Elara 成功保卫了她的船并启航，但这场冲突巩固了她与 Kaelen 之间痛苦的私人竞争，确保了他们前往神庙的旅程将充满直接对抗和危险。
6. 你事件描述中的每个细节必须直接由输入小说支持。不要添加、假设或编造任何信息。
7. 输出值中的语言应与输入文本一致。
"""

human_prompt_template_extract_next_event = \
"""
<NOVEL_TEXT_START>
{novel_text}
<NOVEL_TEXT_END>

<EXTRACTED_EVENTS_START>
{extracted_events}
<EXTRACTED_EVENTS_END>
"""



class EventExtractor:
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
        self.parser = PydanticOutputParser(pydantic_object=Event)


    # 提取事件的上限：is_last 仅由 LLM 断言，若不加
    # 上限，一个永不设置它的模型会无限循环（并消耗 token）。
    max_events = 50

    def __call__(
        self,
        novel_text: str,
    ):
        logging.info("正在从小说中提取事件...")

        events = []
        while True:
            if len(events) >= self.max_events:
                raise RuntimeError(
                    f"事件提取超过了 {self.max_events} 个事件的上限，"
                    "且未出现 is_last 标记；为避免无限 LLM 调用而中止。"
                )
            event = self.extract_next_event(novel_text, events)

            events.append(event)
            logging.info(f"已提取事件: \n{event}")
            if event.is_last:
                break

        return events


    @retry(
        stop=stop_after_attempt(3),
        after=lambda retry_state: logging.warning(f"因错误正在重试 extract_next_event: {retry_state.outcome.exception()}"),
    )
    def extract_next_event(
        self,
        novel_text: str,
        extracted_events: List[Event]
    ) -> Event:

        extracted_events_str = "\n\n".join([str(e) for e in extracted_events])

        messages = [
            SystemMessage(
                content=system_prompt_template_extract_events.format(format_instructions=self.parser.get_format_instructions()),
            ),
            HumanMessage(
                content=human_prompt_template_extract_next_event.format(
                    novel_text=novel_text,
                    extracted_events=extracted_events_str,
                )
            )
        ]

        chain = self.chat_model | self.parser

        event: Event = chain.invoke(messages)

        assert event.index == len(extracted_events), f"提取的事件索引 {event.index} 与预期索引 {len(extracted_events)} 不匹配"

        return event