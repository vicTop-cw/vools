"""
持久化缓存装饰器 (persist decorator)

将函数的执行结果缓存到本地文件，并提供灵活的刷新控制。
"""

import time
import json
import re
import os
import threading
from functools import wraps
from inspect import signature, getfile
from typing import Any, Callable, Optional, Dict

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

try:
    import msvcrt
    HAS_MSVC = True
except ImportError:
    HAS_MSVC = False

__all__ = ['persist', 'FileLock']


def sanitize_file_key(file_key: str) -> str:
    """
    安全清理文件名，防止路径遍历攻击
    
    Args:
        file_key: 原始文件名
    
    Returns:
        清理后的安全文件名
    
    Raises:
        ValueError: 当文件名包含危险字符时
    """
    if not file_key:
        raise ValueError("文件名不能为空")
    
    sanitized = re.sub(r'[\\/:\*\?"<>\|]', '_', file_key)
    sanitized = sanitized.replace('..', '')
    sanitized = re.sub(r'_+', '_', sanitized)
    sanitized = sanitized.strip('_')
    
    if len(sanitized) > 255:
        sanitized = sanitized[:255]
    
    if not sanitized:
        raise ValueError("文件名清理后为空")
    
    return sanitized


class FileLock:
    """跨平台文件锁"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.lock_file_path = f"{file_path}.lock"
        self._lock_fd = None
    
    def acquire(self):
        """获取锁"""
        self._lock_fd = open(self.lock_file_path, 'w')
        if HAS_FCNTL:
            try:
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
        elif HAS_MSVC:
            try:
                msvcrt.locking(self._lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
            except Exception:
                pass
    
    def release(self) -> None:
        """释放锁"""
        if self._lock_fd:
            if HAS_FCNTL:
                try:
                    fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
            elif HAS_MSVC:
                try:
                    msvcrt.locking(self._lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            try:
                self._lock_fd.close()
            except Exception:
                pass
            self._lock_fd = None
    
    def __enter__(self):
        self.acquire()
        return self
    

    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def _default_force_when_by_day(result: Any, start: float, end: float) -> bool:
    """
    应用于 persist 装饰器的目标函数，force_when 参数
    该函数 实现 同一天内只跑一次的效果
    """
    import datetime
    f = lambda x: datetime.datetime.fromtimestamp(x).date()
    p = f(start) == f(end) == datetime.datetime.today().date()
    return not p


def persist(func: Optional[Callable] = None, 
           *, 
           file_key: Optional[str] = None,
           force: bool = False,
           force_when: Optional[Callable[[Any, float, float], bool]] = None,
           target_folder: Optional[str] = None) -> Callable:
    """
    装饰器：将函数的执行结果缓存到本地文件，并提供灵活的刷新控制。

    参数:
        func: 要装饰的函数（可选）
        file_key: 缓存文件名（不含扩展名），默认使用函数名
        force: 是否强制重新执行，默认 False
        force_when: 当 force=False 时，若此函数返回 True 则强制刷新
                    该函数接收三个参数：缓存结果、上次执行的开始时间戳、结束时间戳
        target_folder: 缓存文件所在目录，默认与被装饰函数所在文件同级的 __persist__ 目录

    被装饰的函数会自动获得以下关键字参数（可在调用时覆盖装饰器参数）：
        file_key: str = None
        force: bool = False
        force_when: Optional[Callable[[Any,float, float], bool]] = None
        target_folder: str = None

    要求：
        - 函数返回值必须可 JSON 序列化（基本类型、列表、字典、None）。
        - 缓存文件保存为 JSON 格式，包含 result、start_time、end_time。

    示例:
        >>> @persist
        ... def fetch_data():
        ...     return {"data": "value"}
        
        >>> @persist(file_key="custom_cache", target_folder="/tmp/cache")
        ... def fetch_data_with_config():
        ...     return {"data": "value"}
    """
    # 参数类型验证
    if file_key is not None and not isinstance(file_key, str):
        raise TypeError(
            f"参数 'file_key' 类型错误: 期望 str 或 None, 实际收到 {type(file_key).__name__}。\n"
            f"修复建议: 使用字符串作为缓存文件名，例如:\n"
            f"  - @persist(file_key='my_cache')  # 缓存文件名为 my_cache.json\n"
            f"  - @persist()                     # 使用函数名作为缓存文件名\n"
        )
    
    if not isinstance(force, bool):
        raise TypeError(
            f"参数 'force' 类型错误: 期望 bool, 实际收到 {type(force).__name__}。\n"
            f"修复建议: 使用布尔值，例如:\n"
            f"  - @persist(force=True)   # 强制重新执行\n"
            f"  - @persist(force=False)  # 使用缓存（默认行为）\n"
        )
    
    if force_when is not None and not callable(force_when):
        raise TypeError(
            f"参数 'force_when' 类型错误: 期望 callable 或 None, 实际收到 {type(force_when).__name__}。\n"
            f"修复建议: 使用函数作为刷新条件判断器，例如:\n"
            f"  - @persist(force_when=lambda result, start, end: time.time() - end > 3600)  # 超过1小时刷新\n"
            f"  - @persist(force_when=lambda result, start, end: result['status'] == 'expired')  # 结果过期时刷新\n"
            f"替代方案: 使用 force=True 直接强制刷新\n"
        )
    
    if target_folder is not None and not isinstance(target_folder, str):
        raise TypeError(
            f"参数 'target_folder' 类型错误: 期望 str 或 None, 实际收到 {type(target_folder).__name__}。\n"
            f"修复建议: 使用字符串作为缓存目录路径，例如:\n"
            f"  - @persist(target_folder='/tmp/cache')  # 使用指定目录\n"
            f"  - @persist()                             # 使用默认 __persist__ 目录\n"
        )
    
    # 使用默认配置
    default_force_when = force_when if force_when is not None else _default_force_when_by_day
    default_target_folder = target_folder
    
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 从调用参数中获取，如果没有则使用装饰器参数
            call_file_key = kwargs.pop('file_key', file_key)
            call_force = kwargs.pop('force', force)
            call_force_when = kwargs.pop('force_when', default_force_when)
            call_target_folder = kwargs.pop('target_folder', default_target_folder)

            if call_file_key is None:
                call_file_key = f.__name__
            else:
                call_file_key = sanitize_file_key(call_file_key)

            if call_target_folder:
                cache_dir = call_target_folder
            else:
                func_file = getfile(f)
                cache_dir = os.path.join(os.path.dirname(func_file), "__persist__")
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, f"{call_file_key}.json")

            cache_data = None
            need_refresh = call_force
            
            if not need_refresh and os.path.exists(cache_path):
                with FileLock(cache_path):
                    try:
                        with open(cache_path, "r", encoding="utf-8") as f_cache:
                            cache_data = json.load(f_cache)
                    
                        result = cache_data.get('result')
                        start_time = cache_data.get('start_time')
                        end_time = cache_data.get('end_time')
                        
                        if call_force_when is not None and start_time is not None and end_time is not None:
                            if call_force_when(result, start_time, end_time):
                                need_refresh = True
                    except Exception:
                        need_refresh = True
                        cache_data = None

            if not need_refresh and cache_data is not None:
                return cache_data['result']
            
            start_time = time.time()
            result = f(*args, **kwargs)
            end_time = time.time()

            try:
                json.dumps(result)
            except (TypeError, ValueError) as e:
                raise TypeError(
                    f"函数 '{f.__name__}' 返回值无法 JSON 序列化。\n"
                    f"错误详情: {type(e).__name__}: {e}\n"
                    f"当前返回值类型: {type(result).__name__}\n"
                    f"修复建议:\n"
                    f"  1. 确保返回值是基本 JSON 类型:\n"
                    f"     - 基本类型: str, int, float, bool, None\n"
                    f"     - 容器类型: list, dict (元素也必须可序列化)\n"
                    f"  2. 如果需要缓存复杂对象，考虑:\n"
                    f"     - 使用 pickle 序列化（需要自定义实现）\n"
                    f"     - 将对象转换为可序列化的字典格式\n"
                    f"     - 只缓存对象的关键属性\n"
                    f"示例:\n"
                    f"  # 正确: 返回字典\n"
                    f"  def fetch_data(): return {{'data': 'value', 'count': 42}}\n"
                    f"  # 错误: 返回不可序列化对象\n"
                    f"  def fetch_data(): return datetime.now()  # datetime 不可直接序列化\n"
                )

            with FileLock(cache_path):
                cache_data = {
                    'result': result,
                    'start_time': start_time,
                    'end_time': end_time,
                }
                with open(cache_path, "w", encoding="utf-8") as f_cache:
                    json.dump(cache_data, f_cache, ensure_ascii=False, indent=2)

            return result

        return wrapper
    
    # 支持两种调用方式
    if func is None:
        # @persist(file_key="cache") 带参数调用
        return decorator
    else:
        # @persist 直接调用
        return decorator(func)

