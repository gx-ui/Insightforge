from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .config import llm_api_key, llm_base_url, llm_model, llm_model_provider
from .models import ToolCall
from utils.provider_presets import resolve_chat_model_config


# 保留为模块级常量是为了与任何导入方保持向后兼容；
# 重试策略现已委托给 langchain ChatModel
#（即下方的 max_retries），超时则委托给其构造函数。
LLM_MAX_ATTEMPTS = 3
LLM_RETRY_BACKOFF_SECONDS = (1.0, 4.0)
LLM_REQUEST_TIMEOUT_SECONDS = 300.0


class LLMResponseShapeError(RuntimeError):
    pass


@dataclass(slots=True)
class AssistantMessage:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_message: dict[str, Any] = field(default_factory=dict)


def _to_langchain_messages(messages: list[dict[str, Any]]) -> list:
    """将 OpenAI 格式的消息字典转换为 langchain BaseMessage 对象。

    处理 system/user(字符串)/user(多模态列表)/assistant(含嵌套
    OpenAI tool_calls)/tool 角色——即 AgentLoop 在 runtime_messages 中
    构建的精确结构。
    """
    result = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_tool_calls = []
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                raw_args = fn.get("arguments", "{}")
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = raw_args or {}
                lc_tool_calls.append(
                    {"name": fn.get("name", ""), "args": args, "id": tc.get("id", "")}
                )
            result.append(AIMessage(content=content, tool_calls=lc_tool_calls))
        elif role == "tool":
            result.append(ToolMessage(content=content, tool_call_id=msg.get("tool_call_id", "")))
        else:
            result.append(HumanMessage(content=content))
    return result


def _assistant_message_from_langchain(ai: AIMessage) -> AssistantMessage:
    text = ai.content if isinstance(ai.content, str) else ""
    calls: list[ToolCall] = []
    for tc in ai.tool_calls or []:
        calls.append(
            ToolCall(
                id=tc.get("id") or f"tool-{uuid4().hex[:12]}",
                name=tc.get("name", ""),
                arguments=dict(tc.get("args") or {}),
            )
        )
    raw = ai.model_dump() if hasattr(ai, "model_dump") else {"content": text}
    return AssistantMessage(text=text, tool_calls=calls, raw_message=raw)


class OpenAICompatibleLLM:
    """由 langchain ChatModel 支撑的 Agent LLM 客户端。

    替代了原先手动实现的 AsyncOpenAI 封装。公共接口
    （构造函数 + ``complete``）保持不变，因此 AgentLoop 无需改动；
    OpenAI 格式的消息字典在内部被转换为 langchain 消息。
    对于在工具调用上失败的供应商/模型，保留了防御性的 tool->plain 回退。
    """

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None) -> None:
        self.model = model or llm_model()
        self.base_url = base_url or llm_base_url()
        self.api_key = api_key or llm_api_key()
        if not self.api_key:
            raise RuntimeError("Agent LLM 客户端需要 INSIGHTFORGE_LLM_API_KEY")
        init_args = resolve_chat_model_config(
            {
                "model": self.model,
                "model_provider": llm_model_provider(),
                "base_url": self.base_url,
                "api_key": self.api_key,
            }
        )
        self._chat_model = init_chat_model(
            max_retries=LLM_MAX_ATTEMPTS,
            timeout=LLM_REQUEST_TIMEOUT_SECONDS,
            **init_args,
        )

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantMessage:
        lc_messages = _to_langchain_messages(messages)
        if tools:
            try:
                ai = await self._chat_model.bind_tools(tools).ainvoke(lc_messages)
            except Exception:
                # 防御性回退：某些中转/模型会拒绝工具请求。
                # 以普通对话重试，使该轮次优雅降级而非
                # 中止；若普通对话也失败，则暴露真实错误。
                ai = await self._chat_model.ainvoke(lc_messages)
        else:
            ai = await self._chat_model.ainvoke(lc_messages)
        return _assistant_message_from_langchain(ai)
