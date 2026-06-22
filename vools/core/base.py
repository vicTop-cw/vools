"""
核心基础类
"""

__all__ = ['VoolsBase', '_validate_type', '_ensure_callable']

from functools import wraps as _wraps


class VoolsBase:
    """vools 基础类，提供通用方法和属性"""

    def __repr__(self):
        return f"<{self.__class__.__name__}>"

    def __str__(self):
        return self.__repr__()

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return False

    def __hash__(self):
        return hash(tuple(sorted(self.__dict__.items())))

    def to_dict(self):
        """转换为字典"""
        result = {}
        for key, value in self.__dict__.items():
            if not key.startswith('_'):
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data):
        """从字典创建对象"""
        return cls(**data)

    def copy(self):
        """返回对象的浅拷贝"""
        return self.__class__(**self.__dict__) if not self.__dict__ else self.__class__(self.__dict__.copy())


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
    
    def update(self, **kwargs):
        """更新对象属性"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self


def _validate_type(value, expected_type, param_name=''):
    """类型验证辅助函数"""
    if not isinstance(value, expected_type):
        raise TypeError(f"{param_name} expected {expected_type.__name__}, got {type(value).__name__}")


def _ensure_callable(func):
    """确保值是可调用的"""
    if not callable(func):
        raise TypeError(f"Expected callable, got {type(func).__name__}")
    return func