"""
vicList 列表类
继承自 Seq，提供更多列表处理方法
"""

import itertools
from collections import OrderedDict
from collections.abc import Iterable

from ..data import Seq
from ..decorators import rself
from ..functional.pipe_ops import P
from ..security import create_filter_func, create_map_func, ExpressionSecurityError


class ListLikeMeta(type):
    """列表类似元类，用于修改isinstance的行为"""
    def __instancecheck__(cls, instance):
        return isinstance(instance, (list, cls))


@rself
class vicList(Seq, metaclass=ListLikeMeta):
    """列表类，继承自Seq，提供更多列表处理方法"""

    def __init__(self, *origins):
        self._data = []
        if origins:
            if len(origins) == 1:
                origin = origins[0]
                if hasattr(origin, '__iter__') and not isinstance(origin, (str, bytes, bytearray)):
                    self._data = list(origin)
                else:
                    self._data = [origin]
            else:
                self._data = list(origins)
        super().__init__(self._data)

    def do(self, f=print, pre_f=None, sub_f=None):
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return vicList(self._data[index])
        return self._data[index]

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __and__(self, other):
        return vicList(set(self._data) & set(other))

    def __or__(self, other):
        """支持管道操作 lst | P(func) 或集合操作"""
        if isinstance(other, P):
            return other.__ror__(self)
        return vicList(set(self._data) | set(other))

    def __sub__(self, other):
        return vicList(set(self._data) - set(other))

    def __xor__(self, other):
        return vicList(set(self._data) ^ set(other))

    def __eq__(self, other):
        """支持列表相等比较"""
        if isinstance(other, vicList):
            return self._data == other._data
        elif isinstance(other, (list, tuple)):
            return self._data == list(other)
        return False

    def __ne__(self, other):
        """支持列表不等比较"""
        return not self.__eq__(other)

    def __rshift__(self, other):
        """支持管道操作 lst >> P(func)"""
        if isinstance(other, P):
            return other.__ror__(self)
        raise TypeError(f"管道操作的右侧必须是 P 实例，当前类型: {type(other).__name__}")

    def __repr__(self):
        return f"vicList({self._data!r})"

    def __call__(self, func=print, *args, **kwargs):
        return func(self, *args, **kwargs)

    def islice(self, start=None, stop=None, step=1):
        if start is None:
            start = 0
        if stop is None:
            stop = len(self)

        start = max(0, start) if start >= 0 else max(len(self) + start, 0)
        stop = min(len(self), stop) if stop >= 0 else min(len(self) + stop, len(self))

        sliced = []
        i = start
        while (i < stop if step > 0 else i > stop) and 0 <= i < len(self):
            sliced.append(self[i])
            i += step
        return vicList(sliced)

    @property
    def unique(self):
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList(OrderedDict.fromkeys(self._data).keys())

    def _run(self, func=print):
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return [func(s) for s in self._data]
        elif isinstance(func, str):
            safe_func = create_map_func(func)
            return [safe_func(s) for s in self._data]
        else:
            return []

    def _run_filter(self, func=bool):
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return [s for s in self._data if func(s)]
        elif isinstance(func, str):
            safe_func = create_filter_func(func)
            return [s for s in self._data if safe_func(s)]
        else:
            return []

    def foreach(self, func=print, filter_func=None, filter_first=True):
        if filter_func is None:
            if func is None:
                return self
            return self.map(func)
        if func is None:
            return self.filter(filter_func)

        if filter_first:
            return self.filter(filter_func).map(func)

        return self.map(func).filter(filter_func)

    def filterfalse(self, func=bool):
        if isinstance(func, str):
            func = create_filter_func(func)
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList([i for i in self._data if not func(i)])

    def filter(self, func=bool):
        temp = self._run_filter(func)
        return vicList(temp) if isinstance(temp, Iterable) else temp

    def map(self, func=None):
        if func is None:
            self._run(print)
            return
        temp = self._run(func)
        return vicList(temp) if isinstance(temp, Iterable) else temp

    def _run_ex(self, func=print, symbols="x"):
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return list(itertools.starmap(func, self._data))
        elif isinstance(func, str):
            from ..security import safe_compile_expression
            safe_func = safe_compile_expression(func, tuple(symbols))
            return list(itertools.starmap(safe_func, self._data))
        else:
            return []

    @property
    def inner_iterable(self):
        l = len(self)
        if l == 0:
            return False
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return isinstance(self._data[0], Iterable) and not isinstance(self._data[0], (str, bytes, bytearray))

    @property
    def is_empty(self):
        return len(self) == 0

    @property
    def size(self):
        return len(self)

    def sizeEx(self, func=None):
        if func is None:
            return self.size
        return self.quantify(func)

    def show(self, func=None):
        if func is None:
            print(self)
            return
        if callable(func):
            func(self)
        else:
            safe_func = create_map_func(func)
            safe_func(self)

    def starmap(self, func, symbols=None):
        if self.is_empty:
            return []
        if not self.inner_iterable:
            raise TypeError("first item is not a iterbale !!!")
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if symbols is None:
            l = len(self._data[0])
            i = ord('x') if l <= 3 else ord('a')
            symbols = [chr(i + j) for j in range(l)]
        return self._run_ex(func, symbols)

    def _run2(self, func=print):
        if callable(func):
            return func(self)
        elif isinstance(func, str):
            safe_func = create_map_func(func)
            return safe_func(self)
        else:
            return []

    def run(self, func=print):
        return self._run2(func)

    def enumerate(self, n=0):
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList(enumerate(self._data, n))

    def take(self, n, action=False):
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if action:
            return self._data[:n]
        return vicList(self._data[:n])

    def prepend(self, value):
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList([value] + self._data)

    def tail(self, n):
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList(self._data[-n:])

    def any_equal(self, pred=bool):
        pred = bool if pred is None else pred
        if callable(pred):
            p = pred is bool
        elif isinstance(pred, str):
            p = pred == 'bool'
            if not pred:
                raise ValueError("pred must not empty ,is a bool function ")
            pred = create_filter_func(pred)
        else:
            raise TypeError("pred must is a bool function,or a bool function that express by string")

        temp = self.map(pred) if p else self.map(pred).map(bool)

        for i in temp:
            if i:
                return True
        else:
            return False

    def all_equal(self, pred=bool):
        pred = bool if pred is None else pred
        if callable(pred):
            p = pred is bool
        elif isinstance(pred, str):
            p = pred == 'bool'
            if not pred:
                raise ValueError("pred must not empty ,is a bool function ")
            pred = create_filter_func(pred)
        else:
            raise TypeError("pred must is a bool function,or a bool function that express by string")

        temp = self.map(pred) if p else self.map(pred).map(bool)

        g = itertools.groupby(temp)
        return next(g, True) and not next(g, False)

    def quantify(self, pred=bool, quan=sum):
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if isinstance(pred, str):
            pred = create_filter_func(pred)
        return quan(1 for item in self._data if pred(item))

    @classmethod
    def __subclasscheck__(cls, subclass):
        return issubclass(subclass, list) or super().__subclasscheck__(subclass)

    def __class_getitem__(cls, item):
        return list[item]