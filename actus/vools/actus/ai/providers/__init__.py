"""LLM provider 实现集。

导入本包即完成全部实现的登记（`@register_provider` 是副作用）。
不想被隐式登记的调用方请直接 import 具体模块：

    from vools.actus.ai.providers.openai_compat import OpenAICompatClient

本包只做登记与 re-export，不含逻辑。

| 模块 | 实现名 | 覆盖 |
|---|---|---|
| `openai_compat` | `openai_compat` | openai / deepseek / groq / ollama / vllm（均为 OpenAI 兼容端点） |
| `anthropic` | `anthropic` | Anthropic Messages API（形状不同，独立实现） |
"""

__all__ = ['OpenAICompatClient', 'AnthropicClient']

from .openai_compat import OpenAICompatClient
from .anthropic import AnthropicClient