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


# Preserved as module-level constants for backward compatibility with any
# importer; the retry policy is now delegated to the langchain ChatModel
# (max_retries below), and the timeout to its constructor.
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
    """Convert OpenAI-format message dicts to langchain BaseMessage objects.

    Handles system/user(str)/user(multimodal list)/assistant(with nested
    OpenAI tool_calls)/tool roles -- the exact shapes AgentLoop builds in
    runtime_messages.
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
    """Agent LLM client backed by a langchain ChatModel.

    Replaces the former hand-rolled AsyncOpenAI wrapper. The public surface
    (constructor + ``complete``) is unchanged so AgentLoop is untouched; the
    OpenAI-format message dicts are converted to langchain messages internally.
    Defensive tool->plain fallback is preserved for providers/models that fail
    on tool calls.
    """

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None) -> None:
        self.model = model or llm_model()
        self.base_url = base_url or llm_base_url()
        self.api_key = api_key or llm_api_key()
        if not self.api_key:
            raise RuntimeError("INSIGHTFORGE_LLM_API_KEY is required for the agent LLM client")
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
                # Defensive fallback: some relays/models reject tool requests.
                # Retry as plain chat so the turn degrades gracefully instead of
                # aborting; if plain chat also fails the real error surfaces.
                ai = await self._chat_model.ainvoke(lc_messages)
        else:
            ai = await self._chat_model.ainvoke(lc_messages)
        return _assistant_message_from_langchain(ai)
