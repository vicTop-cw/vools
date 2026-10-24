"""
Maybe type for optional value handling

提供可选值处理的 Maybe 类型，支持 Some（有值）和 Nothing（无值）两种状态。
类似于 Haskell 的 Maybe 或 Rust 的 Option，用于安全地处理可能缺失的值。
"""

from typing import TypeVar, Callable, Generic, Optional, Any, Union

T = TypeVar('T')
R = TypeVar('R')
E = TypeVar('E')


class Maybe(Generic[T]):
    """
    可选值处理的 Maybe 类型

    Maybe 类型封装了可能存在或不存在的值，可以是 Some（有值）或 Nothing（无值）。
    这是一种类型安全的可选值处理方式，避免使用 None 检查。
    """

    @staticmethod
    def _require_callable(fn: Any, what: str) -> None:
        """回调参数校验（BUG-438）。

        原实现对 ``map/filter/bind/flat_map/or_else/unwrap_or_else/map_or``
        的回调零校验：``some(1).filter('x')`` 抛 ``'str' object is not
        callable``（看不出是回调参数错误）；而 ``nothing().filter('x')``
        因为回调不会被调用而**静默返回 Nothing**（非法回调被悄悄接受）。
        """
        if not callable(fn):
            raise TypeError(
                f"Maybe.{what}() 的回调必须可调用，收到 "
                f"{type(fn).__name__}: {fn!r}")

    def __init__(self, value: Union[T, None], has_value: bool):
        self._value = value
        self._has_value = has_value

    @classmethod
    def some(cls, value: T) -> 'Maybe[T]':
        """创建有值的 Maybe"""
        if value is None:
            return cls.none()
        return cls(value, has_value=True)

    @classmethod
    def none(cls) -> 'Maybe[T]':
        """创建无值的 Maybe（Nothing）"""
        return cls(None, has_value=False)

    @classmethod
    def from_optional(cls, value: Optional[T]) -> 'Maybe[T]':
        """从 Optional 值创建 Maybe"""
        if value is None:
            return cls.none()
        return cls.some(value)

    @property
    def has_value(self) -> bool:
        """判断是否有值"""
        return self._has_value

    @property
    def is_none(self) -> bool:
        """判断是否为无值"""
        return not self._has_value

    def bind(self, fn: Callable[[T], 'Maybe[R]']) -> 'Maybe[R]':
        """
        链式调用，只有有值时才执行函数

        Args:
            fn: 接收值并返回新 Maybe 的函数

        Returns:
            新的 Maybe 对象
        """
        self._require_callable(fn, 'bind')
        if self.has_value:
            return fn(self._value)
        return Maybe.none()

    def map(self, fn: Callable[[T], R]) -> 'Maybe[R]':
        """
        映射值，无值时保持不变

        Args:
            fn: 对值进行转换的函数

        Returns:
            新的 Maybe 对象，有值时包含转换后的值
        """
        self._require_callable(fn, 'map')
        if self.has_value:
            return Maybe.some(fn(self._value))
        return Maybe.none()

    def map_or(self, fn: Callable[[T], R], default: R) -> R:
        """
        映射值或使用默认值

        Args:
            fn: 对值进行转换的函数
            default: 无值时返回的默认值

        Returns:
            转换后的值或默认值
        """
        self._require_callable(fn, 'map_or')
        if self.has_value:
            return fn(self._value)
        return default

    def unwrap(self) -> T:
        """
        获取值，无值时抛出异常

        Returns:
            有值时返回值

        Raises:
            ValueError: 如果是无值状态
        """
        if self.has_value:
            return self._value
        raise ValueError("Cannot unwrap None Maybe")

    def unwrap_or(self, default: T) -> T:
        """
        获取值或默认值

        Args:
            default: 无值时返回的默认值

        Returns:
            值或默认值
        """
        if self.has_value:
            return self._value
        return default

    def unwrap_or_else(self, fn: Callable[[], T]) -> T:
        """
        获取值或通过函数计算的值

        Args:
            fn: 返回默认值的函数

        Returns:
            值或函数计算的默认值
        """
        self._require_callable(fn, 'unwrap_or_else')
        if self.has_value:
            return self._value
        return fn()

    def or_else(self, fn: Callable[[], 'Maybe[T]']) -> 'Maybe[T]':
        """
        无值时执行备选函数

        Args:
            fn: 返回新 Maybe 的函数

        Returns:
            有值时返回原 Maybe，无值时返回备选函数的结果
        """
        self._require_callable(fn, 'or_else')
        if self.has_value:
            return self
        return fn()

    def get_or(self, default: T) -> T:
        """获取值或默认值，同 unwrap_or"""
        return self._value if self.has_value else default

    def flat_map(self, fn: Callable[[T], 'Maybe[R]']) -> 'Maybe[R]':
        """扁平化映射，同 bind"""
        self._require_callable(fn, 'flat_map')
        return self.bind(fn)

    def filter(self, pred: Callable[[T], bool]) -> 'Maybe[T]':
        """
        过滤值，如果值不满足条件则变为 Nothing

        Args:
            pred: 过滤条件

        Returns:
            满足条件时返回原 Maybe，否则返回 Nothing
        """
        self._require_callable(pred, 'filter')
        if self.has_value and pred(self._value):
            return self
        return Maybe.none()

    def if_some(self, fn: Callable[[T], None]) -> 'Maybe[T]':
        """有值时执行副作用函数"""
        self._require_callable(fn, 'if_some')
        if self.has_value:
            fn(self._value)
        return self

    def if_none(self, fn: Callable[[], None]) -> 'Maybe[T]':
        """无值时执行副作用函数"""
        self._require_callable(fn, 'if_none')
        if self.is_none:
            fn()
        return self

    def __repr__(self) -> str:
        if self.has_value:
            return f"Some({self._value!r})"
        return "Nothing"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Maybe):
            return False
        return (self._has_value == other._has_value and
                self._value == other._value)

    def __hash__(self) -> int:
        return hash((self._has_value, self._value))

    # ─── 序列化支持 ───

    def __getstate__(self) -> dict:
        return {'_value': self._value, '_has_value': self._has_value}

    def __setstate__(self, state: dict) -> None:
        self._value = state['_value']
        self._has_value = state['_has_value']


class Some(Maybe[T]):
    """有值的便捷子类"""

    def __init__(self, value: T):
        if value is None:
            raise ValueError("Some cannot hold None value, use Maybe.none() instead")
        Maybe.__init__(self, value, has_value=True)


# Nothing 作为单例使用
class Nothing_(Maybe[T]):
    """无值的便捷子类"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
        return cls._instance

    def __init__(self):
        # 避免重复初始化
        if not hasattr(self, '_initialized'):
            Maybe.__init__(self, None, has_value=False)
            self._initialized = True


def some(value: T) -> Maybe[T]:
    """创建 Some 的便捷函数"""
    return Maybe.some(value)


def nothing() -> Maybe:
    """创建 Nothing 的便捷函数"""
    return Maybe.none()


def optional(value: Optional[T]) -> Maybe[T]:
    """从 Optional 值创建 Maybe 的便捷函数"""
    return Maybe.from_optional(value)


def maybe_map(d: dict, key: str) -> Maybe:
    """从字典中安全获取值并包装为 Maybe"""
    return Maybe.from_optional(d.get(key))


__all__ = [
    'Maybe',
    'Some',
    'Nothing_',
    'some',
    'nothing',
    'optional',
    'maybe_map',
]
