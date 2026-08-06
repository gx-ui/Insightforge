"""
InsightForge 对话模型的供应商预设系统。

支持自动检测和解析 LLM 供应商设置，
允许用户指定供应商名称（例如 ``minimax``）而无需
手动配置 base_url 和模型详情。
"""

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 供应商预设
# ---------------------------------------------------------------------------

PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "minimax": {
        "base_url": "https://api.minimax.io/v1",
        "env_key": "MINIMAX_API_KEY",
        "default_model": "MiniMax-M3",
        "models": [
            "MiniMax-M3",
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
        ],
        "temperature_range": (0.0, 1.0),
    },
}


def resolve_chat_model_config(init_args: Dict[str, Any]) -> Dict[str, Any]:
    """解析供应商预设并返回最终的 ``init_chat_model`` 参数。

    若 ``model_provider`` 匹配已知预设（例如 ``minimax``），返回的字典将包含：

    * ``model_provider`` 改写为 ``"openai"``（OpenAI 兼容 API）
    * ``base_url`` 在未设置时从预设中填充
    * ``api_key`` 在未设置时从环境变量获取
    * ``model`` 在未设置时默认为预设的默认模型
    * ``temperature`` 限制在供应商支持的范围内

    对于未知供应商，字典原样返回。
    """
    args = dict(init_args)  # 浅拷贝
    provider = args.get("model_provider", "openai")

    preset = PROVIDER_PRESETS.get(provider)
    if preset is None:
        return args

    # base_url
    if not args.get("base_url"):
        args["base_url"] = preset["base_url"]

    # api_key -- 回退到环境变量
    if not args.get("api_key"):
        env_key = preset.get("env_key", "")
        env_val = os.environ.get(env_key, "")
        if env_val:
            args["api_key"] = env_val
            logger.info("Using %s API key from environment variable %s", provider, env_key)

    # 默认模型
    if not args.get("model"):
        args["model"] = preset["default_model"]
        logger.info("Defaulting to model %s for provider %s", args["model"], provider)

    # temperature 裁剪
    temp_range = preset.get("temperature_range")
    if temp_range and "temperature" in args and args["temperature"] is not None:
        lo, hi = temp_range
        original = args["temperature"]
        args["temperature"] = max(lo, min(hi, original))
        if args["temperature"] != original:
            logger.warning(
                "Clamped temperature %.2f -> %.2f for provider %s",
                original, args["temperature"], provider,
            )

    # 改写为 LangChain 兼容的 openai 供应商
    args["model_provider"] = "openai"

    return args


def detect_provider_from_env() -> Optional[str]:
    """返回在环境变量中找到 API key 的供应商名称。

    按定义顺序检查 ``PROVIDER_PRESETS``，返回第一个匹配项，
    若未设置任何 key 则返回 ``None``。
    """
    for name, preset in PROVIDER_PRESETS.items():
        env_key = preset.get("env_key", "")
        if env_key and os.environ.get(env_key):
            return name
    return None