"""
函数重载装饰器模块

提供基于模式标志的函数重载系统，支持：
- 优先级模式 (Priority)：按 priority 属性排序匹配，允许多个候选
- 非同名注册 (AllowSyncName)：允许函数名与原始函数不同（需配合 Priority）
- 严格类型检查 (Strict)：按参数类型注解精确匹配
- 模糊匹配 (Ambiguous)：多个候选时取第一个，而非报错
- 注册模式：export_mode 控制 register 的返回值（默认返回管理器支持链式）

示例:
    >>> @overload
    ... def add(a, b):
    ...     return a + b
    ...
    >>> @add.register          # 返回管理器，支持链式
    ... def add_int(a: int, b: int):
    ...     return a + b
    ...
    >>> add(1, 2)              # 3
    >>> add("a", "b")          # "ab"
"""

import inspect
import types
import pickle
from functools import wraps
from typing import Any, Callable, Optional, List, Tuple, Union, Dict
from enum import IntFlag

from vools.cache.sigcache import get_signature

try:
    from .curry_core import is_curried, Curried
except ImportError:
    def is_curried(func):
        return False

    class Curried:
        pass


__all__ = [
    'overload',
    'OverloadManager',
    'OverloadMode',
    'Priority', 'AllowSyncName', 'Strict', 'Ambiguous',
    'strict',
    'reset_registry',
    'ParentMode', 'ExportAsFunction', 'ExportAsManager',
]


# =============================================================================
# 模式标志定义
# =============================================================================

class OverloadMode(IntFlag):
    """重载模式标志。"""
    Priority = 1 << 0           # 优先级模式：按 priority 属性排序匹配
    AllowSyncName = 1 << 1      # 允许非同名函数注册（需配合 Priority）
    Strict = 1 << 2              # 严格类型检查
    Ambiguous = 1 << 3           # 允许多个候选匹配（取第一个，非报错）


# 简写别名
Priority = OverloadMode.Priority
AllowSyncName = OverloadMode.AllowSyncName
Strict = OverloadMode.Strict
Ambiguous = OverloadMode.Ambiguous

_DEFAULT_MODE = Priority | Strict | AllowSyncName


# =============================================================================
# 导出模式常量
# =============================================================================

ParentMode = 'parent'            # 返回新管理器（继承父级模式）
ExportAsFunction = None          # 返回原函数（不创建新管理器）
ExportAsManager = 'manager'      # 返回新管理器（等同于 ParentMode 语义）


# =============================================================================
# 注册表（便于跨作用域复用；同时用于测试隔离）
# =============================================================================

_registry: Dict[Tuple[str, str, str], 'OverloadManager'] = {}


def _get_scope_from_qualname(qualname: str) -> str:
    return qualname.rpartition('.')[0]


def reset_registry() -> None:
    """清空全局注册表（用于测试隔离）。"""
    _registry.clear()


# =============================================================================
# 模式验证
# =============================================================================

def _validate_mode(mode: 'OverloadMode') -> None:
    """验证模式组合是否合法。

    规则:
        - AllowSyncName 只能在 Priority 模式下使用
        - Strict + Ambiguous 非 Priority 不禁止（但通常配合 Priority 使用更有意义）
    """
    if not (mode & OverloadMode.Priority) and (mode & OverloadMode.AllowSyncName):
        raise ValueError("AllowSyncName 只能在 Priority 模式下使用")


# =============================================================================
# 检查函数工厂：基于参数数量 / 类型
# =============================================================================

def _create_count_check(func: Callable) -> Callable:
    """基于参数数量的检查函数（无副作用）。"""
    if is_curried(func) and hasattr(func, 'func'):
        func = func.func

    sig = get_signature(func)
    params = sig.parameters

    min_args = sum(
        1 for p in params.values()
        if p.default == p.empty
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    )
    has_var = any(
        p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for p in params.values()
    )
    max_args = float('inf') if has_var else len(params)

    def count_check(args, kwargs):
        # 仅判断调用参数数量是否在函数签名的允许范围内
        arg_count = len(args) + len(kwargs)
        return min_args <= arg_count <= max_args

    return count_check


def _create_strict_check(func: Callable) -> Callable:
    """基于类型注解的严格检查函数。"""
    if is_curried(func) and hasattr(func, 'func'):
        func = func.func

    sig = get_signature(func)
    annotations = func.__annotations__
    params = sig.parameters

    def strict_check(args, kwargs):
        try:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
        except TypeError as e:
            return False, f"参数不匹配: {e}"

        errors = []
        for name, value in bound.arguments.items():
            if name in annotations:
                expected = annotations[name]
                param = params[name]

                if param.kind == inspect.Parameter.VAR_POSITIONAL:
                    for i, item in enumerate(value):
                        if not isinstance(item, expected):
                            errors.append(
                                f"位置参数 #{i} (*{name}) 类型错误: "
                                f"期望 {getattr(expected, '__name__', str(expected))}, "
                                f"实际 {type(item).__name__}"
                            )
                elif param.kind == inspect.Parameter.VAR_KEYWORD:
                    for k, item in value.items():
                        if not isinstance(item, expected):
                            errors.append(
                                f"关键字参数 '{k}' (**{name}) 类型错误: "
                                f"期望 {getattr(expected, '__name__', str(expected))}, "
                                f"实际 {type(item).__name__}"
                            )
                else:
                    if not isinstance(value, expected):
                        errors.append(
                            f"'{name}' 类型错误: "
                            f"期望 {getattr(expected, '__name__', str(expected))}, "
                            f"实际 {type(value).__name__}"
                        )

        if errors:
            return False, " | ".join(errors)
        return True, None

    return strict_check


# =============================================================================
# OverloadManager
# =============================================================================

class OverloadManager:
    """
    重载管理器。

    负责存储注册的函数列表，并根据当前 mode 和调用参数匹配最合适的函数。

    属性:
        mode (OverloadMode): 重载模式
        overloads: [(check, func, priority, reg_index, func_name), ...]
        main_func (Callable): 主函数
        export_mode: 本管理器的默认导出模式（用于 register 未显式传入时）
        parent (Optional[OverloadManager]): 父管理器（若存在）
    """

    def __init__(self,
                 func: Optional[Callable] = None,
                 mode: OverloadMode = _DEFAULT_MODE,
                 priority: int = 0,
                 export_mode=None,
                 parent: Optional['OverloadManager'] = None) -> None:

        self.mode = mode
        self.overloads: List[Tuple[Callable, Callable, int, int, str]] = []
        self.main_func: Optional[Callable] = func
        self.export_mode = export_mode
        self.parent = parent
        self.counter = 0

        if func is not None:
            self.func_name = func.__name__
            self.module = func.__module__
            self.qualname = func.__qualname__
            self.scope = _get_scope_from_qualname(self.qualname)
            self._key = (self.module, self.scope, self.func_name)

            # 验证模式组合
            _validate_mode(self.mode)

            # 注册主函数到自身重载列表
            self._register_function(func, priority=priority)

            # 写入注册表（仅主管理器；子管理器不注册）
            if parent is None:
                _registry[self._key] = self

    # ------------------------------------------------------------------
    # 注册逻辑
    # ------------------------------------------------------------------

    def _get_check_func(self, func: Callable) -> Callable:
        if self.mode & OverloadMode.Strict:
            return _create_strict_check(func)
        return _create_count_check(func)

    def _register_function(self,
                           func: Callable,
                           priority: Optional[int] = None) -> None:
        """内部注册：检查 + 加入重载列表。"""
        # Priority + AllowSyncName 检查
        if self.mode & OverloadMode.Priority:
            if (func.__name__ != self.func_name
                    and not (self.mode & OverloadMode.AllowSyncName)):
                raise ValueError(
                    f"非同名函数 '{func.__name__}' 不能注册到 '{self.func_name}' "
                    f"（需要 AllowSyncName 模式）"
                )
        else:
            # 非 Priority 模式必须同名
            if func.__name__ != self.func_name:
                raise ValueError(
                    f"非同名函数 '{func.__name__}' 不能注册到 '{self.func_name}' "
                    f"（非 Priority 模式必须同名）"
                )

        if priority is None:
            priority = 0

        check = self._get_check_func(func)
        reg_index = self.counter
        self.counter += 1
        self.overloads.append((check, func, priority, reg_index, func.__name__))

    # ------------------------------------------------------------------
    # register 公共 API（支持装饰器用法 + 链式注册）
    # ------------------------------------------------------------------

    def register(self,
                 func: Optional[Callable] = None,
                 *,
                 priority: Optional[int] = None,
                 export_mode=None) -> Union[Callable, 'OverloadManager']:
        """注册重载函数。

        参数:
            func: 要注册的函数；若为 None 则返回装饰器
            priority: 优先级（默认 0；在 Priority 模式下生效）
            export_mode: 决定 register 调用的返回值
                - None (默认)：返回原函数，不改变原函数
                - ParentMode / ExportAsManager：返回新管理器（继承父级模式）
                - OverloadMode 值：以指定模式创建新管理器

        返回:
            原函数 / 管理器 —— 取决于 export_mode
        """
        eff_export_mode = export_mode if export_mode is not None else self.export_mode

        def _handle(f: Callable):
            eff_priority = priority if priority is not None else 0
            self._register_function(f, priority=eff_priority)

            # 默认：不改变原函数，返回 f
            if eff_export_mode is None or eff_export_mode is ExportAsFunction:
                return f

            # ParentMode / ExportAsManager：创建子管理器并返回
            if eff_export_mode is ParentMode or eff_export_mode is ExportAsManager:
                return self._spawn_manager(f, self.mode, eff_priority, eff_export_mode)

            # OverloadMode 值：以指定模式创建子管理器
            if isinstance(eff_export_mode, OverloadMode):
                return self._spawn_manager(f, eff_export_mode, eff_priority, eff_export_mode)

            # 兜底：返回原函数
            return f

        if func is None:
            def decorator(f: Callable):
                return _handle(f)
            return decorator

        return _handle(func)

    # ------------------------------------------------------------------
    # 描述符支持：类方法
    # ------------------------------------------------------------------

    def _spawn_manager(self, f: Callable, mode: OverloadMode,
                         priority: int, export_mode) -> 'OverloadManager':
        """创建子管理器。复制当前管理器的现有重载函数。
        使新管理器拥有父级的所有候选函数。"""
        new_manager = OverloadManager(
            func=f,
            mode=mode,
            priority=priority,
            export_mode=export_mode,
            parent=self,
        )
        # 把父管理器已有的重载函数也注册进去（主函数已经在初始化时注册了，所以跳过同名函数）
        # 注意：主函数 f 已经在 __init__ 中注册过了
        # 我们需要把父级的其他函数也加进来，使新管理器也能调用父级的函数
        for _, existing_func, existing_priority, existing_index, existing_name in self.overloads:
            # 避免重复注册主函数
            if existing_func is f:
                continue
            # 注意：注册检查基于新的 mode 可能跟父级 mode 可能有冲突
            # 为避免模式冲突导致报错，直接跳过冲突函数
            try:
                new_manager._register_function(existing_func, priority=existing_priority)
            except ValueError:
                    pass
        return new_manager

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return types.MethodType(self, instance)

    # ------------------------------------------------------------------
    # 调用入口
    # ------------------------------------------------------------------

    def __call__(self, *args, **kwargs) -> Any:
        """根据 mode 匹配候选函数并执行。"""
        has_priority = bool(self.mode & OverloadMode.Priority)
        is_strict = bool(self.mode & OverloadMode.Strict)
        allow_ambiguous = bool(self.mode & OverloadMode.Ambiguous)

        # 优先级模式下按 (-priority, reg_index) 排序；否则保持注册顺序
        if has_priority:
            ordered = sorted(self.overloads, key=lambda x: (-x[2], x[3]))
        else:
            ordered = list(self.overloads)

        candidates: List[Tuple[Callable, Optional[str]]] = []

        for check, func, _, _, _ in ordered:
            if is_strict:
                # 严格模式：check 返回 (ok, error_msg)
                is_valid, msg = check(args, kwargs)
                if is_valid:
                    candidates.append((func, msg))
            else:
                # 非严格模式：用参数数量检查（无副作用）
                if check(args, kwargs):
                    candidates.append((func, None))

        if not candidates:
            raise TypeError(f"没有找到匹配的重载函数")

        if len(candidates) > 1 and not allow_ambiguous:
            names = ", ".join(f.__name__ for f, _ in candidates)
            raise TypeError(f"模糊调用: 多个函数匹配 ({names})")

        return candidates[0][0](*args, **kwargs)

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def __getstate__(self):
        """序列化时剔除 check 函数（闭包不可 pickled）。"""
        serializable = []
        for _, func, priority, reg_index, func_name in self.overloads:
            try:
                pickle.dumps(func)
                serializable.append((None, func, priority, reg_index, func_name))
            except (pickle.PicklingError, AttributeError, TypeError):
                pass
        return {
            'mode': self.mode,
            'overloads': serializable,
            'main_func': self.main_func,
            'export_mode': self.export_mode,
            'func_name': getattr(self, 'func_name', None),
            'module': getattr(self, 'module', None),
            'qualname': getattr(self, 'qualname', None),
            'scope': getattr(self, 'scope', None),
            'counter': self.counter,
            'parent': None,   # 反序列化时父级丢失
        }

    def __setstate__(self, state):
        self.mode = state['mode']
        raw = state.get('overloads', [])
        self.overloads = []
        for _, func, priority, reg_index, func_name in raw:
            check = self._get_check_func(func)
            self.overloads.append((check, func, priority, reg_index, func_name))
        self.main_func = state['main_func']
        self.export_mode = state['export_mode']
        self.func_name = state['func_name']
        self.module = state['module']
        self.qualname = state['qualname']
        self.scope = state['scope']
        self.counter = state['counter']
        self.parent = None

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def is_overload_manager(self) -> bool:
        return True


# =============================================================================
# overload 装饰器入口
# =============================================================================

def overload(func: Optional[Callable] = None,
             *,
             mode: OverloadMode = _DEFAULT_MODE,
             priority: int = 0,
             export_mode=None) -> Union[OverloadManager, Callable]:
    """
    函数重载装饰器，支持多种模式组合。

    支持无括号用法：
        @overload
        def add(a, b): ...

    也支持带参数用法：
        @overload(mode=Priority | Strict)
        def add(a, b): ...

    参数:
        func: 被装饰的函数（若不传，返回装饰器）
        mode: 重载模式，默认 Priority | Strict | AllowSyncName
        priority: 主函数优先级
        export_mode: register 的默认返回策略（默认 None → 返回管理器）

    返回:
        OverloadManager 实例
    """
    if func is None:
        def decorator(f: Callable) -> OverloadManager:
            _validate_mode(mode)
            return OverloadManager(
                func=f,
                mode=mode,
                priority=priority,
                export_mode=export_mode,
            )
        return decorator

    _validate_mode(mode)
    return OverloadManager(
        func=func,
        mode=mode,
        priority=priority,
        export_mode=export_mode,
    )


# =============================================================================
# strict 独立装饰器
# =============================================================================

def strict(func: Optional[Callable] = None, *, enabled: bool = True) -> Callable:
    """
    严格类型检查装饰器（独立于 overload 使用）。

    示例:
        >>> @strict
        ... def add(a: int, b: int) -> int:
        ...     return a + b
        >>> add(1, 2)
        3
        >>> add(1, "2")       # TypeError
    """
    def _wrap(f: Callable) -> Callable:
        sig = get_signature(f)
        annotations = f.__annotations__

        @wraps(f)
        def wrapper(*args, **kwargs):
            if not enabled:
                return f(*args, **kwargs)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            for name, value in bound.arguments.items():
                if name in annotations:
                    expected = annotations[name]
                    if not isinstance(value, expected):
                        raise TypeError(
                            f"参数 '{name}' 应为 "
                            f"{getattr(expected, '__name__', str(expected))}, "
                            f"实际 {type(value).__name__}"
                        )
            return f(*args, **kwargs)

        return wrapper

    if func is None:
        return lambda f: _wrap(f)
    return _wrap(func)
