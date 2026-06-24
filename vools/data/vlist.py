"""
VList 列表类
继承自 Seq，提供链式列表处理方法
"""

__all__ = ['ListLikeMeta', 'VList']

import itertools
from collections import OrderedDict
from collections.abc import Iterable
from typing import TypeVar, Generic, Callable, List, Optional, Any, Union, Iterable as IterType, Iterator, Dict, Tuple, Type

from .seq import Seq
from ..decorators import rself
from ..functional.pipe_ops import P
from ..security import create_filter_func, create_map_func, ExpressionSecurityError
from ..serialize.context import get_protocol

T = TypeVar('T')
R = TypeVar('R')
K = TypeVar('K')


class ListLikeMeta(type):
    """列表类似元类，使 isinstance(x, VList) 对普通 list 也返回 True。

    通过自定义 __instancecheck__ 方法，使得任何 list 实例同时也被认为是 VList 的实例。
    这允许 VList 的方法直接工作在普通列表上。
    """
    def __instancecheck__(cls, instance):
        return isinstance(instance, (list, cls))
    
    def do(self: type, f: Callable[..., Any] = print, pre_f: Optional[Callable[[Any], Any]] = None, sub_f: Optional[Callable[[Any], None]] = None) -> type:
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



@rself
class VList(Seq, metaclass=ListLikeMeta):
    """链式列表类，继承自 Seq，提供丰富的列表处理方法"""

    def __init__(self, *origins: Any) -> None:
        """初始化 VList。

        Args:
            *origins: 初始元素，支持单个可迭代对象或多个独立元素
        """
        self._data: List[Any] = []
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

    def do(self, f: Callable[..., Any] = print, pre_f: Optional[Callable[[Any], Any]] = None, sub_f: Optional[Callable[[Any], None]] = None) -> 'VList':
        """执行副作用操作，返回自身以支持链式调用。

        Args:
            f: 要执行的函数（默认 print）
            pre_f: 在 f 执行前执行的预处理函数
            sub_f: 在 f 执行后执行的后处理函数（无返回值要求）

        Returns:
            self，自身引用以支持链式调用
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self

    def __getitem__(self, index: Union[int, slice]) -> Union[Any, 'VList']:
        """支持整数索引和切片访问。

        Args:
            index: 整数索引或切片对象

        Returns:
            整数索引返回元素，切片返回新的 VList
        """
        if isinstance(index, slice):
            return VList(self._data[index])
        return self._data[index]

    def __len__(self) -> int:
        """返回列表长度。

        Returns:
            列表中元素的数量
        """
        return len(self._data)

    def __iter__(self) -> Iterator[Any]:
        """返回列表的迭代器。

        Returns:
            列表元素的迭代器
        """
        return iter(self._data)

    def __and__(self, other: Any) -> 'VList':
        """集合交集运算（& 运算符）。

        Args:
            other: 另一个可迭代对象

        Returns:
            两个集合的交集组成的 VList
        """
        return VList(set(self._data) & set(other))

    def __or__(self, other: Any) -> 'VList':
        """支持管道操作 lst | P(func) 或集合操作。

        Args:
            other: P 实例或其他可迭代对象

        Returns:
            P 管道操作的结果，或两个集合的并集组成的 VList
        """
        if isinstance(other, P):
            return other.__ror__(self)
        return VList(set(self._data) | set(other))

    def __rand__(self, other: Any) -> 'VList':
        """反向集合交集运算。

        Args:
            other: 另一个可迭代对象

        Returns:
            两个集合的交集组成的 VList
        """
        return VList(set(other) & set(self._data))

    def __ror__(self, other: Any) -> 'VList':
        """反向管道操作或集合并集运算。

        Args:
            other: P 实例或其他可迭代对象

        Returns:
            P 管道操作的结果，或两个集合的并集组成的 VList
        """
        if isinstance(other, P):
            return other.__ror__(self)
        return VList(set(other) | set(self._data))

    def __sub__(self, other: Any) -> 'VList':
        """集合差集运算（- 运算符）。

        Args:
            other: 另一个可迭代对象

        Returns:
            两个集合的差集组成的 VList
        """
        return VList(set(self._data) - set(other))

    def __xor__(self, other: Any) -> 'VList':
        """集合对称差集运算（^ 运算符）。

        Args:
            other: 另一个可迭代对象

        Returns:
            两个集合的对称差集组成的 VList
        """
        return VList(set(self._data) ^ set(other))

    def __eq__(self, other: Any) -> bool:
        """相等比较运算。

        Args:
            other: 另一个对象

        Returns:
            如果相等返回 True，否则返回 False
        """
        if isinstance(other, VList):
            return self._data == other._data
        elif isinstance(other, (list, tuple)):
            return self._data == list(other)
        return False

    def __ne__(self, other: Any) -> bool:
        """不相等比较运算。

        Args:
            other: 另一个对象

        Returns:
            如果不相等返回 True，否则返回 False
        """
        return not self.__eq__(other)

    def __rshift__(self, other: Any) -> Any:
        """支持管道操作 lst >> P(func)。

        Args:
            other: P 实例

        Returns:
            P 管道操作的结果

        Raises:
            TypeError: 当 other 不是 P 实例时抛出
        """
        if isinstance(other, P):
            return other.__ror__(self)
        raise TypeError(f"管道操作的右侧必须是 P 实例，当前类型: {type(other).__name__}")

    def __repr__(self) -> str:
        """返回 VList 的字符串表示。

        Returns:
            VList 的官方字符串表示
        """
        return f"VList({self._data!r})"

    def __call__(self, func: Callable[..., Any] = print, *args: Any, **kwargs: Any) -> Any:
        """将列表作为参数传递给函数。

        Args:
            func: 要调用的函数（默认 print）
            *args: 传递给函数的位置参数
            **kwargs: 传递给函数的关键字参数

        Returns:
            函数调用的结果
        """
        return func(self, *args, **kwargs)

    def islice(self, start: Optional[int] = None, stop: Optional[int] = None, step: int = 1) -> 'VList':
        """切片操作，返回指定范围的元素。

        Args:
            start: 起始索引（默认为 0）
            stop: 结束索引（默认为列表长度）
            step: 步长（默认为 1）

        Returns:
            切片后的 VList
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
        return VList(sliced)

    @property
    def unique(self) -> 'VList':
        """返回去重后的 VList，保持元素顺序。

        Returns:
            去重后的新 VList
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return VList(OrderedDict.fromkeys(self._data).keys())

    def _run(self, func: Union[Callable[[Any], Any], str] = print) -> List[Any]:
        """内部方法：运行映射函数。

        Args:
            func: 映射函数或表达式字符串

        Returns:
            映射结果列表
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return [func(s) for s in self._data]
        elif isinstance(func, str):
            safe_func = create_map_func(func)
            return [safe_func(s) for s in self._data]
        else:
            return []

    def _run_filter(self, func: Union[Callable[[Any], bool], str] = bool) -> List[Any]:
        """内部方法：运行过滤函数。

        Args:
            func: 过滤函数或表达式字符串

        Returns:
            过滤结果列表
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if callable(func):
            return [s for s in self._data if func(s)]
        elif isinstance(func, str):
            safe_func = create_filter_func(func)
            return [s for s in self._data if safe_func(s)]
        else:
            return []

    def foreach(self, func: Callable[[Any], Any] = print, filter_func: Optional[Union[Callable[[Any], bool], str]] = None, filter_first: bool = True) -> Optional['VList']:
        """遍历并应用函数，可选先过滤。

        Args:
            func: 要应用的函数（默认 print）
            filter_func: 可选的过滤函数
            filter_first: 是否先过滤再应用函数（默认 True）

        Returns:
            处理后的 VList 或 None
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

    def filterfalse(self, func: Union[Callable[[Any], bool], str] = bool) -> 'VList':
        """返回不满足条件的元素（与 filter 相反）。

        Args:
            func: 过滤函数或表达式字符串

        Returns:
            不满足条件的元素组成的 VList
        """
        if isinstance(func, str):
            func = create_filter_func(func)
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return VList([i for i in self._data if not func(i)])

    def filter(self, func: Union[Callable[[Any], bool], str] = bool) -> 'VList':
        """LINQ 风格的过滤操作。

        Args:
            func: 过滤函数或表达式字符串

        Returns:
            满足条件的元素组成的 VList
        """
        temp = self._run_filter(func)
        return VList(temp) if isinstance(temp, Iterable) else temp

    def where(self, func: Union[Callable[[Any], bool], str]) -> 'VList':
        """LINQ 风格的过滤操作（filter 的别名）。

        Args:
            func: 过滤函数或表达式字符串

        Returns:
            满足条件的元素组成的 VList
        """
        return self.filter(func)

    def wherenot(self, func: Union[Callable[[Any], bool], str]) -> 'VList':
        """LINQ 风格的反向过滤操作。

        Args:
            func: 过滤函数或表达式字符串

        Returns:
            不满足条件的元素组成的 VList
        """
        return self.filterfalse(func)

    def select(self, func: Union[Callable[[Any], Any], str]) -> 'VList':
        """LINQ 风格的映射操作（map 的别名）。

        Args:
            func: 映射函数或表达式字符串

        Returns:
            映射后的元素组成的 VList
        """
        return self.map(func)

    def map(self, func: Optional[Union[Callable[[Any], Any], str]] = None) -> Optional['VList']:
        """LINQ 风格的映射操作。

        Args:
            func: 映射函数或表达式字符串，为 None 时打印列表

        Returns:
            映射后的 VList 或 None（当 func 为 None 时）
        """
        if func is None:
            self._run(print)
            return None
        temp = self._run(func)
        return VList(temp) if isinstance(temp, Iterable) else temp

    def flat_map(self, func: Union[Callable[[Any], IterType[Any]], str]) -> 'VList':
        """扁平化映射操作，将每个元素映射为一个可迭代对象并合并。

        Args:
            func: 映射函数，返回可迭代对象

        Returns:
            扁平化后的 VList
        """
        if isinstance(func, str):
            safe_func = create_map_func(func)
            result = []
            for item in self._data:
                mapped = safe_func(item)
                if hasattr(mapped, '__iter__') and not isinstance(mapped, (str, bytes, bytearray)):
                    result.extend(mapped)
                else:
                    result.append(mapped)
            return VList(result)
        else:
            result = []
            for item in self._data:
                mapped = func(item)
                if hasattr(mapped, '__iter__') and not isinstance(mapped, (str, bytes, bytearray)):
                    result.extend(mapped)
                else:
                    result.append(mapped)
            return VList(result)

    def flatmap(self, func: Union[Callable[[Any], IterType[Any]], str]) -> 'VList':
        """flat_map 的别名。

        Args:
            func: 映射函数，返回可迭代对象

        Returns:
            扁平化后的 VList
        """
        return self.flat_map(func)

    def distinct(self) -> 'VList':
        """返回去重后的列表（unique 的别名）。

        Returns:
            去重后的 VList
        """
        return self.unique

    def group_by(self, key_func: Union[Callable[[Any], K], str]) -> Dict[K, 'VList']:
        """根据键函数对元素进行分组。

        Args:
            key_func: 键提取函数或表达式字符串

        Returns:
            键到 VList 分组的字典
        """
        if isinstance(key_func, str):
            safe_func = create_map_func(key_func)
            key_func = safe_func
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        groups: Dict[K, List[Any]] = {}
        for item in self._data:
            key = key_func(item)
            if key not in groups:
                groups[key] = []
            groups[key].append(item)
        return {k: VList(v) for k, v in groups.items()}

    def sort_by(self, key_func: Optional[Union[Callable[[Any], Any], str]] = None, reverse: bool = False) -> 'VList':
        """返回排序后的列表（不修改原列表）。

        Args:
            key_func: 排序键函数或表达式字符串
            reverse: 是否降序排列

        Returns:
            排序后的新 VList
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if key_func is None:
            return VList(sorted(self._data, reverse=reverse))
        if isinstance(key_func, str):
            safe_func = create_map_func(key_func)
            return VList(sorted(self._data, key=safe_func, reverse=reverse))
        return VList(sorted(self._data, key=key_func, reverse=reverse))

    def reverse(self) -> 'VList':
        """反转列表中的元素（就地反转）。

        Returns:
            反转后的自身引用
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        self._data = self._data[::-1]
        return self

    def sorted(self, key_func: Optional[Union[Callable[[Any], Any], str]] = None, reverse: bool = False) -> 'VList':
        """返回排序后的列表（不修改原列表，sort_by 的别名）。

        Args:
            key_func: 排序键函数或表达式字符串
            reverse: 是否降序排列

        Returns:
            排序后的新 VList
        """
        return self.sort_by(key_func, reverse)

    def count_by(self, key_func: Union[Callable[[Any], K], str]) -> Dict[K, int]:
        """根据键函数对元素进行分组计数。

        Args:
            key_func: 键提取函数或表达式字符串

        Returns:
            键到计数的字典
        """
        if isinstance(key_func, str):
            safe_func = create_map_func(key_func)
            key_func = safe_func
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        counts: Dict[K, int] = {}
        for item in self._data:
            key = key_func(item)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def reduce_by(self, key_func: Union[Callable[[Any], K], str], reduce_func: Callable[[Any, Any], R]) -> Dict[K, R]:
        """根据键函数分组并对每组应用聚合函数。

        Args:
            key_func: 键提取函数或表达式字符串
            reduce_func: 聚合函数，接收一个累加器和一个当前元素

        Returns:
            键到聚合结果的字典
        """
        if isinstance(key_func, str):
            safe_func = create_map_func(key_func)
            key_func = safe_func
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        groups: Dict[K, List[Any]] = {}
        for item in self._data:
            key = key_func(item)
            if key not in groups:
                groups[key] = []
            groups[key].append(item)
        result: Dict[K, R] = {}
        for key, items in groups.items():
            accumulator = items[0]
            for item in items[1:]:
                accumulator = reduce_func(accumulator, item)
            result[key] = accumulator
        return result

    def collect(self) -> List[Any]:
        """物化为普通列表。

        Returns:
            列表元素的普通列表
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return list(self._data)

    def add(self, item: Any) -> 'VList':
        """添加单个元素到列表末尾。

        Args:
            item: 要添加的元素

        Returns:
            添加元素后的 VList
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        self._data.append(item)
        return self

    def push(self, item: Any) -> 'VList':
        """在列表末尾添加元素（add 的别名）。

        Args:
            item: 要添加的元素

        Returns:
            添加元素后的 VList
        """
        return self.add(item)

    def pop(self) -> Any:
        """弹出并返回列表末尾的元素。

        Returns:
            弹出的元素，如果列表为空则返回 None
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if not self._data:
            return None
        return self._data.pop()

    def shift(self) -> Any:
        """弹出并返回列表第一个元素。

        Returns:
            弹出的元素，如果列表为空则返回 None
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if not self._data:
            return None
        return self._data.pop(0)

    def unshift(self, item: Any) -> 'VList':
        """在列表开头插入元素。

        Args:
            item: 要插入的元素

        Returns:
            插入元素后的 VList
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        self._data.insert(0, item)
        return self

    def _run_ex(self, func: Union[Callable[..., Any], str] = print, symbols: str = "x") -> List[Any]:
        """内部方法：运行带星号的映射函数（用于 starmap）。

        Args:
            func: 映射函数或表达式字符串
            symbols: 表达式中使用的变量名

        Returns:
            映射结果列表
        """
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
    def inner_iterable(self) -> bool:
        """判断列表的第一个元素是否也是可迭代对象。

        Returns:
            如果第一个元素是可迭代对象（但不是字符串/字节）返回 True
        """
        l = len(self)
        if l == 0:
            return False
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return isinstance(self._data[0], Iterable) and not isinstance(self._data[0], (str, bytes, bytearray))

    @property
    def is_empty(self) -> bool:
        """判断列表是否为空。

        Returns:
            如果列表为空返回 True
        """
        return len(self) == 0

    @property
    def size(self) -> int:
        """返回列表长度。

        Returns:
            列表中元素的数量
        """
        return len(self)

    def sizeEx(self, func: Optional[Union[Callable[[Any], bool], str]] = None) -> int:
        """返回满足条件的元素数量。

        Args:
            func: 可选的计数条件函数

        Returns:
            满足条件的元素数量，或总长度
        """
        if func is None:
            return self.size
        return self.quantify(func)

    def show(self, func: Optional[Union[Callable[[Any], Any], str]] = None) -> None:
        """打印列表或应用自定义函数。

        Args:
            func: 可选的自定义函数
        """
        if func is None:
            print(self)
            return
        if callable(func):
            func(self)
        else:
            safe_func = create_map_func(func)
            safe_func(self)

    def starmap(self, func: Union[Callable[..., Any], str], symbols: Optional[List[str]] = None) -> List[Any]:
        """使用星号映射应用函数（每个元素的各项作为独立参数）。

        Args:
            func: 要应用的函数或表达式字符串
            symbols: 表达式中使用的变量名列表

        Returns:
            映射结果列表
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

    def _run2(self, func: Union[Callable[[Any], Any], str] = print) -> Any:
        """内部方法：运行函数（整个列表作为参数）。

        Args:
            func: 函数或表达式字符串

        Returns:
            函数调用结果
        """
        if callable(func):
            return func(self)
        elif isinstance(func, str):
            safe_func = create_map_func(func)
            return safe_func(self)
        else:
            return []

    def run(self, func: Union[Callable[[Any], Any], str] = print) -> Any:
        """运行函数（整个列表作为参数）。

        Args:
            func: 函数或表达式字符串

        Returns:
            函数调用结果
        """
        return self._run2(func)

    def enumerate(self, n: int = 0) -> 'VList':
        """返回带索引的枚举对象。

        Args:
            n: 起始索引（默认 0）

        Returns:
            (索引, 元素) 元组组成的 VList
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return VList(enumerate(self._data, n))

    def take(self, n: int, action: bool = False) -> Union['VList', List[Any]]:
        """返回前 n 个元素。

        Args:
            n: 要获取的元素数量
            action: 为 True 时返回普通列表

        Returns:
            前 n 个元素组成的 VList 或普通列表
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if action:
            return self._data[:n]
        return VList(self._data[:n])

    def prepend(self, value: Any) -> 'VList':
        """在列表开头插入元素。

        Args:
            value: 要插入的值

        Returns:
            插入后的新 VList
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return VList([value] + self._data)

    def tail(self, n: int) -> 'VList':
        """返回后 n 个元素。

        Args:
            n: 要获取的元素数量

        Returns:
            后 n 个元素组成的 VList
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        return VList(self._data[-n:])

    def any_equal(self, pred: Union[Callable[[Any], bool], str, None] = None) -> bool:
        """检查是否存在满足条件的元素。

        Args:
            pred: 谓词函数或表达式字符串

        Returns:
            如果存在满足条件的元素返回 True
        """
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

    def all_equal(self, pred: Union[Callable[[Any], bool], str, None] = None) -> bool:
        """检查是否所有元素都满足条件。

        Args:
            pred: 谓词函数或表达式字符串

        Returns:
            如果所有元素都满足条件返回 True
        """
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

    def quantify(self, pred: Union[Callable[[Any], bool], str] = bool, quan: Callable[[IterType[int]], int] = sum) -> int:
        """统计满足条件的元素数量。

        Args:
            pred: 谓词函数或表达式字符串
            quan: 聚合函数（默认 sum）

        Returns:
            满足条件的元素数量
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if isinstance(pred, str):
            pred = create_filter_func(pred)
        return quan(1 for item in self._data if pred(item))

    @classmethod
    def __subclasscheck__(cls, subclass: type) -> bool:
        """检查子类关系。

        Args:
            subclass: 要检查的类型

        Returns:
            如果 subclass 是 list 或 cls 的子类返回 True
        """
        return issubclass(subclass, list) or super().__subclasscheck__(subclass)

    def __class_getitem__(cls, item: Any) -> Any:
        """支持类型注解语法 List[T]。

        Args:
            item: 类型参数

        Returns:
            列表类型
        """
        return List[item]

    # ─── 序列化支持 ───

    def __getstate__(self) -> Dict[str, List[Any]]:
        """获取序列化状态。

        Returns:
            包含 _data 的字典
        """
        return {'_data': getattr(self, '_data', [])}

    def __setstate__(self, state: Dict[str, List[Any]]) -> None:
        """设置序列化状态。

        Args:
            state: 包含 _data 的字典
        """
        self._data = state.get('_data', [])
        from .seq import Seq
        Seq.__init__(self, self._data)
