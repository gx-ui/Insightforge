from __future__ import annotations

import json
from datetime import datetime
from typing import Any, AsyncIterator, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, START, END

from .context_compactor import ContextCompactor, CompactionResult
from .llm import AssistantMessage  # noqa: F401  (re-exported for test compat)
from .models import TurnControl
from .loop import (
    MAX_TOOL_PASSES,
    _compaction_record,
    _openai_tool_call,
    _prompt_tokens,
    _tool_schema_tokens,
    _transition,
)

_OBSERVATION_PREFIX = (
    "Tool-provided image observation(s). Inspect these pixels as evidence "
    "for the active task; this is not a new user request."
)


class AgentState(TypedDict, total=False):
    user_input: str
    turn_id: str
    control: TurnControl
    tool_schemas: list[dict[str, Any]]
    system: str
    runtime_messages: list[dict[str, Any]]
    assistant: Any
    assistant_turns: list[dict[str, Any]]
    tool_rounds: list[dict[str, Any]]
    transitions: list[dict[str, str]]
    all_tool_results: list[dict[str, Any]]
    final_text: str
    status: str
    tool_round: int


class AgentLoop:
    """LangGraph-backed agent loop.

    Public surface (constructor + stream_events + compact_history) is identical
    to AgentLoopLegacy so callers (main_agent.py, tests) are unchanged. Internally
    the ReAct loop is a StateGraph; nodes emit JSONL events directly via
    get_stream_writer() (Phase 0 prototype gate validated byte-level equivalence).
    """

    def __init__(
        self,
        session_index,
        prompt_builder,
        tool_registry,
        tool_executor,
        llm: Any,
        context_compactor: ContextCompactor | None = None,
    ) -> None:
        self.session_index = session_index
        self.prompt_builder = prompt_builder
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.llm = llm
        self.context_compactor = context_compactor or ContextCompactor(llm)
        self.history: list[dict[str, Any]] = []
        self._graph = self._build_graph()

    # -- public API (unchanged from legacy) --

    async def compact_history(self, *, reason: str = "manual") -> str:
        if not self.history:
            return "No conversation history to compact."
        session = self.session_index.active() or self.session_index.create()
        result = await self.context_compactor.compact(
            self.history,
            previous_summary=str(session.get("compacted_summary", "") or ""),
            reason=reason,
        )
        self.history = [
            self.context_compactor.synthetic_summary_message(result.summary),
            *result.preserved_messages,
        ]
        self.session_index.update_compaction(session["session_id"], _compaction_record(result))
        return f"Compacted context {result.estimated_tokens_before} -> {result.estimated_tokens_after} ({result.mode})."

    async def stream_events(self, user_input: str) -> AsyncIterator[dict[str, Any]]:
        config = {"recursion_limit": MAX_TOOL_PASSES * 2 + 10}
        async for chunk in self._graph.astream({"user_input": user_input}, config=config, stream_mode="custom"):
            yield chunk

    # -- graph construction --

    def _build_graph(self):
        g = StateGraph(AgentState)
        g.add_node("init", self._init_node)
        g.add_node("model", self._model_node)
        g.add_node("tools", self._tools_node)
        g.add_node("finalize", self._finalize_node)
        g.add_edge(START, "init")
        g.add_edge("init", "model")
        g.add_conditional_edges("model", self._route_after_model, {"tools": "tools", "finalize": "finalize"})
        g.add_edge("tools", "model")
        g.add_edge("finalize", END)
        return g.compile()

    # -- nodes --

    async def _init_node(self, state: AgentState) -> dict:
        writer = get_stream_writer()
        control = TurnControl()
        turn_id = control.turn_id
        writer({"type": "turn", "turn_id": turn_id, "turn": {"id": turn_id}})
        user_input = state["user_input"]
        tool_schemas = self.tool_registry.list_function_tools()
        parts = self.prompt_builder.build_parts(user_input)
        system = "\n\n".join(f"## {part.title}\n{part.body}" for part in parts if part.id != "request.user")
        if self.context_compactor.should_preflight_compact(
            [*self.history, {"role": "user", "content": user_input}],
            system_tokens=_prompt_tokens(parts),
            tools_tokens=_tool_schema_tokens(tool_schemas),
        ):
            writer({"type": "status", "turn_id": turn_id, "phase": "compact", "message": "Compacting context before sampling"})
            await self.compact_history(reason="token-pressure")
            parts = self.prompt_builder.build_parts(user_input)
            system = "\n\n".join(f"## {part.title}\n{part.body}" for part in parts if part.id != "request.user")
        writer({"type": "prompt_trace", "turn_id": turn_id, "prompt_trace": self.prompt_builder.trace(parts)})
        runtime_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            *self.history,
            {"role": "user", "content": user_input},
        ]
        return {
            "turn_id": turn_id,
            "control": control,
            "tool_schemas": tool_schemas,
            "runtime_messages": runtime_messages,
            "assistant_turns": [],
            "tool_rounds": [],
            "transitions": [],
            "all_tool_results": [],
            "final_text": "",
            "status": "completed",
            "tool_round": 0,
        }

    async def _model_node(self, state: AgentState) -> dict:
        writer = get_stream_writer()
        turn_id = state["turn_id"]
        tool_round = state.get("tool_round", 0)
        writer({"type": "status", "turn_id": turn_id, "phase": "sampling_assistant", "message": "Sampling assistant"})
        try:
            assistant = await self.llm.complete(state["runtime_messages"], tools=state["tool_schemas"])
        except Exception as exc:
            final_text = f"Agent LLM request failed: {exc}"
            transitions = state.get("transitions", []) + [_transition("sampling_assistant", "finalizing_answer", "llm_sampling_failed")]
            writer({"type": "error", "turn_id": turn_id, "message": final_text, "metadata": {"error_type": "llm_sampling_failed"}})
            return {"final_text": final_text, "status": "failed", "transitions": transitions, "assistant": None}
        assistant_turns = state.get("assistant_turns", []) + [
            {
                "phase": "initial" if tool_round == 0 else f"followup_{tool_round}",
                "text": assistant.text,
                "tool_calls": [c.as_dict() for c in assistant.tool_calls],
            }
        ]
        if not assistant.tool_calls:
            transitions = state.get("transitions", []) + [_transition("sampling_assistant", "finalizing_answer", "assistant_finished_without_tools")]
            final_text = assistant.text
            if final_text:
                writer({"type": "token", "turn_id": turn_id, "delta": final_text})
            return {"assistant": assistant, "assistant_turns": assistant_turns, "transitions": transitions, "final_text": final_text}
        transitions = state.get("transitions", []) + [_transition("sampling_assistant", "executing_tools", "assistant_requested_tools")]
        if tool_round >= MAX_TOOL_PASSES:
            final_text = "Tool loop halted after max tool passes."
            writer({"type": "error", "turn_id": turn_id, "message": final_text, "metadata": {"max_tool_passes": MAX_TOOL_PASSES}})
            return {"assistant": assistant, "assistant_turns": assistant_turns, "transitions": transitions, "final_text": final_text, "status": "halted"}
        return {"assistant": assistant, "assistant_turns": assistant_turns, "transitions": transitions}

    def _route_after_model(self, state: AgentState) -> str:
        assistant = state.get("assistant")
        if assistant is None or not getattr(assistant, "tool_calls", None):
            return "finalize"
        if state.get("tool_round", 0) >= MAX_TOOL_PASSES:
            return "finalize"
        return "tools"

    async def _tools_node(self, state: AgentState) -> dict:
        writer = get_stream_writer()
        turn_id = state["turn_id"]
        control = state["control"]
        assistant = state["assistant"]
        tool_round = state.get("tool_round", 0) + 1
        writer({"type": "status", "turn_id": turn_id, "phase": "executing_tools", "message": f"Running tools (round {tool_round})"})
        runtime_messages = list(state["runtime_messages"])
        runtime_messages.append(
            {"role": "assistant", "content": assistant.text or "", "tool_calls": [_openai_tool_call(c) for c in assistant.tool_calls]}
        )
        round_results = []
        round_model_content: list[dict[str, Any]] = []
        all_tool_results = list(state.get("all_tool_results", []))

        def on_progress(event: dict[str, Any]) -> None:
            writer(event)

        for call in assistant.tool_calls:
            writer({"type": "tool_start", "turn_id": turn_id, "tool": call.as_dict()})
            record = await self.tool_executor.execute(call, control, progress_callback=on_progress)
            result = record.result
            round_results.append(result)
            all_tool_results.append(result.as_dict())
            writer({"type": "tool_result", "turn_id": turn_id, "tool_result": result.as_dict()})
            runtime_messages.append(
                {"role": "tool", "tool_call_id": call.id, "name": result.name, "content": json.dumps(result.as_dict(), ensure_ascii=False)}
            )
            if result.model_content:
                round_model_content.extend(result.model_content)
        if round_model_content:
            runtime_messages.append(
                {"role": "user", "content": [{"type": "text", "text": _OBSERVATION_PREFIX}, *round_model_content]}
            )
        tool_rounds = state.get("tool_rounds", []) + [
            {
                "tool_round": tool_round,
                "requested_tools": [c.as_dict() for c in assistant.tool_calls],
                "tool_results": [r.as_dict() for r in round_results],
            }
        ]
        transitions = state.get("transitions", []) + [
            _transition("executing_tools", "post_tool_decision", "tool_round_completed"),
            _transition("post_tool_decision", "sampling_assistant", "runtime_continuation_after_tools"),
        ]
        return {
            "runtime_messages": runtime_messages,
            "tool_round": tool_round,
            "tool_rounds": tool_rounds,
            "transitions": transitions,
            "all_tool_results": all_tool_results,
        }

    async def _finalize_node(self, state: AgentState) -> dict:
        writer = get_stream_writer()
        turn_id = state["turn_id"]
        final_text = state.get("final_text", "")
        user_input = state["user_input"]
        self.history.extend([{"role": "user", "content": user_input}, {"role": "assistant", "content": final_text}])
        turn_record = {
            "turn_id": turn_id,
            "status": state.get("status", "completed"),
            "raw_user_input": user_input,
            "assistant_turns": state.get("assistant_turns", []),
            "tool_rounds": state.get("tool_rounds", []),
            "transitions": state.get("transitions", []),
            "final_assistant_text": final_text,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        final_session = self.session_index.active() or self.session_index.create()
        self.session_index.append_turn_record(final_session["session_id"], turn_record)
        all_tool_results = state.get("all_tool_results", [])
        writer({"type": "done", "turn_id": turn_id, "assistant": final_text, "tool_results": all_tool_results})
        writer({"type": "session", "turn_id": turn_id, "session": self.session_index.snapshot()})
        return {}
