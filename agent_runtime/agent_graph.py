from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, TypedDict
from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, START, END
from .context_compactor import ContextCompactor, CompactionResult
from .llm import AssistantMessage, OpenAICompatibleLLM
from .models import TurnControl, ToolCall
from .prompts import PromptBuilder
from .session_index import SessionIndex
from .tool_executor import ToolExecutor
from .tools import build_builtin_registry
from .streaming import normalize_stage, utc_timestamp_ms

MAX_TOOL_PASSES = 50

_OBSERVATION_PREFIX = (
    "工具提供的图像观察结果。请将这些像素作为证据进行审查， "
    "以推进当前任务；这不是新的用户请求。"
)


class AgentState(TypedDict, total=False):
    # 跨轮次持久化（检查点）：
    history: list[dict[str, Any]]
    # 每轮次（在 init 中重置）：
    user_input: str
    run_id: str
    turn_id: str
    tool_schemas: list[dict[str, Any]]
    system: str
    runtime_messages: list[dict[str, Any]]
    assistant_text: str
    assistant_tool_calls: list[dict[str, Any]]
    assistant_turns: list[dict[str, Any]]
    tool_rounds: list[dict[str, Any]]
    transitions: list[dict[str, str]]
    all_tool_results: list[dict[str, Any]]
    final_text: str
    status: str
    tool_round: int


class AgentLoop:
    """基于 LangGraph 的 Agent 循环，带 sqlite 检查点。
    对话历史存储在图状态中，通过以 thread_id=session_id 为键的
    AsyncSqliteSaver 跨轮次和进程重启持久化。
    TurnControl（不可序列化）是实例属性，而非图状态。
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
        self._control: TurnControl | None = None
        self._graph = None
        self._saver = None
        self._conn = None
        self._checkpoint_path = str(
            Path(session_index.workspace_root) / ".insightforge" / "checkpoints.sqlite"
        )

    # -- 延迟图编译（AsyncSqliteSaver 需要异步上下文）--

    async def _ensure_graph(self):
        if self._graph is not None:
            return
     
        import aiosqlite
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        Path(self._checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._checkpoint_path)
        self._saver = AsyncSqliteSaver(
            self._conn,
            serde=JsonPlusSerializer(
                allowed_json_modules=(("langchain",), ("langchain_core",), ("langgraph",))

            ),
        )
        self._graph = self._build_graph()

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
        return g.compile(checkpointer=self._saver)

    async def aclose(self) -> None:
        """关闭 sqlite 检查点连接。可安全多次调用。"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            self._saver = None
            self._graph = None

    # -- 公共 API（签名不变）--

    async def _do_compact(self, session: dict, *, reason: str):
        """共享压缩：压缩 self.history，更新会话元数据。"""
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
        return result

    async def compact_history(self, *, reason: str = "manual") -> str:
        await self._ensure_graph()
        session = self.session_index.active() or self.session_index.create()
        thread_id = session["session_id"]
        config = {"configurable": {"thread_id": thread_id}}
        state = await self._graph.aget_state(config)
        self.history = list(state.values.get("history", [])) if state and state.values else []
        if not self.history:
            return "No conversation history to compact."
        result = await self._do_compact(session, reason=reason)
        await self._graph.aupdate_state(config, {"history": self.history})
        return f"Compacted context {result.estimated_tokens_before} -> {result.estimated_tokens_after} ({result.mode})."

    async def stream_events(self, user_input: str, *, run_id: str | None = None) -> AsyncIterator[dict[str, Any]]:
        await self._ensure_graph()
        session = self.session_index.active() or self.session_index.create()
        thread_id = session["session_id"]
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": MAX_TOOL_PASSES * 2 + 10}
        input_state = {"user_input": user_input, "run_id": run_id or ""}
        async for chunk in self._graph.astream(input_state, config=config, stream_mode="custom"):
            yield _stream_event_envelope(chunk, run_id)

    # -- 节点 --

    async def _init_node(self, state: AgentState) -> dict:
        writer = get_stream_writer()
        control = TurnControl(turn_id=state.get("run_id") or TurnControl().turn_id)
        self._control = control
        turn_id = control.turn_id
        writer({"type": "turn", "turn_id": turn_id, "turn": {"id": turn_id}})
        user_input = state["user_input"]
        checkpoint_history = state.get("history")
        if checkpoint_history is not None:
            self.history = list(checkpoint_history)
        tool_schemas = self.tool_registry.list_function_tools()
        parts = self.prompt_builder.build_parts(user_input)
        system = "\n\n".join(f"## {part.title}\n{part.body}" for part in parts if part.id != "request.user")
        if self.context_compactor.should_preflight_compact(
            [*self.history, {"role": "user", "content": user_input}],
            system_tokens=_prompt_tokens(parts),
            tools_tokens=_tool_schema_tokens(tool_schemas),
        ):
            writer({"type": "status", "turn_id": turn_id, "phase": "compact", "message": "采样前压缩上下文"})
            session = self.session_index.active() or self.session_index.create()
            await self._do_compact(session, reason="token-pressure")
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
            "run_id": turn_id,
            "history": self.history,
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
        writer({"type": "status", "turn_id": turn_id, "phase": "sampling_assistant", "message": "正在采样助手"})
        try:
            assistant = await self._complete_assistant(state["runtime_messages"], state["tool_schemas"], writer, turn_id)
        except Exception as exc:
            final_text = f"Agent LLM 请求失败: {exc}"
            transitions = state.get("transitions", []) + [_transition("sampling_assistant", "finalizing_answer", "llm_sampling_failed")]
            writer({"type": "error", "turn_id": turn_id, "message": final_text, "metadata": {"error_type": "llm_sampling_failed"}})
            return {"final_text": final_text, "status": "failed", "transitions": transitions, "assistant_tool_calls": []}
        assistant_turns = state.get("assistant_turns", []) + [
            {
                "phase": "initial" if tool_round == 0 else f"followup_{tool_round}",
                "text": assistant.text,
                "tool_calls": [c.as_dict() for c in assistant.tool_calls],
            }
        ]
        tc_dicts = [c.as_dict() for c in assistant.tool_calls]
        if not assistant.tool_calls:
            transitions = state.get("transitions", []) + [_transition("sampling_assistant", "finalizing_answer", "assistant_finished_without_tools")]
            final_text = assistant.text
            return {"assistant_text": assistant.text, "assistant_tool_calls": tc_dicts, "assistant_turns": assistant_turns, "transitions": transitions, "final_text": final_text}
        transitions = state.get("transitions", []) + [_transition("sampling_assistant", "executing_tools", "assistant_requested_tools")]
        if tool_round >= MAX_TOOL_PASSES:
            final_text = "工具循环在达到最大工具调用轮次后停止。"
            writer({"type": "error", "turn_id": turn_id, "message": final_text, "metadata": {"max_tool_passes": MAX_TOOL_PASSES}})
            return {"assistant_text": assistant.text, "assistant_tool_calls": tc_dicts, "assistant_turns": assistant_turns, "transitions": transitions, "final_text": final_text, "status": "halted"}
        return {"assistant_text": assistant.text, "assistant_tool_calls": tc_dicts, "assistant_turns": assistant_turns, "transitions": transitions}

    async def _complete_assistant(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], writer: Any, turn_id: str) -> AssistantMessage:
        complete_stream = getattr(self.llm, "complete_stream", None)
        if callable(complete_stream):
            text_parts: list[str] = []
            tool_calls: dict[str, ToolCall] = {}
            started = False
            sequence = 0
            try:
                async for chunk in complete_stream(messages, tools):
                    text = str(getattr(chunk, "text", "") or "")
                    if text:
                        if not started:
                            writer({"type": "stream_start", "turn_id": turn_id, "mode": "stream"})
                            started = True
                        sequence += 1
                        text_parts.append(text)
                        writer({"type": "token", "turn_id": turn_id, "sequence": sequence, "delta": text})
                    for call in getattr(chunk, "tool_calls", []) or []:
                        tool_calls[call.id] = call
            except Exception:
                if started:
                    writer({"type": "stream_end", "turn_id": turn_id, "mode": "stream", "tokens": sequence})
                assistant = await self.llm.complete(messages, tools=tools)
                self._emit_buffered_text(writer, turn_id, assistant.text)
                return assistant
            if started:
                writer({"type": "stream_end", "turn_id": turn_id, "mode": "stream", "tokens": sequence})
            return AssistantMessage(text="".join(text_parts), tool_calls=list(tool_calls.values()))
        assistant = await self.llm.complete(messages, tools=tools)
        self._emit_buffered_text(writer, turn_id, assistant.text)
        return assistant

    def _emit_buffered_text(self, writer: Any, turn_id: str, text: str) -> None:
        chunks = _buffered_text_chunks(text)
        if not chunks:
            return
        writer({"type": "stream_start", "turn_id": turn_id, "mode": "buffered"})
        for sequence, chunk in enumerate(chunks, start=1):
            writer({"type": "token", "turn_id": turn_id, "sequence": sequence, "delta": chunk, "mode": "buffered"})
        writer({"type": "stream_end", "turn_id": turn_id, "mode": "buffered", "tokens": len(chunks)})

    def _route_after_model(self, state: AgentState) -> str:
        tcs = state.get("assistant_tool_calls")
        if not tcs:
            return "finalize"
        if state.get("tool_round", 0) >= MAX_TOOL_PASSES:
            return "finalize"
        return "tools"

    async def _tools_node(self, state: AgentState) -> dict:
        writer = get_stream_writer()
        turn_id = state["turn_id"]
        control = self._control or TurnControl()
        assistant_text = state.get("assistant_text", "")
        tc_dicts = state.get("assistant_tool_calls", [])
        # 为执行器重建 ToolCall 对象
        calls = [ToolCall(name=tc["name"], arguments=tc.get("arguments", {}), id=tc.get("id", "")) for tc in tc_dicts]
        tool_round = state.get("tool_round", 0) + 1
        writer({"type": "status", "turn_id": turn_id, "phase": "executing_tools", "message": f"正在运行工具（第 {tool_round} 轮）"})
        runtime_messages = list(state["runtime_messages"])
        runtime_messages.append(
            {"role": "assistant", "content": assistant_text or "", "tool_calls": [_openai_tool_call(c) for c in calls]}
        )
        round_results = []
        round_model_content: list[dict[str, Any]] = []
        all_tool_results = list(state.get("all_tool_results", []))

        def on_progress(event: dict[str, Any]) -> None:
            writer(event)

        for call in calls:
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
                "requested_tools": [c.as_dict() for c in calls],
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
        history = list(state.get("history", []))
        history.extend([{"role": "user", "content": user_input}, {"role": "assistant", "content": final_text}])
        self.history = history
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
        return {"history": history}


def _compaction_record(result: CompactionResult) -> dict[str, Any]:
    return {
        "summary": result.summary,
        "preserved_message_count": len(result.preserved_messages),
        "compacted_message_count": result.compacted_message_count,
        "estimated_tokens_before": result.estimated_tokens_before,
        "estimated_tokens_after": result.estimated_tokens_after,
        "reason": result.reason,
        "mode": result.mode,
        "created_at": result.created_at,
    }


def _prompt_tokens(parts: list[Any]) -> int:
    return sum(max(1, len(str(getattr(part, "body", ""))) // 4) for part in parts)


def _tool_schema_tokens(tool_schemas: list[dict[str, Any]]) -> int:
    try:
        return max(0, len(json.dumps(tool_schemas, ensure_ascii=False, default=str)) // 4)
    except TypeError:
        return max(0, len(str(tool_schemas)) // 4)


def _transition(src: str, dst: str, reason: str) -> dict[str, str]:
    return {"from": src, "to": dst, "reason": reason}


def _openai_tool_call(call: ToolCall) -> dict[str, Any]:
    return {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)}}


def _stream_event_envelope(event: dict[str, Any], run_id: str | None) -> dict[str, Any]:
    payload = dict(event)
    turn_id = str(payload.get("turn_id") or run_id or "")
    if turn_id:
        payload.setdefault("turn_id", turn_id)
        payload.setdefault("run_id", run_id or turn_id)
    payload.setdefault("timestamp", utc_timestamp_ms())
    raw_stage = payload.get("raw_stage")
    if not isinstance(raw_stage, str):
        progress = payload.get("progress")
        raw_stage = progress.get("stage") if isinstance(progress, dict) else payload.get("phase")
    if isinstance(raw_stage, str) and raw_stage:
        info = normalize_stage(raw_stage)
        payload.setdefault("stage_group", info.group)
        payload.setdefault("stage", info.stage)
        payload.setdefault("label", info.label)
        payload.setdefault("raw_stage", raw_stage)
    return payload


def _buffered_text_chunks(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[。！？.!?])\s*", text) if part]


def build_runtime(workspace_root: str | Path = ".", llm: Any | None = None, adapter_specs: list[Any] | None = None) -> AgentLoop:
    from .insightforge_adapters import build_insightforge_adapter_specs
    root = Path(workspace_root).resolve()
    session_index = SessionIndex(root)
    specs = adapter_specs if adapter_specs is not None else build_insightforge_adapter_specs(root, session_index)
    registry = build_builtin_registry(root, session_index, specs)
    executor = ToolExecutor(registry, session_index)
    prompt_builder = PromptBuilder(root / "prompts", session_index, registry)
    resolved_llm = llm or OpenAICompatibleLLM()
    return AgentLoop(session_index, prompt_builder, registry, executor, resolved_llm, ContextCompactor(resolved_llm))
