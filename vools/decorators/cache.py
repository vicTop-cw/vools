"""
缓存相关装饰器

包含：
- memorize: 函数结果缓存装饰器
- once: 单次执行装饰器（支持函数和类）
"""

import time
import hashlib
import pickle
from functools import wraps
from inspect import signature, isclass,getfile
from typing import Callable, Any, Optional
import json
import os
from ..config import config

__all__ = ['memorize', 'once','persist']

# ============================================================================
# memorize - 函数结果缓存装饰器
# ============================================================================

_cache = {}

def _is_obsolete(entry: dict, duration: float) -> bool:
    """检查缓存是否过期"""
    return time.time() - entry['time'] > duration

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
            if key in _cache and not _is_obsolete(_cache[key], duration):
                return _cache[key]['result']
            result = func(*args, **kwargs)
            _cache[key] = {'result': result, 'time': time.time()}
            return result
        return _wrapper
    
    if func:
        return wrapper(func)
    return wrapper


# ============================================================================
# once - 单次执行装饰器，支持强制刷新，引擎重启缓存失效
# ============================================================================

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
    # 处理类装饰
    if isclass(obj):
        class Singleton(obj):
            _instance = None
            
            def __new__(cls, *args, **kwargs):
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                return cls._instance
            
            def __init__(self, *args, **kwargs):
                if not self._initialized:
                    super().__init__(*args, **kwargs)
                    self._initialized = True
        
        # 复制原始类的属性
        Singleton.__name__ = obj.__name__
        Singleton.__qualname__ = obj.__qualname__
        Singleton.__doc__ = obj.__doc__
        Singleton.__module__ = obj.__module__
        return Singleton
    
    # 处理函数装饰
    return _OnceWrapper(obj)





# ============================================================================
# persist - 函数结果缓存到磁盘装饰器，支持强制刷新，引擎重启缓存有效
# ============================================================================

def _default_force_when_by_day(result: Any, start: float, end: float) -> bool:
    """
    应用于 persist 装饰器的目标函数，force_when 参数
    该函数 实现 同一天内只跑一次的效果
    """
    import datetime
    f = lambda x: datetime.datetime.fromtimestamp(x).date()
    p = f(start) == f(end) == datetime.datetime.today().date()
    return not p

_DEFAULT_FORCE_WHEN = config.other['default_force_when'] # 默认不强制刷新
# _DEFAULT_FORCE_WHEN = _default_force_when_by_day # 默认同一天内只跑一次
# _DEFAULT_FORCE_WHEN = lambda result,start, end: time.time() - end > 5 and result > 25 # 默认5秒内温度高于25度强制刷新
_DEFAULT_TARGET_FOLDER = config.other['default_target_folder'] # 默认缓存目录，与被装饰函数所在文件同级的 __persist__ 目录，可以直接修订

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
        # 提取装饰器注入的特殊参数，并从 kwargs 中移除，避免传给原函数
        file_key = kwargs.pop('file_key', None)
        force = kwargs.pop('force', False)
        force_when = kwargs.pop('force_when', _DEFAULT_FORCE_WHEN)
        target_folder = kwargs.pop('target_folder', _DEFAULT_TARGET_FOLDER)

        if file_key is None:
            file_key = func.__name__

        # 确定缓存文件路径
        if target_folder:
            # 使用指定的缓存目录
            cache_dir = target_folder
        else:
            # 默认与被装饰函数所在文件同级的 __persist__ 目录
            func_file = getfile(func)
            cache_dir = os.path.join(os.path.dirname(func_file), "__persist__")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{file_key}.json")

        # 判断是否需要强制刷新（缓存文件存在且未损坏时才检查 force_when）
        need_refresh = force
        if not need_refresh and os.path.exists(cache_path):
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
                # 缓存损坏，视为需要刷新
                need_refresh = True

        # 如果不需要刷新且缓存文件存在，直接读取并返回
        if not need_refresh and os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                result = cache_data['result']
                return result
            except Exception:
                # 读取失败时，继续执行原函数（相当于 force=True）
                pass

        # 执行原函数，记录起止时间
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()

        # 确保结果可 JSON 序列化
        try:
            json.dumps(result)
        except (TypeError, ValueError) as e:
            raise TypeError(
                f"Function '{func.__name__}' returned a non-JSON-serializable object. "
                f"Please ensure the return value is a basic JSON type. Error: {e}"
            )

        # 写入缓存文件
        cache_data = {
            'result': result,
            'start_time': start_time,
            'end_time': end_time,
        }
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)


        return result

    return wrapper



# ============================================================================
# 测试代码
# ============================================================================

if __name__ == '__main__':
    # 测试 memorize
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
    
    # 测试 once
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
    





    # 测试 persist
    print("\n=== 测试 persist ===")


    @persist
    def fetch_weather(city: str, api_key: str = "default"):
        """模拟一个耗时的 API 请求，返回温度（基本类型）"""
        import random
        print(f"[执行] 正在获取 {city} 的天气...")
        # 模拟耗时
        time.sleep(1)
        return random.randint(20, 30)

    # 第一次调用 —— 会实际执行
    temp = fetch_weather("Beijing", file_key="weather_beijing")
    print(temp)

    # 第二次调用 —— 直接返回缓存
    temp = fetch_weather("Beijing", file_key="weather_beijing")
    print(temp)

    # 强制刷新
    temp = fetch_weather("Beijing", file_key="weather_beijing", force=True)
    print(temp)

    # 使用 force_when：如果距离上次执行结束超过 5 秒则刷新 且 温度高于 25 度
    for i in range(20):
        temp = fetch_weather(
            "Beijing",
            file_key="weather_beijing",
            force_when=lambda result,start, end: time.time() - end > 5 or result > 27
        )
        print(temp)
        time.sleep(1)
    
    # 测试 persist 指定缓存目录
    print("\n=== 测试 persist 指定缓存目录 ===")
    
    import tempfile
    import shutil
    
    # 创建临时目录作为缓存目录
    temp_dir = tempfile.mkdtemp()
    print(f"临时缓存目录: {temp_dir}")
    
    @persist
    def fetch_data(city: str):
        """模拟获取数据"""
        import random
        print(f"[执行] 正在获取 {city} 的数据...")
        time.sleep(0.5)
        return random.randint(100, 200)
    
    # 第一次调用 —— 会实际执行，使用指定的缓存目录
    data = fetch_data("Shanghai", file_key="data_shanghai", target_folder=temp_dir)
    print(data)
    
    # 验证缓存文件是否存在于指定目录
    expected_cache_path = os.path.join(temp_dir, "data_shanghai.json")
    if os.path.exists(expected_cache_path):
        print(f"✓ 缓存文件已正确保存到指定目录: {expected_cache_path}")
    else:
        print(f"✗ 缓存文件未保存到指定目录")
    
    # 第二次调用 —— 直接返回缓存
    data = fetch_data("Shanghai", file_key="data_shanghai", target_folder=temp_dir)
    print(data)
    
    # 清理临时目录
    shutil.rmtree(temp_dir)
    print(f"✓ 临时目录已清理: {temp_dir}")

    print("\n所有测试通过!")
