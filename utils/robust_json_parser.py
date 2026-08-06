# 某些对话模型（在通过 OpenAI 兼容端点调用 gemini-flash-lite 时观察到）
# 经常在结构化 JSON 响应的闭合 `}`/`]` 之前输出一个尾随逗号
# （例如 `"variation_reason": "...",\n}`）。这是无效的 JSON，因此
# PydanticOutputParser 会抛出 OutputParserException，尽管负载在其他方面
# 格式良好且语义完整——而重新采样会消耗 LLM 调用次数，且往往以同样的方式再次失败。
# 包装 PydanticOutputParser，使得解析失败时先在本地尝试去除尾随逗号后重试，
# 再决定放弃。
import re
from typing import List, Optional

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.outputs import Generation

_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def strip_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA_RE.sub(r"\1", text)


class TrailingCommaTolerantPydanticOutputParser(PydanticOutputParser):
    """PydanticOutputParser 的扩展：解析失败时去除尾随逗号后重试一次。"""

    def parse_result(self, result: List[Generation], *, partial: bool = False):
        try:
            return super().parse_result(result, partial=partial)
        except OutputParserException:
            if not result:
                raise
            cleaned_text = strip_trailing_commas(result[0].text)
            if cleaned_text == result[0].text:
                raise
            cleaned_result = [Generation(text=cleaned_text)]
            return super().parse_result(cleaned_result, partial=partial)