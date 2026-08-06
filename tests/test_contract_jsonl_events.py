"""Phase 0 contract gate: freeze the exact JSONL event sequence the AgentLoop emits.

This is the highest-priority frozen contract (see plan.md S1.1). Every later phase
(especially Phase 3, where the hand-written loop becomes a LangGraph StateGraph)
must keep these event sequences and field shapes byte-for-byte equivalent.

Scenarios mirror the four event_bridge prototype-gate cases:
  A. plain text reply (no tool calls)
  B. one tool call then finish
  C. LLM sampling error
  D. preflight compaction
"""

import asyncio
import tempfile
import unittest

from agent_runtime.context_compactor import ContextCompactor
from agent_runtime.llm import AssistantMessage
from agent_runtime.loop import AgentLoop
from agent_runtime.models import ToolCall, ToolResult
from agent_runtime.prompts import PromptBuilder
from agent_runtime.session_index import SessionIndex
from agent_runtime.tool_executor import ToolExecutor
from agent_runtime.tools import ToolArgumentSchema, ToolRegistry, ToolSpec


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    async def complete(self, messages, tools):
        return self.replies.pop(0)


class FailingLLM:
    async def complete(self, messages, tools):
        raise RuntimeError("provider returned invalid response shape")


def _build_loop(tmp, llm, registry=None, compactor=None):
    index = SessionIndex(tmp)
    registry = registry or ToolRegistry([])
    builder = PromptBuilder(f"{tmp}/prompts", index, registry)
    return index, AgentLoop(index, builder, registry, ToolExecutor(registry, index), llm, compactor)


def _type_phase(event):
    """将事件归约为其 (类型, phase 或键) 签名以进行黄金比对。"""
    t = event["type"]
    if t == "status":
        return (t, event.get("phase"))
    if t == "tool_start":
        return (t, event.get("tool", {}).get("name"))
    if t == "tool_result":
        return (t, event.get("tool_result", {}).get("name"))
    if t == "tool_progress":
        return (t, event.get("tool", {}).get("name"))
    if t == "error":
        return (t, event.get("metadata", {}).get("error_type"))
    return t


class JsonlEventContractTests(unittest.IsolatedAsyncioTestCase):
    async def _events(self, loop, user_input):
        return [_type_phase(e) async for e in loop.stream_events(user_input)]

    async def test_scenario_a_plain_text_reply_event_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, loop = _build_loop(tmp, FakeLLM([AssistantMessage(text="hello there")]))
            seq = await self._events(loop, "hi")
            self.assertEqual(
                seq,
                ["turn", "prompt_trace", ("status", "sampling_assistant"),
                 "token", "done", "session"],
            )

    async def test_scenario_b_one_tool_call_then_finish_event_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            def hello(args):
                return ToolResult("hello", True, "hello result")

            registry = ToolRegistry([ToolSpec("hello", "Say hello", hello, schema={"name": ToolArgumentSchema(str, False, "x")})])
            llm = FakeLLM([
                AssistantMessage(tool_calls=[ToolCall(name="hello", arguments={})]),
                AssistantMessage(text="finished"),
            ])
            _, loop = _build_loop(tmp, llm, registry)
            seq = await self._events(loop, "start")
            self.assertEqual(
                seq,
                ["turn", "prompt_trace",
                 ("status", "sampling_assistant"),
                 ("status", "executing_tools"),
                 ("tool_start", "hello"),
                 ("tool_result", "hello"),
                 ("status", "sampling_assistant"),
                 "token", "done", "session"],
            )

    async def test_scenario_c_llm_sampling_error_event_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, loop = _build_loop(tmp, FailingLLM())
            seq = await self._events(loop, "start")
            self.assertEqual(
                seq,
                ["turn", "prompt_trace",
                 ("status", "sampling_assistant"),
                 ("error", "llm_sampling_failed"),
                 "done", "session"],
            )

    async def test_scenario_d_preflight_compaction_event_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            index, loop = _build_loop(
                tmp,
                FakeLLM([AssistantMessage(text="after compact")]),
                compactor=ContextCompactor(None, token_threshold=200, buffer_tokens=0, preserve_last_n=2, summary_max_chars=2000),
            )
            loop.history = [
                {"role": "user", "content": "old request " + "x" * 1200},
                {"role": "assistant", "content": "old answer " + "y" * 1200},
                {"role": "user", "content": "recent request"},
                {"role": "assistant", "content": "recent answer"},
            ]
            seq = await self._events(loop, "continue")
            self.assertEqual(
                seq,
                ["turn",
                 ("status", "compact"),
                 "prompt_trace",
                 ("status", "sampling_assistant"),
                 "token", "done", "session"],
            )
            self.assertIn("Reference Context Only", index.active()["compacted_summary"])

    async def test_every_event_carries_turn_id_and_done_has_required_fields(self):
        """字段形状不变量：每个事件都有 turn_id；done 携带 assistant+tool_results。"""
        with tempfile.TemporaryDirectory() as tmp:
            def hello(args):
                return ToolResult("hello", True, "hello result")

            registry = ToolRegistry([ToolSpec("hello", "Say hello", hello, schema={"name": ToolArgumentSchema(str, False, "x")})])
            llm = FakeLLM([
                AssistantMessage(tool_calls=[ToolCall(name="hello", arguments={})]),
                AssistantMessage(text="finished"),
            ])
            _, loop = _build_loop(tmp, llm, registry)
            events = [e async for e in loop.stream_events("start")]
            turn_id = events[0]["turn_id"]
            self.assertTrue(events[0]["type"] == "turn")
            for event in events:
                if event["type"] in {"token", "status", "tool_start", "tool_progress", "tool_result", "error", "done", "session", "prompt_trace"}:
                    self.assertEqual(event.get("turn_id"), turn_id, f"event {event['type']} missing turn_id")
            done = next(e for e in events if e["type"] == "done")
            self.assertEqual(done["assistant"], "finished")
            self.assertEqual(len(done["tool_results"]), 1)
            self.assertEqual(done["tool_results"][0]["name"], "hello")
            session_event = events[-1]
            self.assertEqual(session_event["type"], "session")
            self.assertIn("artifact_checklist", session_event["session"])


if __name__ == "__main__":
    unittest.main()
