"""
vools - Python 函数式编程工具集

一个强大的 Python 函数式编程工具集，提供装饰器、函数式编程工具、数据处理工具等。"""

import importlib
import os
import pkgutil

# ============================================================================
# 版本信息
# ============================================================================

__version__ = "0.1.4"
__author__ = "Victor"
__license__ = "Apache 2.0"

# ============================================================================
# 导入子模块
# ============================================================================

# 配置管理
from .config import config, ConfigManager

# 定义子包优先级（优先级高的会覆盖优先级低的）
SUBPACKAGE_PRIORITIES = [
    'vools',
    'functional',
    'decorators',
    'utils',
    'oop',
    'data',
    'datetime',  # 最低优先级
]

# 存储导入的对象
_imported_objects = {}

# 从文件导入对象
def _import_from_file(file_name):
    """从单个文件导入对象"""
    try:
        # 导入文件模块
        module = importlib.import_module(f'.{file_name}', package='vools')
        
        # 获取模块的所有公共对象
        all_objects = [name for name in dir(module) if not name.startswith('_')]
        
        # 导入对象
        for obj_name in all_objects:
            if hasattr(module, obj_name):
                obj = getattr(module, obj_name)
                _imported_objects[obj_name] = {
                    'object': obj,
                    'package': file_name
                }
    except Exception:
        pass

# 获取所有子包
def _get_subpackages():
    """获取所有子包"""
    subpackages = []
    package_path = os.path.dirname(__file__)
    for _, name, is_pkg in pkgutil.iter_modules([package_path]):
        if is_pkg and name not in ['__pycache__']:
            subpackages.append(name)
    return subpackages

# 从子包导入对象
def _import_from_subpackage(subpackage_name):
    """从子包导入对象"""
    try:
        # 导入子包
        subpackage = importlib.import_module(f'.{subpackage_name}', package='vools')

        # 获取子包的 __all__ 列表
        if hasattr(subpackage, '__all__'):
            all_objects = subpackage.__all__
        else:
            # 如果没有 __all__，则导入所有非下划线开头的对象
            all_objects = [name for name in dir(subpackage) if not name.startswith('_')]

        # 导入对象
        for obj_name in all_objects:
            if hasattr(subpackage, obj_name):
                obj = getattr(subpackage, obj_name)

                # 检查是否已有同名对象
                if obj_name in _imported_objects:
                    # 优先级检查，保持高优先级的对象
                    existing_priority = SUBPACKAGE_PRIORITIES.index(_imported_objects[obj_name]['package']) if _imported_objects[obj_name]['package'] in SUBPACKAGE_PRIORITIES else len(SUBPACKAGE_PRIORITIES)
                    current_priority = SUBPACKAGE_PRIORITIES.index(subpackage_name) if subpackage_name in SUBPACKAGE_PRIORITIES else len(SUBPACKAGE_PRIORITIES)
                    
                    if current_priority < existing_priority:
                        # 当前包优先级更高，覆盖现有对象
                        _imported_objects[obj_name] = {
                            'object': obj,
                            'package': subpackage_name
                        }
                else:
                    # 新对象，直接导入
                    _imported_objects[obj_name] = {
                        'object': obj,
                        'package': subpackage_name
                    }
    except Exception:
        # 静默处理导入错误，避免干扰用户
        pass

# 先导入 shotcut.py 文件（最高优先级）
_import_from_file('shotcut')

# 导入所有子包
subpackages = _get_subpackages()
for subpackage in SUBPACKAGE_PRIORITIES:
    if subpackage in subpackages:
        _import_from_subpackage(subpackage)

# 将导入的对象添加到模块命名空间
for obj_name, info in _imported_objects.items():
    globals()[obj_name] = info['object']

# 特殊处理：导入 config 和 ConfigManager
globals()['config'] = config
globals()['ConfigManager'] = ConfigManager

# 特殊处理：导入 curry_overloads
try:
    from .oop import overloads as curry_overloads
    globals()['curry_overloads'] = curry_overloads
except ImportError:
    pass

# 可选导入
# 数据处理工具
try:
    from . import data
    DATA_AVAILABLE = True
    globals()['data'] = data
except Exception:
    DATA_AVAILABLE = False

# OOP 工具
try:
    from . import oop
    OOP_AVAILABLE = True
    globals()['oop'] = oop
except ImportError:
    OOP_AVAILABLE = False

# 自定义数据类型
try:
    from .vools import (
        vicTools,
        vicDate,
        vicText,
        vicList,
    )
    VIC_AVAILABLE = True
    globals()['vicTools'] = vicTools
    globals()['vicDate'] = vicDate
    globals()['vicText'] = vicText
    globals()['vicList'] = vicList
except Exception:
    VIC_AVAILABLE = False

# 日期时间工具
try:
    from . import datetime
    DATETIME_AVAILABLE = True
    globals()['datetime'] = datetime
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
    'overloads',

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
    '_',
    '_1',
    '_2',
    '_3',

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

# 确保 __all__ 中的所有名称都在模块命名空间中
for name in __all__:
    if name not in globals() and not name.startswith('__'):
        globals()[name] = None

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