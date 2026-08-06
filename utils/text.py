import re


def safe_path_component(name) -> str:
    """将 LLM 生成的标识符净化为可用的文件系统路径组件。

    标识符来源于模型基于用户故事文本的输出，可能包含分隔符或目录穿越序列；
    保留单词字符（含中文）、连字符、点和空格，其余字符统一替换，并去除前导点，
    确保结果不会逃出或隐藏在工作目录之外。
    """
    cleaned = re.sub(r"[^\w\-. ]", "_", str(name))
    cleaned = cleaned.strip().lstrip(".")
    return cleaned or "unnamed"