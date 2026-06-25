"""
inspect 兼容层 — 统一处理 Python 不同版本的 inspect 接口

在高版本 Python 使用标准库 inspect 的原生接口，
在低版本提供兼容实现或回退方案。

提供与标准库一致的常用接口：
- signature(func)               → 获取函数签名
- Parameter                     → 参数类
- Parameter.empty               → 空值标记
- Parameter.VAR_POSITIONAL      → *args 类型
- Parameter.VAR_KEYWORD         → **kwargs 类型
- getsource(func)               → 获取源代码
- iscoroutinefunction(func)     → 是否是协程函数
- isclass(obj)                  → 是否是类
- isfunction(obj)               → 是否是函数
- Signature                     → 签名类
- getfile(func)                 → 获取文件路径
"""

__all__ = [
    'signature',
    'Parameter',
    'Signature',
    'getsource',
    'iscoroutinefunction',
    'isclass',
    'isfunction',
    'getfile',
]

import inspect
import sys


# ================================================================
# 检测运行环境
# ================================================================

# 3.6+ 基本的 inspect 功能都有，这里主要为未来版本兼容预留
# 以及统一入口，方便后续添加更多兼容功能

signature = inspect.signature
Parameter = inspect.Parameter
Signature = inspect.Signature
getsource = inspect.getsource
iscoroutinefunction = inspect.iscoroutinefunction
isclass = inspect.isclass
isfunction = inspect.isfunction
getfile = inspect.getfile
