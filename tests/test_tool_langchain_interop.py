"""Phase 2 interop guard: the hand-written ToolRegistry schemas must remain
acceptable to langchain's bind_tools, because Phase 3's model node binds tools
via the OpenAI-format dicts produced by list_function_tools().

A full StructuredTool migration was deferred (see plan.md Phase 2): langchain's
convert_to_openai_tool cannot reproduce the additionalProperties:false field
that all 13 builtin tools expose, so migrating the schema generation would
break the "schema diff = empty" contract. The existing ToolRegistry already
interops with langchain, and Phase 3's custom tool node reuses ToolExecutor
directly (no ToolNode/StructuredTool required).
"""

import tempfile
import unittest

from langchain.chat_models import init_chat_model

from agent_runtime.session_index import SessionIndex
from agent_runtime.tools import build_builtin_registry


class ToolSchemaLangchainInteropTests(unittest.TestCase):
    def test_all_builtin_tool_schemas_accepted_by_bind_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = SessionIndex(tmp)
            registry = build_builtin_registry(tmp, index, [])
            tools = registry.list_function_tools()
            self.assertEqual(len(tools), 13)
            model = init_chat_model(model="test", model_provider="openai", api_key="k", base_url="http://localhost:1")
            # 不得抛出异常：每个 schema 都与 bind_tools 兼容
            bound = model.bind_tools(tools)
            self.assertIsNotNone(bound)

    def test_every_tool_schema_has_additional_properties_false(self):
        """契约不变量：所有工具参数都携带 additionalProperties:false。"""
        with tempfile.TemporaryDirectory() as tmp:
            index = SessionIndex(tmp)
            registry = build_builtin_registry(tmp, index, [])
            for tool in registry.list_function_tools():
                params = tool["function"]["parameters"]
                self.assertIn(
                    "additionalProperties", params,
                    f"{tool['function']['name']} missing additionalProperties",
                )
                self.assertFalse(params["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
