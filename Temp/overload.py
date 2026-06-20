"""
函数重载装饰器模块 - 合并版本

支持多种模式组合：
- Priority: 优先级模式，按注册时的 priority 属性排序匹配
- AllowSyncName: 允许非同名函数注册（仅在优先级模式下生效）
- Strict: 严格类型检查模式
- Ambiguous: 允许模糊匹配（存在多个候选函数时也执行第一个）

模式组合规则：
1. Priority 模式：按 priority 属性尝试匹配，非同名函数需通过 export_mode 导出
2. 非优先级模式：必须函数同名
3. Strict 模式：检查参数类型注解
4. Ambiguous 模式：允许多个候选函数存在

示例:
    # 优先级模式 + 严格 + 允许非同名 + 允许模糊
    @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
    def add(a, b):
        return a + b

    @add.register(export_mode=ParentMode)
    def add_int(a: int, b: int):
        return a + b

    add(1, 2)  # OK
"""

import inspect
import types
from functools import wraps
from typing import Any, Callable, Optional, List, Tuple, Union, Dict, Set, TYPE_CHECKING
from enum import IntFlag

from vools.sig_cache import get_signature
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from vools.decorators.curry_core import is_curried, Curried
except ImportError:
    # 如果导入失败，定义空函数
    def is_curried(func):
        return False
    class Curried:
        pass

__all__ = [
    'overload', 'OverloadManager', 'NewOverloadManager',
    'Strict', 'Ambiguous', 'Priority', 'AllowSyncName',
    'ParentMode', 'ExportAsFunction', 'ExportAsManager',
    'reset_registry'
]


# =============================================================================
# 模式标志定义
# =============================================================================

class OverloadMode(IntFlag):
    """重载模式标志"""
    # 基本模式
    Priority = 1 << 0       # 优先级模式：按 priority 属性排序
    AllowSyncName = 1 << 1  # 允许非同名函数注册
    Strict = 1 << 2          # 严格类型检查
    Ambiguous = 1 << 3       # 允许模糊匹配（多个候选）


# 别名
Priority = OverloadMode.Priority
AllowSyncName = OverloadMode.AllowSyncName
Strict = OverloadMode.Strict
Ambiguous = OverloadMode.Ambiguous


# 导出模式别名
ParentMode = 'parent'  # 特殊标记，表示返回管理器（继承父级模式）
ExportAsFunction = None  # 不改变原函数，返回原函数
ExportAsManager = 'manager'  # 特殊标记，表示返回新管理器


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
    import typing

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

    def __init__(self, func: Optional[Callable] = None, mode: OverloadMode = OverloadMode(0),
                 priority: int = 0, export_mode: Optional[OverloadMode] = None):
        """
        初始化重载管理器

        参数:
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
            if mode & OverloadMode.Priority:
                # 优先级模式下，主函数注册为第一个
                self._register_function(func, priority=priority)
            else:
                # 非优先级模式，必须同名
                self._register_function(func, priority=priority)

    def _validate_mode(self) -> None:
        """验证模式组合的合法性"""
        mode = self.mode

        # 非优先级模式不允许 AllowSyncName
        if not (mode & OverloadMode.Priority) and (mode & OverloadMode.AllowSyncName):
            raise ValueError(
                "AllowSyncName 只能在 Priority 模式下使用"
            )

        # 非优先级模式不允许 Ambiguous（除非没有多个候选）
        # 这个在运行时检查，不在初始化时检查

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

        参数:
            func: 要注册的函数
            priority: 优先级（仅在 Priority 模式下有效）
            export_mode: 导出模式
                         - None: 不改变原函数，返回原函数
                         - ParentMode: 返回管理器（继承父级模式）
                         - ExportAsManager: 返回新管理器（继承父级模式）
                         - OverloadMode 值: 使用该模式作为新管理器的模式

        返回:
            装饰器/管理器/新管理器
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

            # ExportAsManager：返回新管理器（继承父级模式）
            if eff_export_mode is ExportAsManager:
                manager = _create_manager(f, self.mode, export_mode=ExportAsManager)
                # ExportAsManager 允许链式注册
                return manager

            # OverloadMode 值：使用该模式
            if isinstance(eff_export_mode, OverloadMode):
                manager = _create_manager(f, eff_export_mode, export_mode=eff_export_mode)
                # 如果包含 Priority，后续注册返回原函数
                if eff_export_mode & OverloadMode.Priority:
                    manager._allow_chain_register = False
                else:
                    # 不包含 Priority 时允许链式注册
                    pass
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
                raise TypeError(f"Ambiguous call: 多个函数匹配")
        else:
            return candidates[0][0](*args, **kwargs)

    def is_overload_manager(self) -> bool:
        """检查是否是 overloadManager"""
        return True


class NewOverloadManager(OverloadManager):
    """
    新建的重载管理器（从 register 返回）

    继承父管理器的模式和导出行为
    """

    def __init__(self, func: Callable, mode: OverloadMode, priority: int, parent: OverloadManager, export_mode=None):
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
        self.export_mode = export_mode  # 继承的导出模式
        self.counter = 0
        self._allow_chain_register = True  # 是否允许链式注册（False时后续register返回原函数）

        # 验证模式
        self._validate_mode()

        # 注册主函数
        if mode & OverloadMode.Priority:
            self._register_function(func, priority=priority)
        else:
            self._register_function(func, priority=priority)

    def _validate_mode(self) -> None:
        """验证模式组合的合法性"""
        mode = self.mode

        # 非优先级模式不允许 AllowSyncName
        if not (mode & OverloadMode.Priority) and (mode & OverloadMode.AllowSyncName):
            raise ValueError(
                "AllowSyncName 只能在 Priority 模式下使用"
            )


# =============================================================================
# overload 装饰器
# =============================================================================

# 默认模式：优先级 | 严格 | 允许同名
_DEFAULT_MODE = Priority | Strict | AllowSyncName


def overload(func: Optional[Callable] = None,
            *,
            mode: OverloadMode = _DEFAULT_MODE,
            priority: int = 0,
            check: Optional[Callable] = None,
            export_mode=None) -> Union[OverloadManager, Callable]:
    """
    高效的重载装饰器，支持多种模式组合

    参数:
        func: 主函数（可选，不填时返回装饰器）
        mode: 重载模式标志组合，默认 Priority | Strict | AllowSyncName
        priority: 主函数的优先级
        check: 自定义参数匹配规则（已废弃）
        export_mode: 导出模式

    返回:
        OverloadManager 实例

    模式组合:
        - Priority: 优先级模式
        - AllowSyncName: 允许非同名函数
        - Strict: 严格类型检查
        - Ambiguous: 允许模糊

    使用示例:
        # 无括号调用（使用默认模式 Priority | Strict | AllowSyncName）
        >>> @overload
        ... def add(a, b):
        ...     return a + b

        # 带括号调用（指定模式）
        >>> @overload(mode=Priority | Strict | Ambiguous)
        ... def add(a, b):
        ...     return a + b
    """
    if func is None:
        def decorator(f: Callable) -> OverloadManager:
            # 验证模式
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
    # 非优先级模式不允许 AllowSyncName
    if not (mode & OverloadMode.Priority) and (mode & OverloadMode.AllowSyncName):
        raise ValueError(
            "AllowSyncName 只能在 Priority 模式下使用"
        )


# =============================================================================
# 兼容性别名
# =============================================================================

class StrictMode:
    """兼容性别名"""
    def __init__(self, func: Optional[Callable] = None, *, enabled: bool = True):
        if func is None:
            self._enabled = enabled
        else:
            self._enabled = enabled
            self.func = func

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
    """严格类型检查装饰器"""
    if func is None:
        def decorator(f: Callable) -> Callable:
            return _strict_wrapper(f)
        return decorator
    else:
        return _strict_wrapper(func)


# =============================================================================
# 测试
# =============================================================================

def test_examples():
    """测试所有例子"""
    print("=" * 60)
    print("测试例子 1: Priority + AllowSyncName + Strict + Ambiguous")
    print("=" * 60)
    reset_registry()

    @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
    def add(a, b):
        return a + b

    @add.register(export_mode=ParentMode)
    def add2(a: int, b: int):
        return a + b

    try:
        result = add(1, 2)
        print(f"add(1, 2) = {result}  # OK")
    except TypeError as e:
        print(f"add(1, 2) Error: {e}")

    print()
    print("=" * 60)
    print("测试例子 2: Priority + AllowSyncName + Strict (不允许模糊)")
    print("=" * 60)
    reset_registry()

    @overload(mode=Priority | AllowSyncName | Strict)
    def add(a, b):
        return a + b

    @add.register(export_mode=ParentMode)
    def add2(a: int, b: int):
        return a + b

    try:
        result = add(1, 2)
        print(f"add(1, 2) = {result}")
    except TypeError as e:
        print(f"add(1, 2) Error: Ambiguous")

    print()
    print("=" * 60)
    print("测试例子 3: add2 是 overloadManager")
    print("=" * 60)
    reset_registry()

    @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
    def add(a, b):
        return a + b

    @add.register(export_mode=ParentMode)
    def add2(a: int, b: int):
        return a + b

    print(f"add 是 OverloadManager: {add.is_overload_manager()}")
    print(f"add2 是 OverloadManager: {add2.is_overload_manager()}")

    # 尝试在 add2 上注册
    try:
        @add2.register
        def add3(a: int, b: int):
            return a + b
        print(f"add3 注册成功")
        print(f"add3 是 OverloadManager: {add3.is_overload_manager()}")
    except Exception as e:
        print(f"add3 注册失败: {e}")

    print()
    print("=" * 60)
    print("测试例子 4: add2 有 export_mode=Priority+AllowSyncName+Strict")
    print("=" * 60)
    reset_registry()

    @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
    def add(a, b):
        return a + b

    @add.register(export_mode=Priority | AllowSyncName | Strict)
    def add2(a: int, b: int):
        return a + b

    print(f"add2 是 OverloadManager: {add2.is_overload_manager()}")

    try:
        @add2.register
        def add3(a: int, b: int):
            return a + b
        print(f"add3 注册成功")
        print(f"add3 是 OverloadManager: {hasattr(add3, 'is_overload_manager') and add3.is_overload_manager()}")
    except Exception as e:
        print(f"add3 注册失败（符合预期）: {type(e).__name__}")

    # add3 是原函数，可以直接调用
    if not hasattr(add3, 'is_overload_manager') or not add3.is_overload_manager():
        print(f"add3 是原函数，直接调用: add3(1, 3) = {add3(1, 3)}")

    print()
    print("=" * 60)
    print("测试例子 5: add 不允许 AllowSyncName")
    print("=" * 60)
    reset_registry()

    try:
        @overload(mode=Priority | Strict | Ambiguous)
        def add(a, b):
            return a + b

        @add.register(export_mode=Priority | AllowSyncName | Strict)
        def add2(a: int, b: int):
            return a + b
    except ValueError as e:
        print(f"Error: {e}")

    print()
    print("=" * 60)
    print("测试例子 6: 非优先级模式不允许 AllowSyncName")
    print("=" * 60)
    reset_registry()

    try:
        @overload(mode=AllowSyncName | Strict | Ambiguous)
        def add(a, b):
            return a + b
    except ValueError as e:
        print(f"Error: {e}")

    print()
    print("=" * 60)
    print("测试例子 7: 非优先级模式不允许 Ambiguous")
    print("=" * 60)
    reset_registry()

    try:
        @overload(mode=Strict | Ambiguous)
        def add(a, b):
            return a + b
    except ValueError as e:
        print(f"Error: {e}")

    print()
    print("=" * 60)
    print("测试例子 8: 非优先级模式的普通注册（同名的重载函数）")
    print("=" * 60)
    reset_registry()

    @overload(mode=Strict)
    def add(a, b):
        return a + b

    # @overload 装饰后 add 是 OverloadManager
    print(f"add 是 OverloadManager: {add.is_overload_manager()}")

    # 注册同名函数，非优先级模式返回原函数
    @add.register
    def add_int(a: int, b: int):  # 使用同名函数
        return a + b

    # 在非优先级模式下，add_int 现在是原函数（不是管理器）
    print(f"add_int 是 OverloadManager: {hasattr(add_int, 'is_overload_manager') and add_int.is_overload_manager()}")

    try:
        result = add_int(1, 3)
        print(f"add_int(1, 3) = {result}")
    except TypeError as e:
        print(f"add_int(1, 3) Error: Ambiguous")

    print()
    print("=" * 60)
    print("测试例子 9: export_mode=ExportAsFunction 不改变原函数")
    print("=" * 60)
    reset_registry()

    @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
    def add(a, b):
        return a + b

    @add.register(export_mode=ParentMode)
    def add2(a: int, b: int):
        return a + b

    print(f"add2 是 OverloadManager: {hasattr(add2, 'is_overload_manager') and add2.is_overload_manager()}")
    print(f"add2(1, 2) = {add2(1, 2)}")

    print()
    print("=" * 60)
    print("测试例子 10: export_mode=ExportAsManager 创建新管理器")
    print("=" * 60)
    reset_registry()

    @overload(mode=Priority | AllowSyncName | Strict | Ambiguous)
    def add(a, b):
        return a + b

    @add.register(export_mode=ExportAsManager)
    def add2(a: int, b: int):
        return a + b

    print(f"add2 是 OverloadManager: {add2.is_overload_manager()}")

    try:
        @add2.register
        def add3(a: int, b: int):
            return a + b
        print(f"add3 注册成功")
        print(f"add3 是 OverloadManager: {add3.is_overload_manager()}")
    except Exception as e:
        print(f"add3 注册失败: {e}")

    print()
    print("=" * 60)
    print("测试例子 11: 可变参数支持")
    print("=" * 60)
    reset_registry()

    @overload(mode=Priority | AllowSyncName | Ambiguous)
    def sum_all(a, b, *args):
        result = a + b
        for arg in args:
            result += arg
        return result

    @sum_all.register(export_mode=ParentMode)
    def sum_int(a: int, b: int, *args: int):
        result = a + b
        for arg in args:
            result += arg
        return result

    print(f"sum_all(1, 2) = {sum_all(1, 2)}")
    print(f"sum_all(1, 2, 3, 4) = {sum_all(1, 2, 3, 4)}")
    print(f"sum_all('a', 'b', 'c') = {sum_all('a', 'b', 'c')}")

    print()
    print("=" * 60)
    print("测试例子 12: @overload 无括号调用（默认模式）")
    print("=" * 60)
    reset_registry()

    @overload  # 无括号，使用默认模式 Priority | Strict | AllowSyncName
    def mul(a, b):
        return a * b

    @mul.register(export_mode=ParentMode)
    def mul_int(a: int, b: int):
        return a * b

    print(f"默认模式: Priority | Strict | AllowSyncName")
    print(f"mul(1, 2) = {mul(1, 2)}")
    print(f"mul(1, 2) 是 Ambiguous: ", end="")
    try:
        result = mul(1, 2)
        print(f"否（结果={result}）")
    except TypeError:
        print("是")

    # 测试非同名函数注册
    @mul.register(export_mode=ParentMode)
    def mul_str(a: str, b: str):
        return a + b

    print(f"mul_str 是 OverloadManager: {mul_str.is_overload_manager()}")


if __name__ == '__main__':
    test_examples()
