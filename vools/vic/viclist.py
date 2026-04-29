"""
vicList 列表类
继承自 Seq，提供更多列表处理方法
"""

import itertools
from collections import OrderedDict
from collections.abc import Iterable

from ..data import Seq
from ..vic.victools import vicTools


class ListLikeMeta(type):
    """列表类似元类，用于修改isinstance的行为"""
    def __instancecheck__(cls, instance):
        """检查实例是否为列表或列表类似对象

        Args:
            instance: 要检查的实例

        Returns:
            是否为列表或列表类似对象
        """
        return isinstance(instance, (list, cls))


class vicList(Seq, metaclass=ListLikeMeta):
    """列表类，继承自Seq，提供更多列表处理方法"""

    def __init__(self, *origins):
        """初始化vicList对象

        Args:
            *origins: 初始化参数
        """
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

    def __getitem__(self, index):
        """获取索引或切片

        Args:
            index: 索引或切片

        Returns:
            对应的元素或切片后的vicList对象
        """
        if isinstance(index, slice):
            return vicList(self._data[index])
        return self._data[index]

    def __len__(self):
        """获取长度

        Returns:
            列表长度
        """
        return len(self._data)

    def __iter__(self):
        """迭代列表

        Returns:
            迭代器
        """
        return iter(self._data)

    def __and__(self, other):
        """交集操作

        Args:
            other: 另一个列表

        Returns:
            交集后的vicList对象
        """
        return vicList(set(self._data) & set(other))

    def __or__(self, other):
        """并集操作

        Args:
            other: 另一个列表

        Returns:
            并集后的vicList对象
        """
        return vicList(set(self._data) | set(other))

    def __sub__(self, other):
        """差集操作

        Args:
            other: 另一个列表

        Returns:
            差集后的vicList对象
        """
        return vicList(set(self._data) - set(other))

    def __xor__(self, other):
        """对称差集操作

        Args:
            other: 另一个列表

        Returns:
            对称差集后的vicList对象
        """
        return vicList(set(self._data) ^ set(other))

    def __repr__(self):
        """repr表示

        Returns:
            表示字符串
        """
        return f"vicList({self._data!r})"

    @vicTools.transfer
    def __call__(self, func=print, *args, **kwargs):
        """调用列表

        Args:
            func: 调用函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            调用结果
        """
        return func(self, *args, **kwargs)

    def islice(self, start=None, stop=None, step=1):
        """自定义切片方法

        Args:
            start: 开始索引
            stop: 结束索引
            step: 步长

        Returns:
            切片后的vicList对象
        """
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
        """获取唯一元素

        Returns:
            唯一元素的vicList对象
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList(OrderedDict.fromkeys(self._data).keys())

    def _run(self, func=print):
        """运行函数

        Args:
            func: 运行函数

        Returns:
            运行结果列表
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return [func(s) for s in self._data]
        elif isinstance(func, str):
            return [eval(func)(s) for s in self._data]
        else:
            return []

    def _run_filter(self, func=bool):
        """运行过滤函数

        Args:
            func: 过滤函数

        Returns:
            过滤后的结果列表
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return [s for s in self._data if func(s)]
        elif isinstance(func, str):
            return [s for s in self._data if eval(func)(s)]
        else:
            return []

    def foreach(self, func=print, filter_func=None, filter_first=True):
        """遍历列表

        Args:
            func: 遍历函数
            filter_func: 过滤函数
            filter_first: 是否先过滤

        Returns:
            处理后的vicList对象
        """
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
        """过滤不符合条件的元素

        Args:
            func: 过滤函数

        Returns:
            过滤后的vicList对象
        """
        if isinstance(func, str):
            func = eval(func)
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList([i for i in self._data if not func(i)])

    @vicTools.transfer
    def filter(self, func=bool):
        """过滤符合条件的元素

        Args:
            func: 过滤函数

        Returns:
            过滤后的结果
        """
        temp = self._run_filter(func)
        return vicList(temp) if isinstance(temp, Iterable) else temp

    @vicTools.transfer
    def map(self, func=None):
        """映射函数

        Args:
            func: 映射函数

        Returns:
            映射后的结果
        """
        if func is None:
            self._run(print)
            return self
        temp = self._run(func)
        return vicList(temp) if isinstance(temp, Iterable) else temp

    def _run_ex(self, func=print, symbols="x"):
        """运行函数（扩展版）

        Args:
            func: 运行函数
            symbols: 参数符号

        Returns:
            运行结果列表
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return list(itertools.starmap(func, self._data))
        elif isinstance(func, str):
            return list(itertools.starmap(eval(func), self._data))
        else:
            return []

    @property
    def inner_iterable(self):
        """检查内部元素是否可迭代

        Returns:
            内部元素是否可迭代
        """
        l = len(self)
        if l == 0:
            return False
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return isinstance(self._data[0], Iterable) and not isinstance(self._data[0], (str, bytes, bytearray))

    @property
    def is_empty(self):
        """检查列表是否为空

        Returns:
            列表是否为空
        """
        return len(self) == 0

    @property
    def size(self):
        """获取列表大小

        Returns:
            列表大小
        """
        return len(self)

    def sizeEx(self, func=None):
        """获取符合条件的元素数量

        Args:
            func: 过滤函数

        Returns:
            符合条件的元素数量
        """
        if func is None:
            return self.size
        return self.quantify(func)

    def show(self, func=None):
        """显示列表

        Args:
            func: 显示函数

        Returns:
            self
        """
        if func is None:
            print(self)
            return self
        if callable(func):
            func(self)
        else:
            eval(func)(self)
        return self

    @vicTools.transfer
    def starmap(self, func, symbols=None):
        """星映射函数

        Args:
            func: 映射函数
            symbols: 参数符号

        Returns:
            映射后的结果
        """
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
        """运行函数（针对整个列表）

        Args:
            func: 运行函数

        Returns:
            运行结果
        """
        if callable(func):
            return func(self)
        elif isinstance(func, str):
            return eval(func)(self)
        else:
            return []

    @vicTools.transfer
    def run(self, func=print):
        """运行函数

        Args:
            func: 运行函数

        Returns:
            运行结果
        """
        temp = self._run2(func)
        return temp

    def enumerate(self, n=0):
        """枚举列表

        Args:
            n: 起始索引

        Returns:
            枚举后的vicList对象
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList(enumerate(self._data, n))

    def take(self, n, action=False):
        """获取前n个元素

        Args:
            n: 元素数量
            action: 是否直接返回列表

        Returns:
            前n个元素的vicList对象或列表
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if action:
            return self._data[:n]
        return vicList(self._data[:n])

    def prepend(self, value):
        """在列表前添加元素

        Args:
            value: 要添加的元素

        Returns:
            添加后的vicList对象
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList([value] + self._data)

    def tail(self, n):
        """获取后n个元素

        Args:
            n: 元素数量

        Returns:
            后n个元素的vicList对象
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return vicList(self._data[-n:])

    def any_equal(self, pred=bool):
        """检查是否有元素满足条件

        Args:
            pred: 条件函数

        Returns:
            是否有元素满足条件
        """
        pred = bool if pred is None else pred
        if callable(pred):
            p = pred is bool
        elif isinstance(pred, str):
            p = pred == 'bool'
            if not pred:
                raise ValueError("pred must not empty ,is a bool function ")
            pred = eval(pred)
        else:
            raise TypeError("pred must is a bool function,or a bool function that express by string")

        temp = self.map(pred) if p else self.map(pred).map(bool)

        for i in temp:
            if i:
                return True
        else:
            return False

    def all_equal(self, pred=bool):
        """检查是否所有元素都满足条件

        Args:
            pred: 条件函数

        Returns:
            是否所有元素都满足条件
        """
        pred = bool if pred is None else pred
        if callable(pred):
            p = pred is bool
        elif isinstance(pred, str):
            p = pred == 'bool'
            if not pred:
                raise ValueError("pred must not empty ,is a bool function ")
            pred = eval(pred)
        else:
            raise TypeError("pred must is a bool function,or a bool function that express by string")

        temp = self.map(pred) if p else self.map(pred).map(bool)

        g = itertools.groupby(temp)
        return next(g, True) and not next(g, False)

    def quantify(self, pred=bool, quan=sum):
        """计算满足条件的元素数量

        Args:
            pred: 条件函数
            quan: 聚合函数

        Returns:
            满足条件的元素数量
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if isinstance(pred, str):
            pred = eval(pred)
        return quan(1 for item in self._data if pred(item))

    @classmethod
    def __subclasscheck__(cls, subclass):
        """检查子类

        Args:
            subclass: 子类

        Returns:
            是否为子类
        """
        return issubclass(subclass, list) or super().__subclasscheck__(subclass)

    def __class_getitem__(cls, item):
        """类索引操作

        Args:
            item: 索引

        Returns:
            列表类型
        """
        return list[item]