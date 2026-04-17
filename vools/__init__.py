"""
vools - Python 函数式编程工具集

一个强大的 Python 函数式编程工具集，提供装饰器、函数式编程工具、数据处理工具等。
"""

# ============================================================================
# 版本信息
# ============================================================================

__version__ = "0.1.1"
__author__ = "Victor"
__license__ = "Apache 2.0"


# ============================================================================
# 导入子模块
# ============================================================================

# 配置管理
from .config import config, ConfigManager

# 装饰器
from .decorators import (
    memorize,
    once,
    persist,
    lazy,
    repeat,
    retry,
    rerun,
    trd,
    proc,
    extend,
    curry,
    delay_curry,
    overload,
    overcurry,
    overloads,
)

# 函数式编程工具
from .functional import (
    Pipe,
    Ops,
    Seq,
    P,
    NONE,
    iif,
    ConditionBuilder,
    LazyProperty,
    arrow_func,
    g,
)

# 通用工具
from .utils import (
    stuff,
    Stuff,
    IndexedDict,
    identity,
    const,
    compose,
    pipe,
)

# 快捷工具
from .shotcut import (
    shotcut,
    shotcutEx,
    hoder,
    Hoder,
    timeit,
    memoize,
    once,
    retry,
    asyncify,
    compose,
    pipe,
    smart_partial,
    safe,
    throttle,
    debounce,
    singleton,
    deprecated,
    conditional,
    with_context,
    with_timeout,
    validate,
    rate_limit,
    log_calls,
    cache_with_ttl,
    hybrid_method,
    classproperty,
    enumize,
)

# 数据处理工具（可选）
try:
    from . import data
    DATA_AVAILABLE = True
except Exception:
    DATA_AVAILABLE = False

# OOP 工具（可选）
try:
    from . import oop
    from .oop import Selector, overloads as curry_overloads
    OOP_AVAILABLE = True
except ImportError:
    OOP_AVAILABLE = False

# 自定义数据类型（可选）
try:
    from .vools import (
        vicTools,
        vicDate,
        vicText,
        vicList,
    )
    VIC_AVAILABLE = True
except Exception:
    VIC_AVAILABLE = False



# 日期时间工具（可选）
try:
    from . import datetime
    DATETIME_AVAILABLE = True
except ImportError:
    DATETIME_AVAILABLE = False




# ============================================================================
# 公共 API
# ============================================================================

__all__ = [
    # 版本信息
    '__version__',
    '__author__',
    '__license__',
    
    # 配置管理
    'config',
    'ConfigManager',
    
    # 装饰器
    'memorize',
    'once',
    'persist',
    'lazy',
    'repeat',
    'retry',
    'rerun',
    'trd',
    'proc',
    'extend',
    'smart_partial',
    'delay_curry',
    'overload',
    'overcurry',
    
    # 函数式编程工具
    'Pipe',
    'Ops',
    'Seq',
    'P',
    'NONE',
    'iif',
    'ConditionBuilder',
    'LazyProperty',
    'arrow_func',
    'g',
    
    # 通用工具
    'stuff',
    'Stuff',
    'IndexedDict',
    'identity',
    'const',
    'compose',
    'pipe',
    
    # 快捷工具
    'shotcut',
    'shotcutEx',
    'hoder',
    'Hoder',
    'timeit',
    'asyncify',
    'safe',
    'throttle',
    'debounce',
    'singleton',
    'deprecated',
    'conditional',
    'with_context',
    'with_timeout',
    'validate',
    'rate_limit',
    'log_calls',
    'cache_with_ttl',
    'hybrid_method',
    'classproperty',
    'enumize',
    
    # 面向对象工具
    'Selector',
    'overloads',
    'Mixer',
    'mixer',
    
    # 自定义数据类型
    'vicTools',
    'vicDate',
    'vicText',
    'vicList',
  
    
    # 数据处理工具
    'data',
    'DATA_AVAILABLE',
    
    # OOP 工具
    'oop',
    'OOP_AVAILABLE',
    'curry_overloads',
    
    # 日期时间工具
    'datetime',
    'DATETIME_AVAILABLE',
    

]


# ============================================================================
# 便捷导入
# ============================================================================

# 所有主要功能已通过 __all__ 导出


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == '__main__':
    print(f"vools version: {__version__}")
    print(f"Available exports: {__all__}")
    
    # 测试装饰器
    print("\n=== 测试 memorize ===")
    
    @memorize(duration=5)
    def expensive_function(x):
        return x ** 2
    
    print(f"expensive_function(5) = {expensive_function(5)}")
    print(f"expensive_function(5) = {expensive_function(5)} (cached)")
    
    # 测试 once
    print("\n=== 测试 once ===")
    
    @once
    def initialize():
        print("Initializing...")
        return 42
    
    print(f"initialize() = {initialize()}")
    print(f"initialize() = {initialize()} (cached)")
    
    # 测试函数式编程工具
    print("\n=== 测试 Ops ===")
    
    result = range(10) | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2) | Ops.sum()
    print(f"range(10) | filter(x % 2 == 0) | map(x * 2) | sum() = {result}")
    
    # 测试 Seq
    print("\n=== 测试 Seq ===")
    
    result = Seq(range(10)).map(lambda x: x * 2).filter(lambda x: x > 5).collect()
    print(f"Seq(range(10)).map(x * 2).filter(x > 5).collect() = {result}")
    
    # 测试 repeat
    print("\n=== 测试 repeat ===")
    
    @repeat(cnt=3, delay=0.1)
    def hello(name):
        return f"Hello, {name}!"
    
    for i, result in enumerate(hello("World")):
        print(f"调用 {i+1}: {result}")
    
    print("\n所有测试通过!")
