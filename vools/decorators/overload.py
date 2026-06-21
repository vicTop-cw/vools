"""
函数重载装饰器模块

提供基于模式标志的函数重载系统，支持：
- 优先级模式 (Priority)：按 priority 属性排序匹配
- 非同名注册 (AllowSyncName)：函数名可与原始函数不同
- 严格类型检查 (Strict)：按类型注解精确匹配
- 模糊匹配 (Ambiguous)：多个候选时选第一个而非报错
- 注册模式：默认不修改原函数 (export_mode=None)

示例:
    >>> @overload
    ... def add(a, b):
    ...     return a + b
    ...
    >>> @add.register(export_mode='parent')
    ... def add_int(a: int, b: int):
    ...     return a + b
    ...
    >>> add(1, 2)          # 3 (匹配 add_int)
    >>> add("a", "b")      # "ab" (匹配 add)
    >>> add_int(1, 2)      # 3 (add_int 是 OverloadManager，走重载匹配)
"""

import inspect
import types
from functools import wraps
from typing import Any, Callable, Optional, List, Tuple, Union, Dict, Set, TYPE_CHECKING
from enum import IntFlag

from vools.cache.sigcache import get_signature

try:
    from .curry_core import is_curried, Curried
except ImportError:
    def is_curried(func):
        return False
    class Curried:
        pass
        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self for chaining.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function applied before f
                sub_f: Post-processing function (no return expected)

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
    """重载模式标志"""
    Priority = 1 << 0       # 优先级模式：按 priority 属性排序
    AllowSyncName = 1 << 1  # 允许非同名函数注册
    Strict = 1 << 2          # 严格类型检查
    Ambiguous = 1 << 3       # 允许模糊匹配（多个候选时选第一个）
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



# 别名
Priority = OverloadMode.Priority
AllowSyncName = OverloadMode.AllowSyncName
Strict = OverloadMode.Strict
Ambiguous = OverloadMode.Ambiguous

# 默认模式
_DEFAULT_MODE = Priority | Strict | AllowSyncName


# =============================================================================
# 导出模式常量
# =============================================================================

ParentMode = 'parent'        # 返回管理器（继承父级模式）
ExportAsFunction = None      # 不改变原函数，返回原函数
ExportAsManager = 'manager'  # 返回新管理器


# =============================================================================
# 注册表管理
# =============================================================================

# 注册表：(module, scope, func_name) -> OverloadManager
_registry: Dict[Tuple[str, str, str], 'OverloadManager'] = {}


def _get_registry_key(func_name: str, scope: str, module: str) -> Tuple[str, str, str]:
    """获取注册表键"""
    return (module, scope, func_name)


def _get_scope_from_qualname(qualname: str) -> str:
    """从 qualname 获取作用域（类名或空字符串）"""
    return qualname.rpartition('.')[0]


def reset_registry():
    """重置全局注册表（用于测试隔离）"""
    global _registry
    _registry.clear()


# =============================================================================
# 检查函数工厂
# =============================================================================

def _create_count_check(func: Callable) -> Callable:
    """创建基于参数数量的检查函数"""
    if is_curried(func):
        if hasattr(func, 'func'):
            func = func.func

    sig = get_signature(func)
    params = sig.parameters

    # 计算必需参数数量
    min_args = sum(1 for p in params.values()
                   if p.default == p.empty
                   and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD))

    # 处理可变参数
    has_var_args = any(p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                       for p in params.values())
    max_args = float('inf') if has_var_args else len(params)

    def count_check(args, kwargs):
        arg_count = len(args) + len(kwargs)
        return min_args <= arg_count <= max_args

    return count_check


def _create_strict_check(func: Callable) -> Callable:
    """创建严格的类型检查函数"""
    if is_curried(func):
        if hasattr(func, 'func'):
            func = func.func

    sig = get_signature(func)
    type_hints = func.__annotations__
    params = sig.parameters

    def strict_check(args, kwargs):
        try:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
        except TypeError as e:
            return False, f"参数不匹配: {str(e)}"

        errors = []
        for name, value in bound.arguments.items():
            if name in type_hints:
                expected_type = type_hints[name]
                param = params[name]

                # 处理可变位置参数 (*args)
                if param.kind == inspect.Parameter.VAR_POSITIONAL:
                    for i, item in enumerate(value):
                        if not isinstance(item, expected_type):
                            errors.append(
                                f"位置参数 #{i} (属于*{name}) 类型错误: "
                                f"期望 {expected_type.__name__}, 实际 {type(item).__name__}"
                            )

                # 处理可变关键字参数 (**kwargs)
                elif param.kind == inspect.Parameter.VAR_KEYWORD:
                    for key, item in value.items():
                        if not isinstance(item, expected_type):
                            errors.append(
                                f"关键字参数 '{key}' (属于**{name}) 类型错误: "
                                f"期望 {expected_type.__name__}, 实际 {type(item).__name__}"
                            )

                # 处理普通参数
                else:
                    if not isinstance(value, expected_type):
                        errors.append(
                            f"参数 '{name}' 类型错误: "
                            f"期望 {expected_type.__name__}, 实际 {type(value).__name__}"
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
    重载管理器

    存储函数列表，按模式和优先级进行匹配。

    属性:
        mode: 重载模式标志
        overloads: 已注册的重载函数列表 (check, func, priority, reg_index, func_name)
        main_func: 主函数
        export_mode: 导出模式
    """

    def __init__(self, func: Optional[Callable] = None,
                 mode: OverloadMode = OverloadMode(0),
                 priority: int = 0,
                 export_mode: Optional[OverloadMode] = None):
        """
        初始化重载管理器

        Args:
            func: 要注册的主函数
            mode: 重载模式
            priority: 主函数的优先级
            export_mode: 导出模式
        """
        self.mode = mode
        self.overloads: List[Tuple[Callable, Callable, int, int, str]] = []
        self.main_func: Optional[Callable] = func
        self.export_mode = export_mode
        self.counter = 0

        # 获取函数信息
        if func:
            self.func_name = func.__name__
            self.module = func.__module__
            self.qualname = func.__qualname__
            self.scope = _get_scope_from_qualname(self.qualname)
            self.key = _get_registry_key(self.func_name, self.scope, self.module)

            # 验证模式组合
            self._validate_mode()

            # 注册主函数
            self._register_function(func, priority=priority)

    def _validate_mode(self) -> None:
        """验证模式组合的合法性"""
        mode = self.mode

        # 非优先级模式不允许 AllowSyncName
        if not (mode & OverloadMode.Priority) and (mode & OverloadMode.AllowSyncName):
            raise ValueError(
                "AllowSyncName 只能在 Priority 模式下使用"
            )

    def _get_check_func(self, func: Callable) -> Callable:
        """获取检查函数"""
        if self.mode & OverloadMode.Strict:
            return _create_strict_check(func)
        else:
            return _create_count_check(func)

    def register(self, func: Optional[Callable] = None,
                 priority: Optional[int] = None,
                 export_mode=None) -> Union[Callable, 'OverloadManager', 'NewOverloadManager']:
        """
        注册重载函数

        Args:
            func: 要注册的函数
            priority: 优先级（仅在 Priority 模式下有效）
            export_mode: 导出模式
                         - None: 不改变原函数，返回原函数
                         - ParentMode: 返回管理器（继承父级模式）
                         - ExportAsManager: 返回新管理器
                         - OverloadMode 值: 使用该模式作为新管理器的模式

        Returns:
            decorator / OverloadManager / NewOverloadManager
        """
        # 使用传入的 export_mode 或继承父级
        eff_export_mode = export_mode if export_mode is not None else self.export_mode

        # 如果不允许链式注册，返回原函数
        if hasattr(self, '_allow_chain_register') and not self._allow_chain_register:
            if func is None:
                def decorator(f):
                    return f
                return decorator
            return func

        def _create_manager(f, mode, export_mode=None):
            """创建新管理器"""
            new_priority = priority if priority is not None else 0

            # 优先级模式下，如果新管理器需要 AllowSyncName，主管理器也必须支持
            if mode & OverloadMode.AllowSyncName and not (self.mode & OverloadMode.Priority):
                raise ValueError(
                    f"函数 '{self.func_name}' 不支持 AllowSyncName "
                    f"（需要 Priority 模式）"
                )

            new_manager = NewOverloadManager(
                func=f,
                mode=mode,
                priority=new_priority,
                parent=self,
                export_mode=export_mode
            )
            return new_manager

        def _handle_func(f):
            # 始终将函数注册到当前管理器的重载列表
            eff_priority = priority if priority is not None else 0
            self._register_function(f, priority=eff_priority)

            # None 或 ExportAsFunction：不改变原函数
            if eff_export_mode is None:
                return f

            # ParentMode：返回管理器（继承父级模式）
            if eff_export_mode is ParentMode:
                if isinstance(self.mode, OverloadMode) and self.mode & OverloadMode.Priority:
                    manager = _create_manager(f, self.mode, export_mode=ParentMode)
                    # ParentMode 允许链式注册
                    return manager
                else:
                    return f

            # ExportAsManager：返回新管理器
            if eff_export_mode is ExportAsManager:
                manager = _create_manager(f, self.mode, export_mode=ExportAsManager)
                # ExportAsManager 允许链式注册
                return manager

            # OverloadMode 值：使用该模式
            if isinstance(eff_export_mode, OverloadMode):
                manager = _create_manager(f, eff_export_mode, export_mode=eff_export_mode)
                if eff_export_mode & OverloadMode.Priority:
                    manager._allow_chain_register = False
                return manager

            # 默认：不改变原函数
            return f

        if func is None:
            def decorator(f):
                return _handle_func(f)
            return decorator

        return _handle_func(func)

    def _register_function(self, func: Callable, priority: Optional[int] = None) -> None:
        """内部注册函数"""
        # 优先级模式检查：非同名函数需要 AllowSyncName
        if self.mode & OverloadMode.Priority:
            if func.__name__ != self.func_name and not (self.mode & OverloadMode.AllowSyncName):
                raise ValueError(
                    f"非同名函数 '{func.__name__}' 不能注册到 '{self.func_name}' "
                    f"（需要 AllowSyncName 模式）"
                )

        # 非优先级模式检查：必须同名
        if not (self.mode & OverloadMode.Priority):
            if func.__name__ != self.func_name:
                raise ValueError(
                    f"非同名函数 '{func.__name__}' 不能注册到 '{self.func_name}' "
                    f"（非优先级模式必须同名）"
                )

        # 设置默认优先级
        if priority is None:
            priority = 0

        # 创建检查函数
        check = self._get_check_func(func)

        # 记录注册顺序
        reg_index = self.counter
        self.counter += 1
        self.overloads.append((check, func, priority, reg_index, func.__name__))

    def __get__(self, instance, owner):
        """描述符协议，支持类方法绑定"""
        if instance is None:
            return self
        return types.MethodType(self, instance)

    def __call__(self, *args, **kwargs) -> Any:
        """执行重载函数调用"""
        candidates = []

        # 按优先级排序
        sorted_overloads = sorted(self.overloads, key=lambda x: (-x[2], x[3]))

        for check, func, _, _, func_name in sorted_overloads:
            try:
                if self.mode & OverloadMode.Strict:
                    is_valid, error_msg = check(args, kwargs)
                    if is_valid:
                        candidates.append((func, error_msg))
                else:
                    # 普通模式：直接尝试调用
                    result = func(*args, **kwargs)
                    candidates.append((func, None))
            except (TypeError, ValueError) as e:
                continue

        # 处理候选函数
        if len(candidates) == 0:
            raise TypeError(f"没有找到匹配的重载函数")

        if len(candidates) > 1:
            if self.mode & OverloadMode.Ambiguous:
                # 允许模糊：执行第一个
                return candidates[0][0](*args, **kwargs)
            else:
                # 不允许模糊：报错
                raise TypeError(f"模糊调用: 多个函数匹配")
        else:
            return candidates[0][0](*args, **kwargs)


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
    def is_overload_manager(self) -> bool:
        """检查是否是 OverloadManager"""
        return True


class NewOverloadManager(OverloadManager):
    """
    新建的重载管理器（从 register 返回）

    继承父管理器的模式和导出行为
    """

    def __init__(self, func: Callable, mode: OverloadMode, priority: int,
                 parent: OverloadManager, export_mode=None):
        self.parent = parent
        self.func_name = func.__name__
        self.module = func.__module__
        self.qualname = func.__qualname__
        self.scope = _get_scope_from_qualname(self.qualname)
        self.key = _get_registry_key(self.func_name, self.scope, self.module)

        # 新管理器的模式
        self.mode = mode
        self.overloads: List[Tuple[Callable, Callable, int, int, str]] = []
        self.main_func: Optional[Callable] = func
        self.export_mode = export_mode
        self.counter = 0
        self._allow_chain_register = True  # 是否允许链式注册

        # 验证模式
        self._validate_mode()

        # 注册主函数
        self._register_function(func, priority=priority)

    # ---- serialization support ----

    def __getstate__(self):
        """Return serialization state (exclude check functions)"""
        import pickle as _pickle
        serializable = []
        for _, func, priority, reg_index, func_name in self.overloads:
            try:
                # Verify the function is pickleable
                _pickle.dumps(func)
                serializable.append((None, func, priority, reg_index, func_name))
            except (_pickle.PicklingError, AttributeError, TypeError):
                # Function is not pickleable (e.g. name shadowed by manager)
                pass
        return {
            'mode': self.mode,
            'overloads': serializable,
            'main_func': self.main_func,
            'export_mode': self.export_mode,
            'func_name': self.func_name,
            'module': self.module,
            'qualname': self.qualname,
            'scope': self.scope,
            'key': self.key,
            'counter': self.counter,
            '_allow_chain_register': self._allow_chain_register,
        }

    def __setstate__(self, state):
        """Restore from serialization state"""
        self.mode = state['mode']
        raw_overloads = state.get('overloads', [])
        self.overloads = []
        for _, func, priority, reg_index, func_name in raw_overloads:
            check = self._get_check_func(func)
            self.overloads.append((check, func, priority, reg_index, func_name))
        self.main_func = state['main_func']
        self.export_mode = state['export_mode']
        self.func_name = state['func_name']
        self.module = state['module']
        self.qualname = state['qualname']
        self.scope = state['scope']
        self.key = state['key']
        self.counter = state['counter']
        self._allow_chain_register = state.get('_allow_chain_register', True)
        self.parent = None

    def _validate_mode(self) -> None:
        """验证模式组合的合法性"""
        mode = self.mode

        if not (mode & OverloadMode.AllowSyncName):
            raise ValueError(
                "NewOverloadManager 必须启用 AllowSyncName"
            )
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function (no return expected)

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



# =============================================================================
# overload 装饰器
# =============================================================================

def overload(func: Optional[Callable] = None,
             *,
             mode: OverloadMode = _DEFAULT_MODE,
             priority: int = 0,
             export_mode=None) -> Union[OverloadManager, Callable]:
    """
    高效的重载装饰器，支持多种模式组合

    Args:
        func: 主函数（可选，不填时返回装饰器）
        mode: 重载模式标志组合，默认 Priority | Strict | AllowSyncName
        priority: 主函数的优先级
        export_mode: 导出模式

    Returns:
        OverloadManager 实例

    模式组合:
        - Priority: 优先级模式
        - AllowSyncName: 允许非同名函数
        - Strict: 严格类型检查
        - Ambiguous: 允许模糊

    示例:
        >>> @overload
        ... def add(a, b):
        ...     return a + b

        >>> @overload(mode=Priority | Strict | Ambiguous)
        ... def add(a, b):
        ...     return a + b
    """
    if func is None:
        def decorator(f: Callable) -> OverloadManager:
            _validate_mode_global(mode)
            manager = OverloadManager(
                func=f,
                mode=mode,
                priority=priority,
                export_mode=export_mode
            )
            return manager
        return decorator

    # 直接装饰函数
    _validate_mode_global(mode)
    return OverloadManager(
        func=func,
        mode=mode,
        priority=priority,
        export_mode=export_mode
    )


def _validate_mode_global(mode: OverloadMode) -> None:
    """验证模式组合的合法性"""
    if not (mode & OverloadMode.Priority) and (mode & OverloadMode.AllowSyncName):
        raise ValueError(
            "AllowSyncName 只能在 Priority 模式下使用"
        )


# =============================================================================
# 严格类型检查装饰器（独立使用）
# =============================================================================

class StrictMode:
    """strict 装饰器的辅助类"""
    def __init__(self, func: Optional[Callable] = None, *, enabled: bool = True):
        if func is None:
            self._enabled = enabled
        else:
            self._enabled = enabled
            self.func = func


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
    def __call__(self, *args, **kwargs):
        if self._enabled:
            return _strict_wrapper(self.func)(*args, **kwargs)
        return self.func(*args, **kwargs)


def _strict_wrapper(func: Callable) -> Callable:
    """严格类型检查包装器"""
    sig = get_signature(func)
    annotations = func.__annotations__

    @wraps(func)
    def wrapper(*args, **kwargs):
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        for name, value in bound.arguments.items():
            if name in annotations:
                expected_type = annotations[name]
                if not isinstance(value, expected_type):
                    raise TypeError(
                        f"参数 '{name}' 应为 {expected_type.__name__} 类型，"
                        f"实际传入 {type(value).__name__} 类型"
                    )

        return func(*args, **kwargs)
    return wrapper


def strict(func: Optional[Callable] = None, *, enabled: bool = True) -> Union[Callable, StrictMode]:
    """
    严格类型检查装饰器

    Args:
        func: 要包装的函数
        enabled: 是否启用检查（默认 True）

    Returns:
        包装后的函数 或 StrictMode 实例

    示例:
        >>> @strict
        ... def add(a: int, b: int) -> int:
        ...     return a + b
        >>> add(1, 2)      # 3
        >>> add(1, "2")    # TypeError
    """
    if func is None:
        def decorator(f: Callable) -> Callable:
            return _strict_wrapper(f)
        return decorator
    else:
        return _strict_wrapper(func)
