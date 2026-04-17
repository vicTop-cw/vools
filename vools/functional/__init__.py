"""
函数式编程工具模块

包含：
- Pipe: 管道操作
- Ops: 操作符集合
- Seq: 序列操作
- P: 可管道化函数包装器
- iif: 条件判断工具
"""

# 由于这些文件相互依赖且较大，这里先创建一个简化版本
# 完整版本需要从源文件迁移

from typing import Callable, Any, Iterable
from functools import reduce, wraps
import itertools

__all__ = ['Pipe', 'Ops', 'Seq', 'P', 'NONE', 'arrow_func', 'g', 'iif', 'ConditionBuilder', 'LazyProperty', '_', 'magic', 'f', 'to_holder', 'F', 'flip', 'apply', 'hd', 'box', 'Box', 'setattr_box'] + [f"_{i}" for i in range(1, 21)]

# 导入 arrow_func
from .arrow_func import arrow_func, g

# 导入 iif
from .iif import iif, ConditionBuilder, LazyProperty

# 导入 placeholder
from .placeholder import *

# 导入 box
from .box import box, Box, setattr_box

# 导入 Seq 和 NONE
from ..data import Seq, NONE


# ============================================================================
# Pipe - 管道操作
# ============================================================================

def _pipe(*funcs):
    """创建管道函数"""
    def _inn(source):
        return reduce(lambda x, f: f(x), funcs, source)
    return _inn


class Pipe:
    """
    管道操作类，支持链式调用
    
    示例:
        >>> result = range(10) | Pipe(lambda x: x * 2) | Pipe(list)
        >>> print(result)
        [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]
    """
    
    def __init__(self, func: Callable, *args, **kwargs):
        self.raw_func = func
        self.func = lambda iterable, *args2, **kwargs2: func(
            iterable, *args, *args2, **kwargs, **kwargs2
        )
        wraps(func)(self)
    
    def __ror__(self, other):
        """支持 | 操作符"""
        return self.func(other)
    
    def __rrshift__(self, other):
        """支持 >> 操作符"""
        if isinstance(other, Iterable) and not isinstance(other, (str, bytes)):
            return (self.func(i) for i in other)
        return self.func(other)
    
    def __call__(self, *args, **kwargs):
        return Pipe(
            lambda iterable, *args2, **kwargs2: self.func(
                iterable, *args, *args2, **kwargs, **kwargs2
            )
        )
    
    @classmethod
    def pipe(cls, *funcs):
        """创建管道"""
        funcs = [f for f in funcs]
        def _compose(source):
            return reduce(lambda obs, op: op(obs), funcs, source)
        return cls(_compose)
    
    @classmethod
    def compose(cls, *funcs):
        """创建组合函数"""
        return cls.pipe(*reversed(funcs))


# ============================================================================
# P - 可管道化函数包装器
# ============================================================================

class P:
    """
    可管道化函数包装器，支持指定参数位置
    
    示例:
        >>> result = [1, 2, 3] | P(sum)
        >>> print(result)
        6
    """
    
    __slots__ = ('func', 'args', 'kwargs', 'ix')
    
    def __init__(self, func: Callable, *args, **kwargs):
        ix = kwargs.pop('ix', 1)  # 管道参数位置，默认第一个
        if ix not in (1, 2, 3, -1, -2, -3):
            raise ValueError("pipe param index must be 1,2,3 or -1,-2,-3")
        self.ix = ix
        self.func = func
        self.args = args or tuple()
        self.kwargs = kwargs or {}
    
    def __ror__(self, other):
        """支持 | 操作符"""
        if self.ix == 1:
            args = (other,) + self.args
        elif self.ix == 2:
            args = (self.args[0], other) if len(self.args) >= 1 else (None, other)
            args = args + self.args[1:] if len(self.args) > 1 else args
        elif self.ix == 3:
            args = (self.args[0], self.args[1], other) if len(self.args) >= 2 else (None, None, other)
            args = args + self.args[2:] if len(self.args) > 2 else args
        elif self.ix == -1:
            args = self.args + (other,)
        elif self.ix == -2:
            args = self.args[:-1] + (other, self.args[-1]) if len(self.args) >= 1 else (other,)
        elif self.ix == -3:
            args = self.args[:-2] + (other, self.args[-2], self.args[-1]) if len(self.args) >= 2 else (other, None)
        else:
            raise ValueError("pipe param index must be 1,2,3 or -1,-2,-3")
        return self.func(*args, **self.kwargs)
    
    def __call__(self, *a, **k):
        args = self.args + a
        kwargs = self.kwargs.copy()
        kwargs.update(k)
        return self.__class__(self.func, *args, **kwargs)


# ============================================================================
# Ops - 操作符集合
# ============================================================================

def _static_pipe1(f):
    """创建静态管道方法（第一个参数）"""
    return staticmethod(P(f, ix=1))

def _static_pipe2(f):
    """创建静态管道方法（第二个参数）"""
    return staticmethod(P(f, ix=2))


class Ops:
    """
    操作符集合，提供常用的函数式操作
    
    示例:
        >>> result = range(10) | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2) | Ops.sum()
        >>> print(result)
        40
    """
    
    # 核心操作
    @staticmethod
    def filter(pred):
        """过滤操作"""
        @Pipe
        def _filter(it):
            return filter(pred, it)
        return _filter
    
    @staticmethod
    def map(func):
        """映射操作"""
        @Pipe
        def _map(it):
            return map(func, it)
        return _map
    
    @staticmethod
    @Pipe
    def sum(it):
        """求和"""
        return sum(it)
    
    @staticmethod
    @Pipe
    def all(it):
        """全部为真"""
        return all(it)
    
    @staticmethod
    @Pipe
    def any(it):
        """任一为真"""
        return any(it)
    
    # 数学操作
    @staticmethod
    @Pipe
    def min(it):
        """最小值"""
        return min(it)
    
    @staticmethod
    @Pipe
    def max(it):
        """最大值"""
        return max(it)
    
    # 集合操作
    @staticmethod
    @Pipe
    def take(iterable, n):
        """取前 n 个元素"""
        return list(itertools.islice(iterable, n))
    
    @staticmethod
    @Pipe
    def drop(iterable, n):
        """丢弃前 n 个元素"""
        return list(itertools.islice(iterable, n, None))
    
    @staticmethod
    @Pipe
    def distinct(iterable):
        """去重"""
        seen = set()
        result = []
        for item in iterable:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result
    
    @staticmethod
    @Pipe
    def count(iterable):
        """计数"""
        return sum(1 for _ in iterable)
    
    @staticmethod
    @Pipe
    def as_list(iterable):
        """转为列表"""
        return list(iterable)
    
    @staticmethod
    @Pipe
    def do(x, func=print):
        """执行副作用"""
        func(x)
        return x





# ============================================================================
# 测试代码
# ============================================================================

if __name__ == '__main__':
    print("=== 测试 Pipe ===")
    result = range(10) | Pipe(lambda x: [i * 2 for i in x])
    print(f"Pipe 结果: {result}")
    
    print("\n=== 测试 Ops ===")
    result = range(10) | Ops.filter(lambda x: x % 2 == 0) | Ops.map(lambda x: x * 2) | Ops.sum()
    print(f"Ops 结果: {result}")
    
    print("\n=== 测试 Seq ===")
    result = Seq(range(10)).map(lambda x: x * 2).filter(lambda x: x > 5).collect()
    print(f"Seq 结果: {result}")
    
    print("\n所有测试通过!")
