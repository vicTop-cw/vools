# vools.actus.ai.providers —— LLM provider 实现

导入本包即完成全部实现的登记（`@register_provider` 是副作用）。

```python
>>> from vools.actus.ai import get_provider
>>> get_provider('openai').base_url          # 惰性触发本包导入
'https://api.openai.com/v1'
```

不想被隐式登记就直接导具体模块：

```python
>>> from vools.actus.ai.providers.openai_compat import OpenAICompatClient
```

`vools.actus.ai/__init__.py` **刻意不 import 本包** —— 让 `import vools.actus.ai`
不带来任何实现加载与网络行为。`registry.get_provider()` / `available_providers()`
会在被调用时惰性触发导入。

## 实现清单

| 模块 | 实现名 | 覆盖 | 备注 |
|---|---|---|---|
| `openai_compat` | `openai_compat` | openai / deepseek / groq / ollama / vllm | 都提供 `POST {base_url}/chat/completions`，差异只在 base_url、默认模型与密钥变量，已由 `registry.PRESETS` 表达 |
| `anthropic` | `anthropic` | Anthropic Messages API | 形状差异有三处（`system` 是顶层字段、content 是块数组、参数键叫 `input_schema`），独立成实现而不是在兼容端点里堆分支 |

## preset 一览

```python
>>> from vools.actus.ai import PRESETS
>>> PRESETS['openai']
('https://api.openai.com/v1', 'gpt-4o-mini', 'OPENAI_API_KEY', True)
>>> PRESETS['ollama'][3]      # 第 4 项 needs_key
False
```

| preset | base_url | 默认模型 | 密钥环境变量 | 需密钥 |
|---|---|---|---|---|
| `openai` | `https://api.openai.com/v1` | gpt-4o-mini | `OPENAI_API_KEY` | 是 |
| `deepseek` | `https://api.deepseek.com/v1` | deepseek-chat | `DEEPSEEK_API_KEY` | 是 |
| `groq` | `https://api.groq.com/openai/v1` | llama-3.1-8b | `GROQ_API_KEY` | 是 |
| `ollama` | `http://localhost:11434/v1` | qwen2.5-coder | — | 否 |
| `vllm` | `http://localhost:8000/v1` | 端点自定 | — | 否 |

密钥解析顺序：**构造参数 `api_key` → `env_name` 指向的环境变量**。
动作侧通过 Vault secrets 注入走的就是环境变量。

## 三条硬约定

1. **`complete()` 永不抛异常。** 失败一律返回 `LLMResponse(stop_reason='error')`，
   错误类别与归一后的码放在 `resp.raw['error_kind']` / `resp.raw['code']`。
2. **`available()` 永不抛异常。** 无密钥返回 `False`；本地端点（`ollama`/`vllm`）
   发一次 2 秒超时的 `GET {base_url}/models`，失败返回 `False`。
   `anthropic` 不做网络探测（该 API 无 `/models` 端点），只看密钥。
3. **`stream=True` 显式报未实现**，不静默降级成非流式结果 ——
   静默降级会让调用方误以为拿到的是增量内容。

## 验证状态

| 实现 | 覆盖情况 |
|---|---|
| `openai_compat` | 响应解析（tool_calls / usage 缺失 / 各种形状错误）与无密钥路径有 mock 判据；**未用真实密钥端到端实测** |
| `anthropic` | **只有 mock 覆盖，无真机密钥实测**。首次接入前请用真实密钥跑一次 `complete([Message(role='user', content='hi')])`，核对 token 计数与 `stop_reason` 取值 |

## 写新 provider 的清单

```python
from ..base import LLMResponse, LLMClient, llm_error_code
from ..registry import register_provider

@register_provider
class MyProvider(LLMClient):
    name = 'my_provider'

    def complete(self, messages, tools=None, temperature=0.0,
                 max_tokens=None, stream=False):
        if stream:
            return LLMResponse(content='stream 未实现', stop_reason='error',
                               raw={'error_kind': 'param_invalid',
                                    'code': llm_error_code('param_invalid')})
        ...

    def available(self):
        return True      # 探测失败返回 False，不要抛
```

要点：类属性 `name` 即登记名；只依赖标准库；错误码必须取自 `ERROR_CODES`
（用 `llm_error_code()` 归一，不要自己造码）。
