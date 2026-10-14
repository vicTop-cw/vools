"""
vools - Python 函数式编程工具集

一个强大的 Python 函数式编程工具集，提供装饰器、函数式编程工具、数据处理工具等。
"""

import pkgutil
import os
import sys
import types

# 允许 vools-rx / vools-bridges 等子包作为同一 vools 命名空间下的独立分发包被合并
__path__ = pkgutil.extend_path(__path__, __name__)

# ============================================================================
# vools.concurrent 兼容别名（防 shadow 标准库 concurrent）
# ============================================================================
# 物理目录 `vools/concurrent` 已改名 `vools/vconcurrent`：因为只要 vools 根出现在
# sys.path 的前面，`import concurrent.futures` 就会命中 vools/concurrent/futures.py
# 而不是标准库，导致 `from concurrent.futures import ThreadPoolExecutor` 直接崩
# （vools/decorators/trd.py 首当其冲）。
# 这里在 sys.modules 注册一个代理模块，其 __path__ 指向 vconcurrent 目录：
#   - `from vools.concurrent.futures import VThreadPoolExecutor`（旧用法）继续可用
#   - `import vools.concurrent.futures`（旧用法）继续可用
#   - 顶层 `import concurrent.futures` 不再被 shadow（标准库正常）
_vools_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_vconcurrent_dir = os.path.join(_vools_pkg_dir, "vconcurrent")
if not sys.modules.get("vools.concurrent") and os.path.isdir(_vconcurrent_dir):
    _conc_proxy = types.ModuleType("vools.concurrent")
    _conc_proxy.__path__ = [_vconcurrent_dir]
    sys.modules["vools.concurrent"] = _conc_proxy

import subprocess

# ============================================================================
# 全局 subprocess 编码兼容：Windows 下子进程输出可能包含非 UTF-8 字节
# 对 text=True/universal_newlines=True 的 Popen 调用默认使用 errors='replace'
# 注意：该修补需要幂等，因为 tests/bridge/test_imports.py 会 reload(vools)
# ============================================================================

if not hasattr(subprocess.Popen.__init__, '_vools_patched'):
    _original_popen_init = subprocess.Popen.__init__

    def _popen_init(self, *args, **kwargs):
        # Python 3.6 的 Popen 没有 text 参数（3.7+ 才加入 text 作为
        # universal_newlines 的别名）。subprocess.run 会把 text 原样透传给
        # Popen，导致 py3.6 下任何 subprocess.run(..., text=True) 都抛
        # TypeError。这里统一转为 universal_newlines。
        if sys.version_info < (3, 7) and 'text' in kwargs:
            text_val = kwargs.pop('text')
            if 'universal_newlines' not in kwargs:
                kwargs['universal_newlines'] = text_val
        if kwargs.get('text') or kwargs.get('universal_newlines'):
            if 'errors' not in kwargs:
                kwargs['errors'] = 'replace'
        return _original_popen_init(self, *args, **kwargs)

    _popen_init._vools_patched = True
    subprocess.Popen.__init__ = _popen_init

import importlib
from typing import Any

__version__ = "0.7.9"
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
    curry, curry_class, rself,
    flex_pos
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
        from .data.vtext import VText
        from .data.vlist import VList
        from .datetime.vdate_class import VDate

        # vicTools 优先用 pyk.tools.vicTools（legacy vicTools 的聚合类，含
        # pyspark 方法）；pyk 缺席（未装 pyspark/pandas）时回退到纯 Python 的
        # vools.utils.tools 模块，保证核心库不依赖 pyspark。
        try:
            from .pyk.tools import vicTools as _vic_tools
        except Exception:
            from .utils import tools as _vic_tools

        _vic_classes = {
            'vicTools': _vic_tools,
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
    'hoder': '.utils',
    'Hoder': '.utils',
    'timeit': '.decorators',
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
    'cache_with_ttl': '.decorators',
    'hybrid_method': '.decorators',
    'classproperty': '.decorators',
    'enumize': '.decorators',

    'Selector': '.oop',
    'Mixer': '.oop',
    'mixer': '.oop',
    'oop': '.oop',
    'calltype': '.oop',
    'derive': '.oop',
    'create_derive': '.oop',
    'clone': '.oop',

    'md': '.md',

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
    # 字符编码文件编解码（GBK/UTF-8/UTF-16/BOM）
    'filecodec': '.encoding.filecodec',
    'detect': '.encoding.filecodec',
    'read_text': '.encoding.filecodec',
    'write_text': '.encoding.filecodec',
    'convert': '.encoding.filecodec',
    'sniff_stdio': '.encoding.filecodec',

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
BRIDGE_AVAILABLE = False
REACTIVE_AVAILABLE = False
DLL32_AVAILABLE = False
XL_AVAILABLE = False

VIC_AVAILABLE = True
PYK_AVAILABLE = False

# ============================================================================
# legacy 兼容层：vicspark / my_spark / get_content
# 旧版 vools 单文件里这三个是模块级全局 API（vicspark = 全局 SparkSession）。
# 新 vools 把 Spark 能力放在 vools.pyk / vools.sql.spark 里，此处提供等价入口，
# 让 look_upon / p3_prod 等 legacy 调用方 `from vools import vicspark, get_content`
# 继续可用，不需要改业务代码。
# ============================================================================

_vicspark = None  # type: Any


def my_spark(spk: Any = None) -> Any:
    """设置/获取全局 SparkSession（legacy vicspark 兼容）。

    Args:
        spk: 传入则把它设为全局 SparkSession；不传则返回当前全局实例。

    Returns:
        SparkSession 实例。

    Notes:
        首次调用且未显式传入时，通过 ``vools.pyk.get_spark`` 惰性创建。
    """
    global _vicspark
    if spk is not None:
        _vicspark = spk
    elif _vicspark is None:
        from .pyk import get_spark as _pyk_get_spark
        _vicspark = _pyk_get_spark(app_name="vools")
    return _vicspark


def get_content(file_path: str, to_text: bool = True):
    """读取文件内容（legacy ``vicText.get_content_fromfile`` 兼容）。

    Args:
        file_path: 文件路径，支持 file:// URI。
        to_text: True 返回 VText（legacy 有 ``.text``）；False 返回行列表。

    Returns:
        VText 或行列表。

    Notes:
        legacy 里 ``get_content = vicText.get_content_fromfile``，返回值带 ``.text``；
        新 vools 的 ``VText.get_content_fromfile`` 直接返回 str，此处补一层包装，
        让 ``get_content(path).text`` 这类旧写法继续可用。
    """
    from .data.vtext import VText
    raw = VText.get_content_fromfile(file_path=file_path, to_text=to_text)
    if to_text and not isinstance(raw, VText):
        return VText(raw)
    return raw


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

    if name == 'bridge':
        global BRIDGE_AVAILABLE
        try:
            module = importlib.import_module('.bridge', package='vools')
            BRIDGE_AVAILABLE = True
            return module
        except Exception:
            raise AttributeError("vools.bridge is not installed; use pip install 'vools[bridges]' or pip install vools-bridges")

    if name == 'reactive':
        global REACTIVE_AVAILABLE
        try:
            module = importlib.import_module('.reactive', package='vools')
            REACTIVE_AVAILABLE = True
            return module
        except Exception:
            raise AttributeError("vools.reactive is not installed; use pip install 'vools[rx]' or pip install vools-rx")

    if name == 'dll32':
        global DLL32_AVAILABLE
        try:
            module = importlib.import_module('.dll32', package='vools')
            DLL32_AVAILABLE = True
            return module
        except Exception:
            raise AttributeError("vools.dll32 is not installed; use pip install 'vools[dll32]' or pip install vools-dll32")

    if name == 'xl':
        global XL_AVAILABLE
        try:
            module = importlib.import_module('.xl', package='vools')
            XL_AVAILABLE = True
            return module
        except Exception:
            raise AttributeError("vools.xl is not installed; use pip install 'vools[xl]' or pip install vools-xl")

    if name == 'pyk':
        global PYK_AVAILABLE
        try:
            # pyk 由独立分发包 vools-pyk 提供（namespace 包 vools/pyk/），不随 vools 核心分发
            module = importlib.import_module('vools.pyk')
            PYK_AVAILABLE = True
            return module
        except Exception as _pe:
            raise AttributeError(
                "vools.pyk 需要 vools-pyk；请先 `pip install 'vools[pyk]'` 或 `pip install vools-pyk`。"
                f" 原始错误: {_pe}"
            )

    if name == 'vicspark':
        # legacy 兼容：全局 SparkSession，惰性创建
        try:
            return my_spark()
        except Exception as _e:
            raise AttributeError(
                "vools.vicspark 需要 pyspark；请先 `pip install 'vools[pyk]'` 或 `pip install vools-pyk`。"
                f" 原始错误: {_e}"
            )

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
    'hoder',
    'Hoder',
    'timeit',
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
    'derive',
    'create_derive',
    'clone',
    'md',

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

# 注意（BUG-1）：可选子包 bridge / reactive / dll32 / xl / pyk **一律不进 __all__**。
# `from vools import *` 会遍历 __all__ 逐名 getattr，而 __getattr__ 对未安装的可选子包
# 按设计抛 AttributeError —— 把可选名放进 __all__ 会让「标准安装（核心不含任何子包）」
# 下的 star import 整条崩溃。pyk 曾被加进 __all__，正是 tests/core/test_import.py 与
# tests/core/test_utils.py 两个收集错误的真因。可选子包请用显式 `vools.pyk` 访问。

# Python 3.6 兼容：模块级 __getattr__ 和 __dir__ 是 3.7+ 才有的
# 在 3.6 中需要主动导入所有延迟加载的名称
import sys as _sys
if _sys.version_info < (3, 7):
    for _name in _lazy_modules:
        if _name not in globals():
            try:
                _module_path = _lazy_modules[_name]
                _module = importlib.import_module(_module_path, package='vools')
                if hasattr(_module, _name):
                    globals()[_name] = getattr(_module, _name)
                else:
                    globals()[_name] = _module
            except Exception:
                pass
    # VList, VText, VDate
    for _vname in ('VList', 'VText', 'VDate'):
        if _vname not in globals():
            try:
                if _vname == 'VList':
                    from .data.vlist import VList as _v
                    globals()['VList'] = _v
                elif _vname == 'VText':
                    from .data.vtext import VText as _v
                    globals()['VText'] = _v
                elif _vname == 'VDate':
                    from .datetime.vdate_class import VDate as _v
                    globals()['VDate'] = _v
            except Exception:
                pass
    # vicTools, vicDate, vicText, vicList
    try:
        _load_vic()
        for _vk, _vv in _vic_classes.items():
            globals()[_vk] = _vv
    except Exception:
        pass
