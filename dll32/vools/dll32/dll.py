"""
@dll32 装饰器

用于调用 32 位 DLL 函数，通过嵌入式 32 位 Python 进程执行。
"""
import os
import ctypes
from typing import Optional, Callable, Any

from ._core._pipe_comm import call_dll


def dll32(dll_spec: str, *, async_mode: bool = False, fallback: Optional[Callable] = None):
    """
    32 位 DLL 调用装饰器
    
    Args:
        dll_spec: DLL 规格，格式为 "path/to/dll::func_name"
        async_mode: 是否启用异步模式
        fallback: 回退函数
    
    用法:
        @dll32('E:/dlls/VB6Plus.dll::Base64Encode_UTF8')
        def base64_encode(input: str, output: bytes, outLen: int) -> int:
            pass
    """
    # 解析 dll_spec
    if '::' in dll_spec:
        dll_path, func_name = dll_spec.rsplit('::', 1)
    else:
        dll_path = dll_spec
        func_name = None
    
    # 转换为绝对路径（如果需要）
    if not os.path.isabs(dll_path):
        # 尝试相对于 _dlls 目录
        _dlls_dir = os.path.join(os.path.dirname(__file__), '_dlls')
        dll_path = os.path.join(_dlls_dir, dll_path)
    
    def decorator(func):
        # 获取函数签名
        import inspect
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())
        is_method = len(param_names) > 0 and param_names[0] == 'self'
        
        def wrapper(*args, **kwargs):
            try:
                # 通过管道调用 32 位 Python
                # 使用 signature.bind 获取完整参数（包含默认值）
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                call_args = list(bound.arguments.values())
                if is_method and len(call_args) > 0:
                    call_args = call_args[1:]
                result = call_dll(dll_path, func_name or func.__name__, call_args)
                return result
            except Exception as e:
                # 回退
                if fallback:
                    return fallback(*args, **kwargs)
                elif func.__code__.co_consts:
                    # 函数体作为 fallback
                    return func(*args, **kwargs)
                else:
                    raise
        
        if async_mode:
            import asyncio
            async def async_wrapper(*args, **kwargs):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, wrapper, *args, **kwargs)
            return async_wrapper
        
        return wrapper
    
    return decorator