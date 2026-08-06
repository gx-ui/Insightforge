import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent_runtime.llm import (
    AssistantMessage,
    OpenAICompatibleLLM,
    _assistant_message_from_langchain,
    _to_langchain_messages,
)


def _llm_with_mock_model():
    llm = OpenAICompatibleLLM(model="test", base_url="https://example.invalid/v1", api_key="test-key")
    mock_model = MagicMock()
    llm._chat_model = mock_model
    return llm, mock_model


class MessageConversionTests(unittest.TestCase):
    def test_converts_all_openai_roles_to_langchain(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"path": "a.txt"})}}
            ]},
            {"role": "tool", "tool_call_id": "c1", "name": "read_file", "content": "body"},
            {"role": "user", "content": [
                {"type": "text", "text": "obs"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA", "detail": "high"}},
            ]},
        ]
        lc = _to_langchain_messages(msgs)
        self.assertIsInstance(lc[0], SystemMessage)
        self.assertIsInstance(lc[1], HumanMessage)
        self.assertIsInstance(lc[2], AIMessage)
        self.assertEqual(lc[2].tool_calls[0]["name"], "read_file")
        self.assertEqual(lc[2].tool_calls[0]["args"], {"path": "a.txt"})
        self.assertIsInstance(lc[3], ToolMessage)
        self.assertEqual(lc[3].tool_call_id, "c1")
        self.assertIsInstance(lc[4], HumanMessage)

    def test_assistant_tool_call_arguments_string_is_parsed(self):
        lc = _to_langchain_messages([{
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "x", "type": "function", "function": {"name": "f", "arguments": '{"a": 1}'}}],
        }])
        self.assertEqual(lc[0].tool_calls[0]["args"], {"a": 1})

    def test_malformed_arguments_string_falls_back_to_empty_dict(self):
        lc = _to_langchain_messages([{
            "role": "assistant", "content": "",
            "tool_calls": [{"id": "x", "type": "function", "function": {"name": "f", "arguments": "not-json"}}],
        }])
        self.assertEqual(lc[0].tool_calls[0]["args"], {})

    def test_assistant_message_from_langchain_preserves_text_and_tool_calls(self):
        ai = AIMessage(content="hello", tool_calls=[{"name": "f", "args": {"a": 1}, "id": "c1"}])
        msg = _assistant_message_from_langchain(ai)
        self.assertEqual(msg.text, "hello")
        self.assertEqual(len(msg.tool_calls), 1)
        self.assertEqual(msg.tool_calls[0].name, "f")
        self.assertEqual(msg.tool_calls[0].arguments, {"a": 1})
        self.assertEqual(msg.tool_calls[0].id, "c1")
        self.assertTrue(msg.raw_message)


class CompleteBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_plain_text_response(self):
        llm, mock_model = _llm_with_mock_model()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="hello there"))
        msg = await llm.complete([{"role": "user", "content": "hi"}], tools=[])
        self.assertEqual(msg.text, "hello there")
        self.assertEqual(msg.tool_calls, [])

    async def test_tool_call_response_maps_to_tool_calls(self):
        llm, mock_model = _llm_with_mock_model()
        bound = MagicMock()
        bound.ainvoke = AsyncMock(return_value=AIMessage(content="", tool_calls=[
            {"name": "read_file", "args": {"path": "a.txt"}, "id": "c1"},
        ]))
        mock_model.bind_tools = MagicMock(return_value=bound)
        msg = await llm.complete([{"role": "user", "content": "read"}], tools=[
            {"type": "function", "function": {"name": "read_file", "parameters": {}}},
        ])
        self.assertEqual(msg.tool_calls[0].name, "read_file")
        self.assertEqual(msg.tool_calls[0].arguments, {"path": "a.txt"})
        self.assertEqual(msg.tool_calls[0].id, "c1")

    async def test_tool_request_falls_back_to_plain_chat(self):
        llm, mock_model = _llm_with_mock_model()
        bound = MagicMock()
        bound.ainvoke = AsyncMock(side_effect=RuntimeError("tool not supported by relay"))
        mock_model.bind_tools = MagicMock(return_value=bound)
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="plain fallback"))
        msg = await llm.complete([{"role": "user", "content": "x"}], tools=[
            {"type": "function", "function": {"name": "x", "parameters": {}}},
        ])
        self.assertEqual(msg.text, "plain fallback")
        self.assertEqual(mock_model.bind_tools.call_count, 1)
        self.assertEqual(mock_model.ainvoke.call_count, 1)

    async def test_plain_chat_failure_propagates(self):
        llm, mock_model = _llm_with_mock_model()
        mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("auth failed"))
        with self.assertRaises(RuntimeError):
            await llm.complete([{"role": "user", "content": "x"}], tools=[])

    async def test_both_tool_and_plain_fail_propagates_plain_error(self):
        llm, mock_model = _llm_with_mock_model()
        bound = MagicMock()
        bound.ainvoke = AsyncMock(side_effect=RuntimeError("tool err"))
        mock_model.bind_tools = MagicMock(return_value=bound)
        mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("real error"))
        with self.assertRaises(RuntimeError):
            await llm.complete([{"role": "user", "content": "x"}], tools=[
                {"type": "function", "function": {"name": "x", "parameters": {}}},
            ])

    async def test_no_tools_does_not_bind_tools(self):
        llm, mock_model = _llm_with_mock_model()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
        mock_model.bind_tools = MagicMock()
        await llm.complete([{"role": "user", "content": "hi"}], tools=[])
        self.assertEqual(mock_model.bind_tools.call_count, 0)


class ConstructionTests(unittest.TestCase):
    def test_constructor_raises_without_api_key(self):
        from unittest.mock import patch
        with patch('agent_runtime.llm.llm_api_key', return_value=''), patch('agent_runtime.llm.llm_model', return_value='m'), patch('agent_runtime.llm.llm_base_url', return_value='http://localhost:1'), patch('agent_runtime.llm.llm_model_provider', return_value='openai'):
            with self.assertRaises(RuntimeError):
                OpenAICompatibleLLM()
    def test_constructor_uses_provided_params(self):
        llm = OpenAICompatibleLLM(model="my-model", base_url="https://example.invalid/v1", api_key="k")
        self.assertEqual(llm.model, "my-model")
        self.assertEqual(llm.base_url, "https://example.invalid/v1")
        self.assertEqual(llm.api_key, "k")


if __name__ == "__main__":
    unittest.main()
