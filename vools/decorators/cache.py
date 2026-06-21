"""
缓存相关装饰器

包含：
- memorize: 函数结果缓存装饰器
- once: 单次执行装饰器（支持函数和类）
- persist: 持久化缓存装饰器
"""

import time
import hashlib
import pickle
import os
import json
import re
import threading
from functools import wraps
from inspect import signature, isclass, getfile
from typing import Callable, Any, Optional, Dict
from collections import OrderedDict
from ..config import config

__all__ = ['memorize', 'once', 'persist']

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
    
    def release(self):
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


class TimedCache:
    """带过期时间和大小限制的缓存（线程安全）"""
    
    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()
    
    def _is_obsolete(self, entry: Dict[str, Any], duration: float) -> bool:
        """检查缓存是否过期"""
        return time.time() - entry['time'] > duration
    
    def get(self, key: str, duration: float) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if not self._is_obsolete(entry, duration):
                    self._cache.move_to_end(key)
                    return entry['result']
                del self._cache[key]
        return None
    
    def set(self, key: str, result: Any):
        """设置缓存值"""
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = {
                'result': result,
                'time': time.time()
            }
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    def __len__(self):
        """返回缓存条目数"""
        with self._lock:
            return len(self._cache)

    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function applied after f (no return expected)

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


_CACHE = TimedCache(max_size=1000)


def _compute_key(func: Callable, args: tuple, kwargs: dict) -> str:
    """计算缓存键"""
    key = pickle.dumps((func.__name__, args, kwargs))
    return hashlib.sha256(key).hexdigest()


def memorize(func: Callable = None, duration: float = 3) -> Callable:
    """
    函数结果缓存装饰器，缓存函数结果一段时间
    
    参数:
        func: 要装饰的函数
        duration: 缓存持续时间（秒），默认 3 秒
    
    返回:
        装饰后的函数
    
    示例:
        >>> @memorize
        ... def expensive_function(x):
        ...     return x ** 2
        
        >>> @memorize(duration=5)
        ... def another_function(x):
        ...     return x ** 3
        
        >>> class MyClass:
        ...     @memorize(duration=5)
        ...     def method(self, x):
        ...         return x * 2
    """
    @wraps(func)
    def wrapper(func):
        def _wrapper(*args, **kwargs):
            key = _compute_key(func, args, kwargs)
            
            cached_result = _CACHE.get(key, duration)
            if cached_result is not None:
                return cached_result
            
            result = func(*args, **kwargs)
            _CACHE.set(key, result)
            
            return result
        return _wrapper
    
    if func:
        return wrapper(func)
    return wrapper


class _OnceWrapper:
    """单次执行函数包装器"""
    
    __slots__ = ("func", "called", "result", "force", "called_args", 
                 "called_kwargs", "last_called_time", "__signature__")
    
    def __init__(self, func: Callable):
        self.func = func
        self.called = False
        self.result = None
        self.force = False
        self.called_args = None
        self.called_kwargs = None
        self.last_called_time = None
        self.__signature__ = signature(func)
    
    def __getstate__(self):
        """Return serialization state"""
        return {k: getattr(self, k) for k in ('func','called','result','force','called_args','called_kwargs','last_called_time')}
    def __setstate__(self, state):
        """Restore from serialization state"""
        for k, v in state.items():
            setattr(self, k, v)
        from inspect import signature
        self.__signature__ = signature(self.func)
        self.force_default = False

    def __call__(self, *args, **kwargs) -> Any:
        force = kwargs.pop("force", False)
        if force:
            self.force = True
        if self.called and not self.force:
            return self.result
        self.called_args = args
        self.called_kwargs = kwargs
        self.called = True
        self.force = False
        self.result = self.func(*args, **kwargs)
        self.last_called_time = time.time()
        return self.result


def once(obj: Any) -> Any:
    """
    单次执行装饰器，确保函数或类只执行/初始化一次
    
    对于函数：
        - 第一次调用时执行并缓存结果
        - 后续调用直接返回缓存结果
        - 可以通过 force=True 强制重新执行
    
    对于类：
        - 转换为单例模式
        - 所有实例共享同一个实例
    
    参数:
        obj: 要装饰的函数或类
    
    返回:
        装饰后的函数或类
    
    示例:
        >>> @once
        ... def initialize():
        ...     print("Initializing...")
        ...     return 42
        
        >>> initialize()  # 输出: Initializing...
        42
        >>> initialize()  # 不输出
        42
        >>> initialize(force=True)  # 强制重新执行
        Initializing...
        42
        
        >>> @once
        ... class Singleton:
        ...     def __init__(self, value):
        ...         self.value = value
        
        >>> s1 = Singleton(1)
        >>> s2 = Singleton(2)
        >>> assert s1 is s2  # 同一个实例
    """
    if isclass(obj):
        class Singleton(obj):
            _instance = None
            
            def __new__(cls, *args, **kwargs):
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                return cls._instance
            

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
            def __init__(self, *args, **kwargs):
                if not self._initialized:
                    super().__init__(*args, **kwargs)
                    self._initialized = True
        
        Singleton.__name__ = obj.__name__
        Singleton.__qualname__ = obj.__qualname__
        Singleton.__doc__ = obj.__doc__
        Singleton.__module__ = obj.__module__
        return Singleton
    
    return _OnceWrapper(obj)


def _default_force_when_by_day(result: Any, start: float, end: float) -> bool:
    """
    应用于 persist 装饰器的目标函数，force_when 参数
    该函数 实现 同一天内只跑一次的效果
    """
    import datetime
    f = lambda x: datetime.datetime.fromtimestamp(x).date()
    p = f(start) == f(end) == datetime.datetime.today().date()
    return not p


_DEFAULT_FORCE_WHEN = config.other['default_force_when']
_DEFAULT_TARGET_FOLDER = config.other['default_target_folder']


def persist(func: Callable) -> Callable:
    """
    装饰器：将函数的执行结果缓存到本地文件，并提供灵活的刷新控制。

    被装饰的函数会自动获得以下关键字参数：
        file_key: str = None      缓存文件名（不含扩展名），默认使用函数名
        force: bool = False       是否强制重新执行
        force_when: Optional[Callable[[Any,float, float], bool]] = None
                                  当 force=False 时，若此函数返回 True 则强制刷新。
                                  该函数接收三个参数：缓存结果、上次执行的开始时间戳、结束时间戳。
        target_folder: str = None  缓存文件所在目录，默认与被装饰函数所在文件同级的 __persist__ 目录


    要求：
        - 函数返回值必须可 JSON 序列化（基本类型、列表、字典、None）。
        - 缓存文件保存为 JSON 格式，包含 result、start_time、end_time。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        file_key = kwargs.pop('file_key', None)
        force = kwargs.pop('force', False)
        force_when = kwargs.pop('force_when', _DEFAULT_FORCE_WHEN)
        target_folder = kwargs.pop('target_folder', _DEFAULT_TARGET_FOLDER)

        if file_key is None:
            file_key = func.__name__
        else:
            file_key = sanitize_file_key(file_key)

        if target_folder:
            cache_dir = target_folder
        else:
            func_file = getfile(func)
            cache_dir = os.path.join(os.path.dirname(func_file), "__persist__")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{file_key}.json")

        cache_data = None
        need_refresh = force
        
        if not need_refresh and os.path.exists(cache_path):
            with FileLock(cache_path):
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                
                    result = cache_data.get('result')
                    start_time = cache_data.get('start_time')
                    end_time = cache_data.get('end_time')
                    
                    if force_when is not None and start_time is not None and end_time is not None:
                        if force_when(result, start_time, end_time):
                            need_refresh = True
                except Exception:
                    need_refresh = True
                    cache_data = None

        if not need_refresh and cache_data is not None:
            return cache_data['result']
        
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()

        try:
            json.dumps(result)
        except (TypeError, ValueError) as e:
            raise TypeError(
                f"Function '{func.__name__}' returned a non-JSON-serializable object. "
                f"Please ensure the return value is a basic JSON type. Error: {e}"
            )

        with FileLock(cache_path):
            cache_data = {
                'result': result,
                'start_time': start_time,
                'end_time': end_time,
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

        return result

    return wrapper


if __name__ == '__main__':
    print("=== 测试 memorize ===")
    
    @memorize
    def test_func1():
        return time.time()
    
    for i in range(5):
        print(f"调用 {i}: {test_func1()}")
        time.sleep(0.5)
    
    @memorize(duration=2)
    def test_func2():
        return time.time()
    
    print("\n测试 duration 参数:")
    for i in range(5):
        print(f"调用 {i}: {test_func2()}")
        time.sleep(0.5)
    
    print("\n=== 测试 once ===")
    
    @once
    def test_once_func():
        print("执行函数")
        return time.time()
    
    print(f"第一次: {test_once_func()}")
    print(f"第二次: {test_once_func()}")
    print(f"强制执行: {test_once_func(force=True)}")
    
    @once
    class TestSingleton:
        def __init__(self, value):
            self.value = value
            print(f"初始化: {value}")
    
    s1 = TestSingleton(1)
    s2 = TestSingleton(2)
    print(f"s1.value: {s1.value}, s2.value: {s2.value}")
    print(f"s1 is s2: {s1 is s2}")
    
    print("\n=== 测试 persist ===")

    @persist
    def fetch_weather(city: str, api_key: str = "default"):
        import random
        print(f"[执行] 正在获取 {city} 的天气...")
        time.sleep(1)
        return random.randint(20, 30)

    temp = fetch_weather("Beijing", file_key="weather_beijing")
    print(temp)

    temp = fetch_weather("Beijing", file_key="weather_beijing")
    print(temp)

    temp = fetch_weather("Beijing", file_key="weather_beijing", force=True)
    print(temp)

    for i in range(20):
        temp = fetch_weather(
            "Beijing",
            file_key="weather_beijing",
            force_when=lambda result,start, end: time.time() - end > 5 or result > 27
        )
        print(temp)
        time.sleep(1)
    
    print("\n=== 测试 persist 指定缓存目录 ===")
    
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    print(f"临时缓存目录: {temp_dir}")
    
    @persist
    def fetch_data(city: str):
        import random
        print(f"[执行] 正在获取 {city} 的数据...")
        time.sleep(0.5)
        return random.randint(100, 200)
    
    data = fetch_data("Shanghai", file_key="data_shanghai", target_folder=temp_dir)
    print(data)
    
    expected_cache_path = os.path.join(temp_dir, "data_shanghai.json")
    if os.path.exists(expected_cache_path):
        print(f"✓ 缓存文件已正确保存到指定目录: {expected_cache_path}")
    else:
        print(f"✗ 缓存文件未保存到指定目录")
    
    data = fetch_data("Shanghai", file_key="data_shanghai", target_folder=temp_dir)
    print(data)
    
    shutil.rmtree(temp_dir)
    print(f"✓ 临时目录已清理: {temp_dir}")

    print("\n所有测试通过!")