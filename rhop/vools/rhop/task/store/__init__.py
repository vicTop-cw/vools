"""vools.rhop.task.store - 存储后端注册表（数据库抽象的可插拔入口）

三种拓扑对应三种 ``kind``：

| kind | 拓扑 | 数据一致性来源 |
|---|---|---|
| ``sqlite-shared``（默认） | 单一共享 SQLite 文件，双方同时读写 | 同一个文件，天然一致 |
| ``sqlite-local`` | 双方各持一个本地 SQLite | TaskSync 加密 JSON 包收敛 |
| （未来）``postgres`` | 网络数据库 | 数据库自身并发控制 |

新增后端只需注册一个工厂，队列层代码零改动::

    from vools.rhop.task.store import register_store

    def build_postgres(spec, ctx):
        from .pg_store import PgTaskStore      # 你的实现，遵守 TaskStore 契约
        return PgTaskStore(spec, ctx)

    register_store("postgres", build_postgres)

工厂签名：``factory(spec: dict, ctx: dict) -> TaskStore``。``spec`` 由配置提供
（``queue.store``），``ctx`` 由 TaskConfig 组装，键为：
``name`` / ``role`` / ``base_dir`` / ``shared_root`` / ``shared``。
"""

from __future__ import absolute_import

import os
from typing import Any, Callable, Dict, List, Optional

from ..errors import StoreUnavailable
from .base import TaskStore, resolve_path_template, require_shared_root
from .sqlite_store import SqliteTaskStore, resolve_shared_db_path

#: 默认存储后端（单一共享库：双方读写同一份任务状态）
DEFAULT_STORE_KIND = "sqlite-shared"

#: kind -> factory
_REGISTRY = {}  # type: Dict[str, Callable[[dict, dict], TaskStore]]


def register_store(kind: str, factory: Optional[Callable[[dict, dict], TaskStore]] = None):
    """注册一个存储后端工厂。

    两种用法等价::

        register_store("postgres", build_postgres)

        @register_store("postgres")
        def build_postgres(spec, ctx):
            ...

    Args:
        kind:    后端标识（大小写不敏感）
        factory: 工厂函数 ``factory(spec, ctx) -> TaskStore``；省略时返回装饰器

    Returns:
        注册后的工厂（或装饰器）。
    """
    key = str(kind or "").strip().lower()
    if not key:
        raise ValueError("存储后端 kind 不能为空")

    def _do_register(func):
        if not callable(func):
            raise ValueError("存储后端工厂必须可调用")
        _REGISTRY[key] = func
        return func

    if factory is None:
        return _do_register
    return _do_register(factory)


def available_store_kinds() -> List[str]:
    """已注册的存储后端 kind 列表（报错提示用）。"""
    return sorted(_REGISTRY.keys())


def create_store(spec: Optional[dict] = None, ctx: Optional[dict] = None) -> TaskStore:
    """按 ``spec['kind']`` 构造存储后端。

    Args:
        spec: ``queue.store`` 配置 dict；缺省用默认 kind。
        ctx:  解析上下文（name/role/base_dir/shared_root/shared）。

    Raises:
        StoreUnavailable: kind 未注册，或该后端所需信息缺失（如共享库缺 shared path）。
    """
    spec = dict(spec or {})
    ctx = dict(ctx or {})
    kind = str(spec.get("kind") or DEFAULT_STORE_KIND).strip().lower()
    factory = _REGISTRY.get(kind)
    if factory is None:
        raise StoreUnavailable(
            "未知存储后端 kind=%r（可用: %s）。"
            "要在双方各自持库的模式下运行请用 sqlite-local；"
            "接入 PostgreSQL 等后端请调用 register_store() 注册工厂。" % (
                kind, ", ".join(available_store_kinds()))
        )
    try:
        store = factory(spec, ctx)
    except TypeError as exc:
        # TaskStore 是真 ABC：缺实现的子类在构造期就抛 TypeError（含缺失方法名）。
        # 这里转成可读的 StoreUnavailable，让"接了不完整后端"在配置期就暴露，
        # 而不是等运行期某个调用点 AttributeError（BUG-279 的收口）。
        raise StoreUnavailable(
            "存储后端 %r 的工厂未能构造出完整实现：%s。"
            "请确认该后端已实现 TaskStore 的全部 @abstractmethod 契约方法。" % (kind, exc))
    if not isinstance(store, TaskStore):
        raise StoreUnavailable("存储后端 %r 的工厂未返回 TaskStore 实例" % kind)
    return store


def _sqlite_common(spec: dict, ctx: dict, kind: str, path: str,
                   journal_mode: str, synchronous: str) -> SqliteTaskStore:
    """构造 SqliteTaskStore 的公共部分（补默认 PRAGMA，随后用户配置可覆盖）。"""
    merged = dict(spec or {})
    merged["kind"] = kind
    merged["path"] = path
    merged.setdefault("journal_mode", journal_mode)
    merged.setdefault("synchronous", synchronous)
    merged.setdefault("table", "tasks")
    return SqliteTaskStore(merged, ctx)


@register_store("sqlite-shared")
def _build_sqlite_shared(spec: dict, ctx: dict) -> SqliteTaskStore:
    """单一共享库：文件位于双方共同可达的文件系统介质上。

    共享盘上禁用 WAL（依赖不可靠的共享内存/文件锁），改用回滚日志 + 全同步。
    """
    path = resolve_shared_db_path(spec, ctx)
    if not str((spec or {}).get("path") or ""):
        # 默认路径依赖 shared path：显式校验，拿到"可承载数据库"的明确报错
        require_shared_root(ctx)
    return _sqlite_common(spec, ctx, "sqlite-shared", path, "DELETE", "FULL")


@register_store("sqlite-local")
def _build_sqlite_local(spec: dict, ctx: dict) -> SqliteTaskStore:
    """双方各自持库：默认落在本端 base_dir，靠 TaskSync 收敛。

    本地盘可以用 WAL（更快），同步语义由 TaskSync 的版本单调性保证。
    """
    template = str((spec or {}).get("path") or "")
    if template:
        path = resolve_path_template(template, ctx)
    else:
        base_dir = str(ctx.get("base_dir") or os.getcwd())
        role = str(ctx.get("role") or "").lower() or "node"
        path = os.path.join(base_dir, "rhop-%s.db" % role)
    return _sqlite_common(spec, ctx, "sqlite-local", path, "WAL", "NORMAL")


__all__ = [
    "DEFAULT_STORE_KIND",
    "TaskStore",
    "SqliteTaskStore",
    "create_store",
    "register_store",
    "available_store_kinds",
    "resolve_shared_db_path",
    "resolve_path_template",
    "require_shared_root",
]