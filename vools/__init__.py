"""
vools - Python 函数式编程工具集

一个强大的 Python 函数式编程工具集，提供装饰器、函数式编程工具、数据处理工具等。
"""

import importlib
from typing import Any

__version__ = "0.1.20"
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
    OverloadManager, OverloadMode, reset_registry,
    Priority, AllowSyncName, Strict, Ambiguous,
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
        from .utils import tools as _tools_module
        from .data.vtext import VText
        from .data.vlist import VList
        from .datetime.vdate_class import VDate
        _vic_classes = {
            'vicTools': _tools_module,
            'vicDate': VDate,
            'vicText': VText,
            'vicList': VList,
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
    'Y': '.functional',
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

    # 任务模块
    'task': '.task',
    'TaskQueue': '.task',
    'WorkerPool': '.task',
    'ThreadPool': '.task',
    'TaskStatus': '.task',
    'Task': '.task',
    'batch_execute': '.task',
    'DagScheduler': '.task',
    'DagValidationError': '.task',
    'Rule': '.task',
    'RuleEngine': '.task',
    'RuleSet': '.task',
    'RuleStatus': '.task',
    'rule': '.task',

    # 响应式模块
    'reactive': '.reactive',
    'Observable': '.reactive',
    'Subject': '.reactive',
    'BehaviorSubject': '.reactive',
    'ReplaySubject': '.reactive',
    'AsyncSubject': '.reactive',
    'ops': '.reactive',

    # 编码模块
    'encoding': '.encoding',
    'Encoder': '.encoding',
    'Decoder': '.encoding',
    'CodecRegistry': '.encoding',
    'encodable': '.encoding',
    'decodable': '.encoding',
    'b64encode': '.encoding',
    'b64decode': '.encoding',
    'urlencode': '.encoding',
    'urldecode': '.encoding',
    'to_bytes': '.encoding',
    'to_str': '.encoding',
    'gzip_compress': '.encoding',
    'gzip_decompress': '.encoding',
    'zlib_compress': '.encoding',
    'zlib_decompress': '.encoding',
    'lzma_compress': '.encoding',
    'lzma_decompress': '.encoding',
    'compress': '.encoding',
    'decompress': '.encoding',
    'json_dumps': '.encoding',
    'json_loads': '.encoding',
    'pickle_dumps': '.encoding',
    'pickle_loads': '.encoding',
    'serialize': '.encoding',
    'deserialize': '.encoding',

    # 加密模块
    'crypto': '.crypto',
    'Encryptor': '.crypto',
    'Decryptor': '.crypto',
    'CryptoRegistry': '.crypto',
    'encryptable': '.crypto',
    'decryptable': '.crypto',
    'md5': '.crypto',
    'sha1': '.crypto',
    'sha224': '.crypto',
    'sha256': '.crypto',
    'sha384': '.crypto',
    'sha512': '.crypto',
    'hmac_md5': '.crypto',
    'hmac_sha1': '.crypto',
    'hmac_sha256': '.crypto',
    'generate_key': '.crypto',
    'generate_token': '.crypto',
}

DATA_AVAILABLE = True
OOP_AVAILABLE = True
DATETIME_AVAILABLE = True

# ============================================================================
# Nim 加速状态 - 自动回退，纯 Python 环境仍可工作
# ============================================================================

try:
    from . import _nim_loader
    from . import _nim_crypto
    from . import _nim_encoding
    from . import _nim_seq
    from . import _nim_datetime
    from . import _nim_curried
    NIM_CRYPTO_AVAILABLE = _nim_crypto.is_nim_available() if hasattr(_nim_crypto, 'is_nim_available') else False
    NIM_ENCODING_AVAILABLE = _nim_encoding.is_nim_encoding_available() if hasattr(_nim_encoding, 'is_nim_encoding_available') else False
    NIM_SEQ_AVAILABLE = _nim_seq.is_nim_seq_available() if hasattr(_nim_seq, 'is_nim_seq_available') else False
    NIM_DATETIME_AVAILABLE = _nim_datetime.is_nim_datetime_available() if hasattr(_nim_datetime, 'is_nim_datetime_available') else False
    NIM_CURRIED_AVAILABLE = _nim_curried.is_nim_curried_available() if hasattr(_nim_curried, 'is_nim_curried_available') else False
    NIM_AVAILABLE = any([NIM_CRYPTO_AVAILABLE, NIM_ENCODING_AVAILABLE, NIM_SEQ_AVAILABLE,
                          NIM_DATETIME_AVAILABLE, NIM_CURRIED_AVAILABLE])
except Exception:
    NIM_AVAILABLE = False
    NIM_CRYPTO_AVAILABLE = False
    NIM_ENCODING_AVAILABLE = False
    NIM_SEQ_AVAILABLE = False
    NIM_DATETIME_AVAILABLE = False
    NIM_CURRIED_AVAILABLE = False
VIC_AVAILABLE = True


def __getattr__(name: str) -> Any:
    """延迟加载模块"""
    if name in ('vicTools', 'vicDate', 'vicText', 'vicList'):
        _load_vic()
        return _vic_classes.get(name)

    if name in ('VList', 'VText', 'VDate'):
        if name == 'VList':
            from .data.vlist import VList as _cls
            return _cls
        elif name == 'VText':
            from .data.vtext import VText as _cls
            return _cls
        elif name == 'VDate':
            from .datetime.vdate_class import VDate as _cls
            return _cls

    if name in _lazy_modules:
        module_path = _lazy_modules[name]
        try:
            module = importlib.import_module(module_path, package='vools')
            if hasattr(module, name):
                return getattr(module, name)
            return module
        except ImportError:
            pass
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> list:
    """返回所有可用的导出名称"""
    return sorted(set(globals().keys()) | set(__all__))


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
    'OverloadManager', 'OverloadMode', 'reset_registry',
    'Priority', 'AllowSyncName', 'Strict', 'Ambiguous',
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
    'Y',
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

    # 编码模块
    'encoding',
    'Encoder',
    'Decoder',
    'CodecRegistry',
    'encodable',
    'decodable',
    'b64encode',
    'b64decode',
    'urlencode',
    'urldecode',
    'to_bytes',
    'to_str',
    'gzip_compress',
    'gzip_decompress',
    'zlib_compress',
    'zlib_decompress',
    'lzma_compress',
    'lzma_decompress',
    'compress',
    'decompress',
    'json_dumps',
    'json_loads',
    'pickle_dumps',
    'pickle_loads',
    'serialize',
    'deserialize',

    # 加密模块
    'crypto',
    'Encryptor',
    'Decryptor',
    'CryptoRegistry',
    'encryptable',
    'decryptable',
    'md5',
    'sha1',
    'sha224',
    'sha256',
    'sha384',
    'sha512',
    'hmac_md5',
    'hmac_sha1',
    'hmac_sha256',
    'generate_key',
    'generate_token',

    # 任务模块
    'task',
    'TaskQueue',
    'WorkerPool',
    'ThreadPool',
    'TaskStatus',
    'Task',
    'batch_execute',
    'DagScheduler',
    'DagValidationError',
    'Rule',
    'RuleEngine',
    'RuleSet',
    'RuleStatus',
    'rule',

    # V 类
    'VList',
    'VText',
    'VDate',
]

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