"""LLM provider 注册表。

解决「provider 名 → 可用客户端」的解析。两种名字都接受：

- **实现名**（'openai_compat' / 'anthropic'）—— 直接取登记的类
- **preset 别名**（'openai' / 'deepseek' / 'groq' / 'ollama' / 'vllm'）
  —— 经 PRESETS 解析出 base_url / model / 密钥环境变量后，
  落到 openai_compat 实现上（这 5 家都是 OpenAI 兼容端点）

刻意不内置任何默认 provider：import 本模块不会带来网络行为，
调用方需显式 import providers 或由 get_provider 惰性触发。

Example:
    >>> from vools.actus.ai.providers import openai_compat  # 触发登记
    >>> 'openai' in PRESETS
    True
"""

__all__ = ['PRESETS', 'register_provider', 'get_provider', 'available_providers']

from .base import LLMClient, llm_error_code
from ..errors import ActionError

# 已知 preset：name -> (base_url, model, env_name, needs_key)
# needs_key=False 的两家是本地推理端点，不校验密钥。
PRESETS = {
    'openai': ('https://api.openai.com/v1', 'gpt-4o-mini', 'OPENAI_API_KEY', True),
    'deepseek': ('https://api.deepseek.com/v1', 'deepseek-chat', 'DEEPSEEK_API_KEY', True),
    'groq': ('https://api.groq.com/openai/v1', 'llama-3.1-8b', 'GROQ_API_KEY', True),
    'ollama': ('http://localhost:11434/v1', 'qwen2.5-coder', '', False),
    'vllm': ('http://localhost:8000/v1', '', '', False),
}

# provider 名 → LLMClient 子类。由 @register_provider 填充。
_PROVIDERS = {}

# 惰性加载标记：只有真的有人要用 provider 时才 import 实现模块，
# 这样 `import vools.actus.ai` 本身不带来任何网络行为或实现加载。
_PROVIDERS_LOADED = False
# 实现加载失败时的原始原因（None 表示没失败过），供排查用
providers_load_error = None


def _ensure_providers():
    """确保 provider 实现已登记。幂等。

    副作用：首次调用时 import providers 子包，触发 @register_provider。

    实现加载失败时**不让异常静默消失** —— 之前这里 `except ImportError: pass`，
    结果调用方只看到「请先 import providers」这种误导性提示，真实原因
    （比如循环导入、依赖缺失）被彻底掩盖，排查成本极高。
    现在把原始异常记在 `providers_load_error` 里，并在报错里带上。

    Returns:
        None

    Raises:
        ImportError: 实现模块加载失败时原样抛出。
    """
    global _PROVIDERS_LOADED, providers_load_error
    if _PROVIDERS_LOADED:
        return
    try:
        from . import providers  # noqa: F401  —— 副作用即登记
    except ImportError as e:
        providers_load_error = str(e)
        raise
    _PROVIDERS_LOADED = True


def register_provider(cls):
    """把 LLMClient 子类登记进全局表。

    Args:
        cls: LLMClient 的子类。类属性 `name` 即登记名。

    Returns:
        type: 原类，便于继续当装饰器用。

    Raises:
        ActionError: code='param_invalid'，类未继承 LLMClient 或缺 name。
    """
    if not (isinstance(cls, type) and issubclass(cls, LLMClient)):
        raise ActionError(llm_error_code('param_invalid'),
                          'register_provider 只接受 LLMClient 子类，得到 %r' % (cls,))
    name = getattr(cls, 'name', '')
    if not name or name == 'abstract':
        raise ActionError(llm_error_code('param_invalid'),
                          'provider 类必须给出非抽象的 name 属性: %r' % (cls,))
    _PROVIDERS[name] = cls
    return cls


def get_provider(name, **kwargs):
    """按名字取 provider 实例。

    Args:
        name: 实现名（'openai_compat'/'anthropic'）或 preset 别名
            （'openai'/'deepseek'/'groq'/'ollama'/'vllm'）。大小写不敏感。
        **kwargs: 构造覆盖项，如 base_url / model / api_key / timeout。
            显式传入的值优先于 preset 解析出的值。

    Returns:
        LLMClient: 就绪的客户端实例。

    Raises:
        ActionError: code='param_invalid'（provider 名未登记），
            details 带已知名字列表。
    """
    key = (name or '').strip().lower()
    _ensure_providers()
    if not key:
        raise ActionError(llm_error_code('unknown_provider'),
                          'provider 名为空',
                          {'known': sorted(set(_PROVIDERS) | set(PRESETS))})

    if key in _PROVIDERS:
        return _PROVIDERS[key](**kwargs)

    if key in PRESETS:
        base_url, model, env_name, needs_key = PRESETS[key]
        options = {'base_url': base_url, 'model': model, 'env_name': env_name,
                   'name': 'openai_compat'}
        options.update(kwargs)
        # preset 别名一律走 OpenAI 兼容端点形状
        impl = _PROVIDERS.get('openai_compat')
        if impl is None:
            raise ActionError(llm_error_code('unknown_provider'),
                              'openai_compat 实现未登记，请先 import providers',
                              {'known': sorted(_PROVIDERS)})
        return impl(**options)

    raise ActionError(llm_error_code('unknown_provider'),
                      '未知的 LLM provider: %r' % (name,),
                      {'known': sorted(set(_PROVIDERS) | set(PRESETS))})


def available_providers():
    """列出已登记的实现名与可用的 preset 别名。

    会触发 provider 实现的惰性加载，因此本函数是「有哪些 provider 可用」
    的权威问答入口。

    Returns:
        List[str]: 排序后的名字列表（实现名 + preset 别名）。

    Example:
        >>> names = available_providers()
        >>> 'openai' in names and 'openai_compat' in names
        True
    """
    _ensure_providers()
    return sorted(set(_PROVIDERS) | set(PRESETS))