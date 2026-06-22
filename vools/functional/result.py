"""
Result type for functional error handling

提供函数式错误处理的核心类型，支持安全的错误处理和链式调用。
"""

from typing import TypeVar, Callable, Generic, Optional, Any, Union

T = TypeVar('T')
E = TypeVar('E', bound=Exception)
R = TypeVar('R')


class Result(Generic[T, E]):
    """
    函数式错误处理的核心类型
    
    Result 类型封装了可能失败的操作结果，可以是 Success 或 Failure。
    这是一种类型安全的错误处理方式，避免使用 try-except 块。
    """
    
    def __init__(self, value: Union[T, E], is_success: bool):
        self._value = value
        self._is_success = is_success
    
    @classmethod
    def success(cls, value: T) -> 'Result[T, E]':
        """创建成功结果"""
        return cls(value, is_success=True)
    
    @classmethod
    def failure(cls, error: E) -> 'Result[T, E]':
        """创建失败结果"""
        return cls(error, is_success=False)
    
    @classmethod
    def from_unsafe(cls, fn: Callable[[], T]) -> 'Result[T, Exception]':
        """从可能抛出异常的函数创建 Result"""
        try:
            return cls.success(fn())
        except Exception as e:
            return cls.failure(e)
    
    @property
    def is_success(self) -> bool:
        """判断是否为成功结果"""
        return self._is_success
    
    @property
    def is_failure(self) -> bool:
        """判断是否为失败结果"""
        return not self._is_success
    
    def bind(self, fn: Callable[[T], 'Result[R, E]']) -> 'Result[R, E]':
        """
        链式调用，只有成功时才执行函数
        
        Args:
            fn: 接收成功值并返回新 Result 的函数
        
        Returns:
            新的 Result 对象
        """
        if self.is_success:
            return fn(self._value)
        return Result.failure(self._value)
    
    def map(self, fn: Callable[[T], R]) -> 'Result[R, E]':
        """
        映射成功值，失败时保持不变
        
        Args:
            fn: 对成功值进行转换的函数
        
        Returns:
            新的 Result 对象，成功时包含转换后的值
        """
        if self.is_success:
            return Result.success(fn(self._value))
        return Result.failure(self._value)
    
    def map_err(self, fn: Callable[[E], Any]) -> 'Result[T, Any]':
        """
        映射失败值，成功时保持不变
        
        Args:
            fn: 对失败值进行转换的函数
        
        Returns:
            新的 Result 对象，失败时包含转换后的值
        """
        if self.is_failure:
            return Result.failure(fn(self._value))
        return Result.success(self._value)
    
    def unwrap(self) -> T:
        """
        获取成功值，失败时抛出异常
        
        Returns:
            成功时返回值
        
        Raises:
            Exception: 如果是失败结果，抛出原始异常
        """
        if self.is_success:
            return self._value
        raise self._value
    
    def unwrap_or(self, default: T) -> T:
        """
        获取成功值或默认值
        
        Args:
            default: 失败时返回的默认值
        
        Returns:
            成功值或默认值
        """
        if self.is_success:
            return self._value
        return default
    
    def unwrap_or_else(self, fn: Callable[[E], T]) -> T:
        """
        获取成功值或通过函数计算的值
        
        Args:
            fn: 接收失败值并返回默认值的函数
        
        Returns:
            成功值或函数计算的默认值
        """
        if self.is_success:
            return self._value
        return fn(self._value)
    
    def or_else(self, fn: Callable[[E], 'Result[T, E]']) -> 'Result[T, E]':
        """
        失败时执行备选函数
        
        Args:
            fn: 接收失败值并返回新 Result 的函数
        
        Returns:
            成功时返回原 Result，失败时返回备选函数的结果
        """
        if self.is_success:
            return self
        return fn(self._value)

    def get_or(self, default: T) -> T:
        """获取值或默认值，同 unwrap_or。

        Args:
            default: 失败时返回的默认值

        Returns:
            成功值或默认值
        """
        return self._value if self.is_success else default

    def get_or_raise(self, exception: Exception) -> T:
        """获取值或抛出异常。

        Args:
            exception: 失败时抛出的异常

        Returns:
            成功值

        Raises:
            exception: 失败时抛出指定异常
        """
        if self.is_failure:
            raise exception
        return self._value

    def flat_map(self, fn: Callable[[T], 'Result[R, E]']) -> 'Result[R, E]':
        """扁平化映射，同 bind。

        Args:
            fn: 接收成功值并返回新 Result 的函数

        Returns:
            新的 Result 对象
        """
        return self.bind(fn)
    
    def __repr__(self) -> str:
        if self.is_success:
            return f"Success({self._value!r})"
        return f"Failure({self._value!r})"
    
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Result):
            return False
        return (self._is_success == other._is_success and
                self._value == other._value)

    # ─── 序列化支持 ───

    def __getstate__(self) -> dict:
        """返回序列化状态"""
        return {'_value': self._value, '_is_success': self._is_success}


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
    def __setstate__(self, state: dict) -> None:
        """从序列化状态恢复"""
        self._value = state['_value']
        self._is_success = state['_is_success']


class Success(Result[T, E]):
    """成功结果的便捷子类"""
    
    def __init__(self, value: T):
        super().__init__(value, is_success=True)


class Failure(Result[T, E]):
    """失败结果的便捷子类"""
    
    def __init__(self, error: E):
        super().__init__(error, is_success=False)


def success(value: T) -> Result[T, Exception]:
    """创建成功结果的便捷函数"""
    return Result.success(value)


def failure(error: E) -> Result[Any, E]:
    """创建失败结果的便捷函数"""
    return Result.failure(error)


def safe(fn: Callable[..., T]) -> Callable[..., Result[T, Exception]]:
    """
    将函数包装为返回 Result 的安全版本
    
    Args:
        fn: 可能抛出异常的函数
    
    Returns:
        返回 Result 的函数
    """
    def wrapper(*args, **kwargs):
        try:
            return Result.success(fn(*args, **kwargs))
        except Exception as e:
            return Result.failure(e)
    return wrapper


__all__ = [
    'Result',
    'Success',
    'Failure',
    'success',
    'failure',
    'safe',
]
