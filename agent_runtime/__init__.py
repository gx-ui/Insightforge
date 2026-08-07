from __future__ import annotations

import warnings

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
