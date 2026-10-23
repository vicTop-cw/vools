"""
vools.sql - SQL 方言框架

提供统一的 SQL 方言抽象与构建能力，支持多种数据库的 SQL 生成与适配。

子模块（本分发实际存在的）：
- core: 核心基础设施（类型映射、构建器抽象、连接抽象、结果集抽象、装饰器、方言基类）
- manager: SQL 方言管理器与注册表
- postgres: PostgreSQL 方言实现
- sqlite: SQLite 方言实现
- spark: Spark SQL 方言实现

（docstring 从前还列着 mysql / oracle / mssql，但本分发【没有】这三个子模块目录
 —— 2026-10-17 寻虫 BUG-77：它们也因此从 __all__ 里摘掉，见下方注释。要加方言
 请连子模块实现一起加。）
"""

from .core.types import SqlTypeMapper, PY_TO_SQL, SQL_TO_PY, infer_arg_types, infer_ret_type, convert_args, convert_result
from .core.builder import SqlBuilder, BaseSqlBuilder
from .core.connection import Connection
from .core.result import ResultSet, Row
from .core.decorators import sql_function, sql_module, sql_func_name
from .core.dialect import Dialect, register_dialect as _core_register_dialect, get_dialect as _core_get_dialect, list_dialects as _core_list_dialects, has_dialect as _core_has_dialect
from .core.config import DialectConfig

from .manager import (
    manager,
    DialectManager,
    register_dialect,
    get_dialect as _manager_get_dialect,
    create_dialect as _manager_create_dialect,
    is_available,
    list_dialects as _manager_list_dialects,
    list_available,
    get_config,
    set_config,
    save_config,
    load_config,
)

__all__ = [
    # core.types
    'SqlTypeMapper',
    'PY_TO_SQL',
    'SQL_TO_PY',
    'infer_arg_types',
    'infer_ret_type',
    'convert_args',
    'convert_result',

    # core.builder
    'SqlBuilder',
    'BaseSqlBuilder',

    # core.connection
    'Connection',

    # core.result
    'ResultSet',
    'Row',

    # core.decorators
    'sql_function',
    'sql_module',
    'sql_func_name',

    # core.dialect
    'Dialect',
    'has_dialect',

    # core.config
    'DialectConfig',

    # manager
    'manager',
    'DialectManager',
    'register_dialect',
    'get_dialect',
    'create_dialect',
    'is_available',
    'list_dialects',
    'list_available',
    'get_config',
    'set_config',
    'save_config',
    'load_config',
    'get_config_file_path',
    'clear_instance_cache',

    # 方言模块（本分发实际存在且可导入的三个）
    # 注意（2026-10-17 寻虫 BUG-77/79）：这里从前还列着 'mysql' / 'oracle' / 'mssql'
    # —— vools/sql/ 下【没有】这三个子模块目录（实测只有 core/postgres/spark/
    # sqlite），空头名让 `from vools.sql import *` 逐名 getattr 时直接失败，
    # 叠加上面的 __getattr__ 自递归后表现为【整条卡死 >120s】。
    'postgres',
    'sqlite',
    'spark',

    # 子模块
    # 'manager' 从前在这里被列了【两次】（上面的 manager 函数区 + 这里）——
    # 而且语义并不相同：上面那个 'manager' 是 `from .manager import manager`
    # 绑进来的 DialectManager【实例】（它同时也是本包属性解析到的那个 manager），
    # 这里当作"子模块"再列一遍是重复声明。去重后保留函数区那一条；子模块仍可
    # 用完整路径 importlib.import_module('vools.sql.manager') 取到。
    'core',
]

# 延迟导入方言模块，避免导入失败影响整体
#
# 为什么不能用 `from . import mysql` 这种写法（2026-10-17 寻虫 BUG-77）：
# 模块级 __getattr__ 存在时，`from . import X` 会走 importlib._bootstrap 的
# _handle_fromlist —— 它在"子模块不存在/已存在"判断里对父包做
# hasattr(parent, 'X')，而 hasattr 又触发本模块的 __getattr__，后者再次调用
# 同一个 _load_*。于是【一次 getattr 自递归上百层】（实测 entries=50~105），
# 最终只是靠 `except Exception` 吞掉 RecursionError 才"看起来能用"；
# `from vools.sql import *` 因此实测卡死 >120s（未修前）。
# importlib.import_module('.X', __name__) 不查父包属性，天然无此环；再加
# _LOADING（防重入）与 _DIALECT_FAILED（不反复撞同一失败）两个集合。
#
# 为什么用两个集合而不是六个 _XXX_LOADED 布尔位：一个布尔要同时表达"成功/失败/
# 正在试"三态必然出错 —— 本文件第一版修复就用单面 flag 记"已试过"，失败时也置
# True，结果成功加载过后再解析同名（例如别处 pop 了 globals 里的绑定）会被误判成
# "加载不了"，把 vools.sql.sqlite 这种真实存在的子模块报成 AttributeError。
# 三态分家：成功→globals()[name] 有值；失败→进 _DIALECT_FAILED；在试→进 _LOADING。
_LOADING = set()
_DIALECT_FAILED = set()


def _auto_register_dialect(name, mod):
    """BUG-347: 惰性加载方言子模块后，把其中的 Dialect 子类登记到 manager。

    原实现只 `globals()[name] = mod`，**从不注册**——于是内置方言虽然可导入，
    `vools.sql.get_dialect('sqlite')` / `create_dialect` / `has_dialect` 全部
    KeyError/False，`list_dialects()` 恒为空（除非用户手动 register_dialect）。
    """
    try:
        # 本模块 __init__ 已绑定 Dialect / manager（见文件上部 import）；
        # 导入期再次 `from .manager import` 会撞上循环导入，因此优先用全局名。
        _Dialect = globals().get('Dialect')
        _manager = globals().get('manager')
        if _Dialect is None or _manager is None:
            from .core.dialect import Dialect as _Dialect
            from .manager import manager as _manager

        try:
            _manager.get_dialect(name)       # 已注册则跳过
            return
        except KeyError:
            pass

        candidates = [
            v for v in vars(mod).values()
            if isinstance(v, type) and issubclass(v, _Dialect) and v is not _Dialect
            and getattr(v, '__module__', '').startswith(mod.__name__)
        ]
        if not candidates:
            return
        _lowered = name.replace('_', '').lower()
        _preferred = [c for c in candidates if _lowered in c.__name__.lower()]
        _manager.register(name, (_preferred or candidates)[0])
    except Exception:
        # 注册失败不影响模块可用性（用户仍可手动 register_dialect）
        return


def _load_dialect(name):
    """按名字惰性加载 vools.sql.<name> 方言子模块（幂等、防重入）。

    Returns:
        bool: 子模块可用并已绑进本模块 globals() 时 True；
              不存在 / 导入失败 / 正在加载（重入）时 False。
    """
    if globals().get(name) is not None:
        return True
    if name in _LOADING or name in _DIALECT_FAILED:
        return False                       # 重入或已知失败：绝不递归、绝不重试
    _LOADING.add(name)
    try:
        import importlib
        mod = importlib.import_module('.' + name, __name__)
        globals()[name] = mod
        _auto_register_dialect(name, mod)
        return True
    except Exception:
        _DIALECT_FAILED.add(name)          # 记一次失败，不在每次 getattr 都撞一遍
        return False
    finally:
        _LOADING.discard(name)


def _load_mysql():
    """延迟加载 MySQL 模块（本分发目前没有 mysql 子模块，见 __all__ 注释）"""
    return _load_dialect('mysql')


def _load_postgres():
    """延迟加载 PostgreSQL 模块"""
    return _load_dialect('postgres')


def _load_sqlite():
    """延迟加载 SQLite 模块"""
    return _load_dialect('sqlite')


def _load_spark():
    """延迟加载 Spark SQL 模块"""
    return _load_dialect('spark')


def _load_oracle():
    """延迟加载 Oracle 模块（本分发目前没有 oracle 子模块）"""
    return _load_dialect('oracle')


def _load_mssql():
    """延迟加载 SQL Server 模块（本分发目前没有 mssql 子模块）"""
    return _load_dialect('mssql')


def __getattr__(name):
    """延迟加载属性"""
    if name == 'mysql':
        if _load_mysql():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    if name == 'postgres':
        if _load_postgres():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    if name == 'sqlite':
        if _load_sqlite():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    if name == 'spark':
        if _load_spark():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    if name == 'oracle':
        if _load_oracle():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    if name == 'mssql':
        if _load_mssql():
            return globals().get(name)
        raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)

    # manager 额外函数
    manager_funcs = (
        'get_config_file_path',
        'clear_instance_cache',
    )
    if name in manager_funcs:
        return getattr(globals()['manager'], name)

    raise AttributeError("module 'vools.sql' has no attribute '%s'" % name)


# ============================================================================
# BUG-347: 公开方言 API 需先触发**惰性加载**
#
# 内置方言（sqlite/spark/postgres…）通过模块级 __getattr__ 惰性导入，
# 但 `get_dialect('sqlite')` / `create_dialect` / `has_dialect` / `list_dialects`
# 直接查 manager 注册表 —— 在用户从未访问 `vools.sql.sqlite` 时注册表是空的，
# 于是"方言实际可用却报未注册 / 列表恒空"。
# 这里统一先按需加载（_load_dialect 内含防重入 + 失败缓存），再委派。
# ============================================================================
_LAZY_DIALECT_NAMES = ('sqlite', 'spark', 'postgres', 'mysql', 'oracle', 'mssql')


def _ensure_dialect_loaded(name):
    """按需加载单个方言子模块（幂等；失败静默，交由后续 KeyError 曝露）。"""
    try:
        _load_dialect(name)
    except Exception:
        pass


def get_dialect(name):
    """获取方言类（自动按需加载内置方言）。"""
    _ensure_dialect_loaded(name)
    return _manager_get_dialect(name)


def create_dialect(name, **kwargs):
    """创建方言实例（自动按需加载内置方言）。"""
    _ensure_dialect_loaded(name)
    return _manager_create_dialect(name, **kwargs)


def has_dialect(name):
    """检查方言是否已注册（自动按需加载内置方言）。"""
    _ensure_dialect_loaded(name)
    return _core_has_dialect(name)


def list_dialects():
    """列出已注册方言（先按需加载全部内置方言）。"""
    for _n in _LAZY_DIALECT_NAMES:
        _ensure_dialect_loaded(_n)
    return _manager_list_dialects()


def __dir__():
    """返回所有可用的导出名称"""
    return sorted(set(globals().keys()) | set(__all__))


# Python 3.6 兼容：模块级 __getattr__ 是 PEP 562（3.7+）才生效的，3.6 下它是个
# 死函数 —— __all__ 里靠它解析的名字全部拿不到，`from vools.sql import *` 直接
# AttributeError（实测 py3.6：postgres/sqlite/spark/get_config_file_path/
# clear_instance_cache 五个名字缺失，2026-10-17 寻虫 BUG-78）。本包
# requires-python = ">=3.6"，属承诺范围内必须可用，故按同仓 vools/__init__.py、
# vools/datetime/__init__.py、vools/decorators/__init__.py 的既有做法，在 <3.7
# 分支里主动把延迟名字绑上。绑不上（子模块确实缺依赖）时保持缺席，行为与
# 3.7+ 下 __getattr__ 抛 AttributeError 一致。
import sys as _sys

if _sys.version_info < (3, 7):
    for _dialect in ('postgres', 'sqlite', 'spark', 'mysql', 'oracle', 'mssql'):
        if _dialect not in globals():
            try:
                _load_dialect(_dialect)
            except Exception:
                pass
    for _mf in ('get_config_file_path', 'clear_instance_cache'):
        if _mf not in globals():
            try:
                globals()[_mf] = getattr(globals()['manager'], _mf)
            except Exception:
                pass
