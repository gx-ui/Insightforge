from __future__ import annotations

import warnings

# langchain 与 langchain_core 在包导入时会调用 surface_langchain_deprecation_warnings()，
# 以"前置插入"方式注册 default 过滤器。若在其之后才注册我们的 ignore，
# 前面的 default 会抢先匹配，导致第三方库（langgraph 的 Reviver）的
# pending 弃用警告仍然弹出。因此先强制导入 langchain，确保它的过滤器
# 注册先完成，再注册 ignore，让 ignore 位于过滤器列表最前。
import langchain  # noqa: F401  # 仅用于稳定 warnings 过滤器注册顺序
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)

__all__ = ["AgentLoop", "SessionIndex", "ToolRegistry", "build_runtime"]


def build_runtime(*args, **kwargs):
    from .agent_graph import build_runtime as _build_runtime

    return _build_runtime(*args, **kwargs)


def __getattr__(name):
    if name == "AgentLoop":
        from .agent_graph import AgentLoop

        return AgentLoop
    if name == "SessionIndex":
        from .session_index import SessionIndex

        return SessionIndex
    if name == "ToolRegistry":
        from .tools import ToolRegistry

        return ToolRegistry
    raise AttributeError(name)
