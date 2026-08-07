import os
import logging
import asyncio
from typing import List, Tuple
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.chat_models import init_chat_model
from langchain.text_splitter import RecursiveCharacterTextSplitter



system_prompt_template_compress_novel_chunk = \
"""
你是一名专注于文学内容的文本压缩专家。你的目标是压缩小说或故事片段，同时保留核心叙事元素、关键细节、角色发展和情节连贯性。


**任务**
压缩提供的输入文本，大幅减少篇幅，去除冗余、过度描写的段落和次要细节——但不丢失必要的故事线索、对话或情感冲击力。压缩后的输出应清晰易读。


**输入**
一段小说文本（可能因上下文长度限制而被截断）。它被包裹在 <NOVEL_CHUNK_START> 和 <NOVEL_CHUNK_END> 标签之间。


**输出**
输入文本的压缩版本，保留核心叙事、关键事件和角色互动。

**指导原则**
1. 忠实于情节：绝对保留所有主要情节点、转折、揭示和关键事件顺序。不要遗漏关键故事元素。
2. 角色一致性：保持角色的行为、决策和发展。揭示情节或角色的重要对话可以被压缩或改写，但必须保持其含义不变。
3. 精简描述：将冗长的场景、角色或物体描述缩减为最必要和最具表现力的元素。捕捉情绪和关键细节，但无需华丽辞藻。
4. 压缩内心独白：概括角色延长的内心思考和反思，聚焦于它们所导致的关键认知或决定。
5. 简化语言：使用更直接和简洁的语言。合并句子，去除多余的副词和形容词，避免重复措辞。
6. 连贯流畅：确保压缩后的文本流畅易读，保持逻辑叙事流。不应感觉像是一个零散的事件列表。
7. 丢弃任何非叙事文本（例如"请关注我的账号！"、"背景设定：……"、个人观点）。
8. 生成无缝的段落（必要时可多段），不要使用标记（如"第一章"）或分节符。
9. 输出语言应与原文语言一致。
"""

human_prompt_template_compress_novel_chunk = \
"""
<NOVEL_CHUNK_START>
{novel_chunk}
<NOVEL_CHUNK_END>
"""


system_prompt_template_aggregate = \
"""
你是一名专业的文本处理助手，专注于分段文本的聚合和精炼。你的专长在于无缝合并连续的文本片段，同时智能处理以不同方式表达的重复或重叠内容。

**任务**
将提供的文本片段聚合为一个连贯、连续的短篇故事。仔细识别并解决一个片段的结尾与下一个片段的开头在语义上相似但表达方式不同的重叠部分。在保留原文含义、风格和流畅性的前提下，去除重复内容。确保所有非重叠内容保持不变且完整。


**输入**
一系列文本片段（按从第一个到最后一个的顺序排列），每个片段可能与下一个片段存在重叠部分。重叠部分可能在措辞上有所不同，但传达相似的含义。每个片段被包裹在 <CHUNK_N_START> 和 <CHUNK_N_END> 标签之间，其中 N 是片段索引，从 0 开始。

**输出**
一个单一的、合并后的文本，没有不自然的重复或中断。输出应保持原始叙事结构、语气和细节，并在相邻片段之间实现平滑过渡。

**指导原则**
1. 按顺序分析输入片段。对于每对相邻片段（例如片段 N 和片段 N+1），比较片段 N 的结尾和片段 N+1 的开头，检测重叠内容。
2. 如果重叠部分语义等价但措辞不同，则合并时保留最自然或上下文最合适的版本（如果两者同样有效，优先选择后一片段的版本，但避免引入不一致）。
3. 如果重叠部分不完全等价（例如一个包含更多细节），则整合有意义的信息而不重复，确保不丢失内容。
4. 保留所有非重叠文本，保持其原始形式。不要修改、改写或省略任何独特内容。
5. 确保合并后的文本流畅连贯，没有突兀的跳跃或冗余的短语。
6. 如果两个片段之间未检测到重叠，则直接拼接，不做修改。
7. 不要编造新内容或改变超出处理重叠范围之外的原始叙事。
8. 输出语言应与原文语言一致。
"""

human_prompt_template_aggregate = \
"""
{chunks}
"""




class NovelCompressor:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        chat_model: str,
        chunk_size: int = 65536,
        chunk_overlap: int = 8192,
    ):
        self.chat_model = init_chat_model(
            model=chat_model,
            api_key=api_key,
            base_url=base_url,
            model_provider="openai",
        )

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )


    def split(
        self,
        novel_text: str,
    ):
        novel_chunks = self.splitter.split_text(novel_text)
        return novel_chunks


    async def compress(
        self,
        index_chunk_pairs: List[Tuple[int, str]],
        max_concurrent_tasks: int = 5,
    ) -> str:
        sem = asyncio.Semaphore(max_concurrent_tasks)

        tasks = [
            self.compress_single_novel_chunk(sem, index, novel_chunk)
            for index, novel_chunk in index_chunk_pairs
        ]
        compressed_novel_chunks = await asyncio.gather(*tasks)
        return compressed_novel_chunks


    async def compress_single_novel_chunk(
        self,
        semaphore: asyncio.Semaphore,
        index,
        novel_chunk: str,
    ) -> str:
        async with semaphore:
            logging.info(f"正在压缩小说分块 {index}")
            messages = [
                SystemMessage(
                    content=system_prompt_template_compress_novel_chunk
                ),
                HumanMessage(
                    content=human_prompt_template_compress_novel_chunk.format(
                        novel_chunk=novel_chunk
                    )
                ),
            ]
            response = await self.chat_model.ainvoke(messages)
            compressed_novel_chunk = response.content
            logging.info(f"已压缩小说分块 {index}")
        return index, compressed_novel_chunk


    def aggregate(
        self,
        compressed_novel_chunks: List[str],
    ):
        chunks_str = "\n".join([
            f"<CHUNK_{i}_START>\n{chunk}\n<CHUNK_{i}_END>"
            for i, chunk in enumerate(compressed_novel_chunks)
        ])

        messages = [
            SystemMessage(
                content=system_prompt_template_aggregate
            ),
            HumanMessage(
                content=human_prompt_template_aggregate.format(
                    chunks=chunks_str
                )
            ),
        ]
        response = self.chat_model.invoke(messages)
        aggregated_novel = response.content
        return aggregated_novel