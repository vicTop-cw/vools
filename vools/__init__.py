"""
vools - Python 函数式编程工具集

一个强大的 Python 函数式编程工具集，提供装饰器、函数式编程工具、数据处理工具等。
"""

import importlib
from typing import Any

__version__ = "0.1.10"
__author__ = "Victor"
__license__ = "Apache 2.0"

# ============================================================================
# Core 模块 - 基础类、异常和配置
# ============================================================================

from .core import (
    VoolsBase,
    VoolsError,
    SafeEvalError,
    ConfigurationError,
    CacheError,
    ValidationError,
    ImportError,
    ConfigManager,
    DatabaseConfig,
    CacheConfig,
    AppConfig,
)

# ============================================================================
# 装饰器（常用）
# ============================================================================

from .decorators import (
    memorize, once, persist,
    lazy, repeat, retry, rerun,
    overload, overcurry, overloads,
    curry, curry_class, rself
)

# ============================================================================
# 函数式编程工具（常用）
# ============================================================================

from .functional import (
    _, _1, _2, _3, g, iif,
    ConditionBuilder, LazyProperty,
    Box, box, setattr_box
)

# ============================================================================
# 数据处理工具
# ============================================================================

from .data import Seq

# ============================================================================
# 日期时间工具（常用）
# ============================================================================

from .datetime import (
    vDate, get_week, get_month,
    days_gap, weeks_gap, months_gap,
    get_recently_months, get_recently_days,
    get_dates, parse_date_string,
    get_date_range, simplify_date_ranges,
)

# ============================================================================
# 通用工具（常用）
# ============================================================================

from .utils import stuff, Stuff

# ============================================================================
# 安全模块
# ============================================================================

from .security import safe_eval
from .core import SafeEvalError as _SafeEvalError

# ============================================================================
# Vic 工具类 (延迟导入避免循环依赖)
# ============================================================================

_vic_loaded = False
_vic_classes = {}


def _load_vic():
    """延迟加载 vic 类"""
    global _vic_loaded, _vic_classes
    if not _vic_loaded:
        from . import vools as _vools_module
        _vic_classes = {
            'vicTools': _vools_module.vicTools,
            'vicDate': _vools_module.vicDate,
            'vicText': _vools_module.vicText,
            'vicList': _vools_module.vicList,
        }
        _vic_loaded = True


# ============================================================================
# 延迟加载映射
# ============================================================================

_lazy_modules = {
    'trd': '.decorators',
    'proc': '.decorators',
    'extend': '.decorators',
    'smart_partial': '.decorators',
    'delay_curry': '.decorators',

    'Pipe': '.functional',
    'Ops': '.functional',
    'O': '.functional',
    'P': '.functional',
    'X': '.functional',
    'Z': '.functional.adapter_z',
    'NONE': '.functional',
    'arrow_func': '.functional',

    'stuff': '.utils',
    'Stuff': '.utils',
    'IndexedDict': '.utils',
    'identity': '.utils',
    'const': '.utils',
    'compose': '.utils',
    'pipe': '.utils',

    'shotcut': '.decorators',
    'shotcutEx': '.decorators',
    'hoder': '.utils',
    'Hoder': '.utils',
    'timeit': '.decorators',
    'asyncify': '.decorators',
    'safe': '.decorators',
    'throttle': '.decorators',
    'debounce': '.decorators',
    'singleton': '.decorators',
    'deprecated': '.decorators',
    'conditional': '.decorators',
    'with_context': '.decorators',
    'with_timeout': '.decorators',
    'validate': '.decorators',
    'rate_limit': '.decorators',
    'log_calls': '.decorators',
    'cache_with_ttl': '.decorators',
    'hybrid_method': '.decorators',
    'classproperty': '.decorators',
    'enumize': '.decorators',

    'Selector': '.oop',
    'Mixer': '.oop',
    'mixer': '.oop',
    'oop': '.oop',
    'calltype': '.oop',

    'vicTools': '.vic',
    'vicDate': '.vic',
    'vicText': '.vic',
    'vicList': '.vic',

    'datetime': '.datetime',
}

DATA_AVAILABLE = True
OOP_AVAILABLE = True
DATETIME_AVAILABLE = True
VIC_AVAILABLE = True


def __getattr__(name: str) -> Any:
    """延迟加载模块"""
    if name in ('vicTools', 'vicDate', 'vicText', 'vicList'):
        _load_vic()
        return _vic_classes.get(name)

    if name in _lazy_modules:
        module_path = _lazy_modules[name]
        try:
            module = importlib.import_module(module_path, package='vools')
            if hasattr(module, name):
                return getattr(module, name)
            for submodule_name in dir(module):
                if not submodule_name.startswith('_'):
                    try:
                        submodule = importlib.import_module(f'{module_path}.{submodule_name}', package='vools')
                        if hasattr(submodule, name):
                            return getattr(submodule, name)
                    except ImportError:
                        continue
        except ImportError:
            pass
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    '__version__',
    '__author__',
    '__license__',

    'VoolsBase',
    'VoolsError',
    'SafeEvalError',
    'ConfigurationError',
    'CacheError',
    'ValidationError',
    'ImportError',
    'ConfigManager',
    'DatabaseConfig',
    'CacheConfig',
    'AppConfig',

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
    'overloads',
    'curry',
    'curry_class',
    'rself',

    'Pipe',
    'Ops',
    'O',
    'Seq',
    'P',
    'X',
    'Z',
    'NONE',
    'iif',
    'ConditionBuilder',
    'LazyProperty',
    'arrow_func',
    'g',
    '_',
    '_1',
    '_2',
    '_3',
    'Box',
    'box',
    'setattr_box',

    'stuff',
    'Stuff',
    'IndexedDict',
    'identity',
    'const',
    'compose',
    'pipe',

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

    'Selector',
    'Mixer',
    'mixer',
    'oop',
    'calltype',
    'OOP_AVAILABLE',

    'vicTools',
    'vicDate',
    'vicText',
    'vicList',

    'vDate',
    'get_week',
    'get_month',
    'days_gap',
    'weeks_gap',
    'months_gap',
    'get_recently_months',
    'get_recently_days',
    'get_dates',
    'parse_date_string',
    'get_date_range',
    'simplify_date_ranges',

    'data',
    'DATA_AVAILABLE',

    'datetime',
    'DATETIME_AVAILABLE',

    'safe_eval',
]

_common_names = [
    'VoolsBase', 'VoolsError', 'SafeEvalError', 'ConfigurationError',
    'CacheError', 'ValidationError', 'ImportError',
    'ConfigManager', 'DatabaseConfig', 'CacheConfig', 'AppConfig',
    'config', 'ConfigManager',
    'memorize', 'once', 'persist', 'lazy', 'repeat', 'retry', 'rerun',
    'overload', 'overcurry', 'overloads',
    '_', '_1', '_2', '_3', 'g', 'iif', 'ConditionBuilder', 'LazyProperty',
    'Box', 'box', 'Seq',
    'P', 'X', 'Z', 'Ops', 'O', 'calltype',
    'safe_eval',
    'vicTools', 'vicDate', 'vicText', 'vicList',
]

for name in __all__:
    if name not in globals() and name not in _common_names and not name.startswith('__'):
        globals()[name] = None


if __name__ == '__main__':
    print(f"vools version: {__version__}")
    print(f"Available exports: {len(__all__)} items")

    @memorize(duration=5)
    def expensive_function(x):
        return x ** 2

    print(f"expensive_function(5) = {expensive_function(5)}")
    print(f"expensive_function(5) = {expensive_function(5)} (cached)")

    print("\n=== 测试 once ===")

    @once
    def initialize():
        print("Initializing...")
        return 42

    print(f"initialize() = {initialize()}")
    print(f"initialize() = {initialize()} (cached)")

    print("\n=== 测试 iif ===")

    result = iif(True, "yes", "no")
    print(f"iif(True, 'yes', 'no') = {result}")

    print("\n=== 测试 g ===")

    f = g("x, y => x + y")
    print(f"g('x, y => x + y')(3, 4) = {f(3, 4)}")

    print("\n所有测试通过!")