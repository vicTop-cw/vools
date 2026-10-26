"""
VList 列表类
继承自 Seq，提供链式列表处理方法
"""

__all__ = ['ListLikeMeta', 'VList']

import itertools
import operator
from collections import OrderedDict, deque
from collections.abc import Iterable
from typing import TypeVar, Generic, Callable, List, Optional, Any, Union, Iterable as IterType, Iterator, Dict, Tuple, Type

from .seq import Seq
from ..decorators import rself
from ..functional.pipe_ops import P
from ..security import create_filter_func, create_map_func, safe_compile_expression, ExpressionSecurityError
from ..serialize.context import get_protocol
from ..core.base import VoolsBase

T = TypeVar('T')
R = TypeVar('R')
K = TypeVar('K')


class ListLikeMeta(type):
    """列表类似元类，使 isinstance(x, VList) 对普通 list 也返回 True。

    通过自定义 __instancecheck__ 方法，使得任何 list 实例同时也被认为是 VList 的实例。
    这允许 VList 的方法直接工作在普通列表上。
    """
    def __instancecheck__(cls, instance):
        # 注意：这里不能写 isinstance(instance, (list, cls)) —— 元组里含 cls 会
        # 再次触发本方法，构成无限递归（VList.size() 这类返回非 list 的方法经
        # @rself 包装后一律 RecursionError）。先做无递归的内建 list 检查，
        # 再退回 type 的默认 MRO 检查。
        if isinstance(instance, list):
            return True
        return type.__instancecheck__(cls, instance)
    
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
class VList(Seq, VoolsBase, metaclass=ListLikeMeta):
    """链式列表类，继承自 Seq，提供丰富的列表处理方法"""

    # BUG-221: pop/shift 的 docstring 明写「列表为空则返回 None」，但 @rself
    # 的链式兜底把方法返回值 None 转成 self——VList([]).pop() 返回整条空列表
    # 本身，`is None` 空弹判断永假，调用方把空列表当弹出的元素消费。
    # 走 _rself_exclude 官方逃生门（先例：VDate._rself_exclude={'date'}
    # BUG-200、VText=('regexp_substr',) BUG-220），弹出语义对齐内置 list：
    # 空列表返回 None、非空返回原始元素。
    # BUG-314: map(func=None) 文档承诺返回 None（打印模式），不能被兜底成 self。
    _rself_exclude = ('pop', 'shift', 'map')

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

    def copy(self):        # noqa: D401 - 覆写 VoolsBase.copy
        """返回**互不影响**的 VList 副本（BUG-505 覆写 VoolsBase.copy）。

        ``VoolsBase.copy`` 的 ``copy.copy(self)`` 会让副本与原件共享同一个
        ``_data`` 列表（实测 ``u = v.copy(); u.add(4)`` 后**原表**也变成
        ``[1, 2, 3, 4]``）——"在副本上加工"会静默破坏原件（与 BUG-504 的
        Table 同一家族）。这里复制 ``_data`` 与操作链 ``_ops``。
        元素对象本身仍按引用共享（值语义足够）。
        """
        _clone = super().copy()
        try:
            _clone._data = list(self._data)
            _ops = getattr(self, "_ops", None)
            if isinstance(_ops, list):
                _clone._ops = list(_ops)
        except Exception:
            pass
        return _clone

    @staticmethod
    def _check_func(func, method_name: str, arg_name: str = "func",
                    allow_none: bool = False) -> None:
        """校验"可调用对象或表达式字符串"参数（BUG-508）。

        ``map``/``filter`` 走 ``_run`` 有清晰校验（BUG-444 修过），但
        ``flat_map``/``group_by``/``count_by``/``sort_by`` 直接 ``func(item)``，
        传 123 会抛裸 "'int' object is not callable"——看不出是哪个参数。
        """
        if func is None and allow_none:
            return
        if callable(func) or isinstance(func, str):
            return
        raise TypeError(
            f"VList.{method_name}() 的 {arg_name} 需要可调用对象或表达式字符串，"
            f"收到 {type(func).__name__}: {func!r}")

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
        if isinstance(other, VList) and hasattr(other, '_data'):
            # BUG-127: 先判 VList 实例（_data 分支），VList 不继承 list，必须先命中这里。
            return self._data == other._data
        if isinstance(other, list):
            # ListLikeMeta.__instancecheck__ 使原生 list 也被 isinstance(x, VList) 判 True，
            # 但 list 没有 _data，故只能走 list() 取值（BUG-127 主修复点）。
            return self._data == list(other)
        if isinstance(other, tuple):
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

        Raises:
            ValueError: 当 step 为 0 时抛出（与 Python 内建切片语义一致）
        """
        if start is None:
            start = 0
        if stop is None:
            stop = len(self)

        if step == 0:
            # BUG-188: step=0 时 i += step 永不推进，start > stop 场景下
            # 循环条件 i > stop 且 i < len 恒为真，构成无限循环挂死。
            raise ValueError("slice step cannot be zero")

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
            # BUG-444: 原实现静默返回 []——``VList([1, 2, 3]).map(123)`` 得到
            # 空列表（静默丢数据）。非法回调必须在入口拒绝。
            raise TypeError(
                f"VList.map() 的 func 需要可调用对象或表达式字符串，收到 "
                f"{type(func).__name__}: {func!r}")

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
            # BUG-444: 同 _run——``VList([1, 2, 3]).filter(123)`` 原静默返回 []。
            raise TypeError(
                f"VList.filter() 的 func 需要可调用对象或表达式字符串，收到 "
                f"{type(func).__name__}: {func!r}")

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
        self._check_func(func, "filterfalse")
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
        self._check_func(func, "wherenot")
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
        self._check_func(func, "flat_map")
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
        self._check_func(func, "flatmap")
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
        self._check_func(key_func, "group_by", "key_func")
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
        self._check_func(key_func, "sort_by", "key_func", allow_none=True)
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        if key_func is None:
            return VList(sorted(self._data, reverse=reverse))
        if isinstance(key_func, str):
            safe_func = create_map_func(key_func)
            return VList(sorted(self._data, key=safe_func, reverse=reverse))
        return VList(sorted(self._data, key=key_func, reverse=reverse))

    def filter_not(self, func: Union[Callable[[Any], bool], str]) -> 'VList':
        """反向过滤（BUG-509：原实现继承 ``Seq.filter_not`` 的惰性 ops 版本，
        对 ``VList`` 已物化的 ``_data`` **不起作用**——``VList([1,2,3,4])
        .filter_not(123)`` 返回全部 4 个元素且无任何报错）。现与 ``wherenot``
        对齐：校验参数 + 直接走 ``filterfalse``。

        Args:
            func: 过滤函数或表达式字符串

        Returns:
            不满足条件的元素组成的 VList
        """
        self._check_func(func, "filter_not")
        return self.filterfalse(func)

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
        self._check_func(key_func, "count_by", "key_func")
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
        self._check_func(key_func, "reduce_by", "key_func")
        if not callable(reduce_func):
            raise TypeError(
                f"VList.reduce_by() 的 reduce_func 必须可调用，收到 "
                f"{type(reduce_func).__name__}: {reduce_func!r}")
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
            # BUG-445: 与 BUG-444 同族——原实现静默返回 []，
            # ``VList([(1, 2)]).starmap(123)`` 得到空列表（静默丢数据）。
            raise TypeError(
                f"VList.starmap() 的 func 需要可调用对象或表达式字符串，收到 "
                f"{type(func).__name__}: {func!r}")

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
            # BUG-445: 原实现静默返回 []，``VList([1, 2]).run(123)`` 得到空列表
            # （run 本应返回单个值，[] 既是静默失败又是错误形状）。
            raise TypeError(
                f"VList.run() 的 func 需要可调用对象或表达式字符串，收到 "
                f"{type(func).__name__}: {func!r}")

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

    # ─── legacy vicList 通用序列能力（对齐 vools.py 大文件） ───
    # 说明：legacy 里这些方法靠 @vicTools.transfer 自动把返回值包装成 vicList。
    # 核心库的 @rself 只包装「返回自身类/父类」的情形，对 chain/zip/生成器等
    # 迭代器返回值不做包装，所以这里显式构造 VList。

    def padnone(self):
        """返回元素后无限补 None（legacy ``vicList.padnone``）。

        与 legacy 一致：返回**惰性**迭代器而非 VList —— 序列无限，
        物化成 VList 会立刻挂死。用法：``itertools.islice(vl.padnone(), n)``。

        Returns:
            itertools.chain，元素之后跟无限 None
        """
        return itertools.chain(self.collect(), itertools.repeat(None))

    def rotate(self, n: int = 1) -> 'VList':
        """循环右移 n 位（legacy ``vicList.rotate``）。

        Args:
            n: 位移量，负数向左

        Returns:
            位移后的 VList
        """
        q = deque(self.collect())
        q.rotate(n)
        return VList(q)

    def ncycles(self, n: int) -> 'VList':
        """把序列重复 n 次（legacy ``vicList.ncycles``）。

        Args:
            n: 重复次数

        Returns:
            重复后的 VList
        """
        return VList(itertools.chain.from_iterable(itertools.repeat(tuple(self.collect()), n)))

    @staticmethod
    def dotproduct(vec1, vec2, sum=sum, map=None, mul=None):
        """两向量点积（legacy ``vicList.dotproduct``）。

        注意：默认参数不能写成 ``map=map``/``mul=operator.mul`` 的裸 map ——
        类体内 ``map`` 会被同名方法 VList.map 遮蔽，取到的是函数对象而非内建 map。
        因此这里用 None 哨兵，在函数体内解析真正的内建。
        """
        # BUG-509: 长度不等时静默算出**部分点积**——dotproduct([1,2],[3])
        # 返回 3（= 1*3），调用方以为算完了。零长度/不可迭代也各有裸错。
        try:
            _n1, _n2 = len(vec1), len(vec2)
        except TypeError as exc:
            raise TypeError(
                f"dotproduct 的 vec1/vec2 必须是长度可求的序列，收到 "
                f"{type(vec1).__name__}/{type(vec2).__name__}") from exc
        if _n1 != _n2:
            raise ValueError(
                f"dotproduct 的两个向量长度必须相同，收到 {_n1} 与 {_n2}"
                f"（长度不等会静默算出部分点积）")
        import builtins
        if map is None:
            map = builtins.map
        if mul is None:
            mul = operator.mul
        return sum(map(mul, vec1, vec2))

    def flatten(self) -> 'VList':
        """展平一层嵌套（legacy ``vicList.flatten``）。"""
        return VList(itertools.chain.from_iterable(self.collect()))

    @staticmethod
    def repeatfunc(func, times=None, *args) -> 'VList':
        """重复调用 func（legacy ``vicList.repeatfunc``）。

        Args:
            func: 被调用的函数
            times: 次数；None 表示无限
            *args: 传给 func 的参数

        Returns:
            VList 结果
        """
        if times is None:
            return VList(itertools.starmap(func, itertools.repeat(args)))
        return VList(itertools.starmap(func, itertools.repeat(args, times)))

    def tee(self, fill_value=None) -> 'VList':
        """相邻元素对 ``(s0,s1), (s1,s2), ...``（legacy ``vicList.tee``）。

        Args:
            fill_value: 第二个迭代器的起始填充值

        Returns:
            VList of tuples
        """
        a, b = itertools.tee(self.collect())
        next(b, fill_value)
        return VList(zip(a, b))

    def grouper(self, n: int, fillvalue=None) -> 'VList':
        """把序列切成定长块（legacy ``vicList.grouper``）。

        Args:
            n: 块大小
            fillvalue: 末块不足时的填充值

        Returns:
            VList of tuples
        """
        args = [iter(self.collect())] * n
        return VList(itertools.zip_longest(*args, fillvalue=fillvalue))

    def roundrobin(self, *iterables) -> 'VList':
        """轮流取各可迭代对象的元素（legacy ``vicList.roundrobin``）。

        实例调用时**接收者本身**是第一个可迭代对象；类调用
        ``VList.roundrobin(a, b)`` 时第一个参数即充当"接收者"，因此两种写法
        结果一致。

        BUG-367: 原实现是 ``@staticmethod`` —— `vl.roundrobin(a, b)` 会把 `vl`
        整个丢掉且不报错（`VList([1,2]).roundrobin([3,4])` 返回 `[3,4]`），
        属静默丢数据。

        Returns:
            VList 结果
        """
        iterables = (self, *iterables)
        num_active = len(iterables)
        nexts = itertools.cycle(iter(it).__next__ for it in iterables)
        out = []
        while num_active:
            try:
                for nxt in nexts:
                    out.append(nxt())
            except StopIteration:
                num_active -= 1
                nexts = itertools.cycle(itertools.islice(nexts, num_active))
        return VList(out)

    def partition(self, pred=bool) -> 'VList':
        """按谓词分成 (不满足, 满足) 两组（legacy ``vicList.partition``）。

        Args:
            pred: 谓词函数或表达式字符串

        Returns:
            含两个 VList 的 VList
        """
        if isinstance(pred, str):
            pred = create_filter_func(pred)
        t1, t2 = itertools.tee(self.collect())
        return VList([VList(itertools.filterfalse(pred, t1)), VList(filter(pred, t2))])

    def powerset(self) -> 'VList':
        """幂集（legacy ``vicList.powerset``）。"""
        data = self.collect()
        return VList(itertools.chain.from_iterable(
            itertools.combinations(data, r) for r in range(len(data) + 1)))

    def unique_everseen(self, key=None) -> 'VList':
        """按出现顺序去重，记住所有见过的元素（legacy ``vicList.unique_everseen``）。

        Args:
            key: 可选的键函数

        Returns:
            去重后的 VList
        """
        seen = set()
        seen_add = seen.add
        if key is None:
            return VList(x for x in self.collect() if not (x in seen or seen_add(x)))
        out = []
        for element in self.collect():
            k = key(element)
            if k not in seen:
                seen_add(k)
                out.append(element)
        return VList(out)

    def unique_justseen(self, key=None) -> 'VList':
        """按出现顺序去重，只记住刚见过的元素（legacy ``vicList.unique_justseen``）。

        Args:
            key: 可选的键函数

        Returns:
            去重后的 VList
        """
        return VList(next(g) for _, g in itertools.groupby(self.collect(), key))

    def first_true(self, default=False, pred=None) -> Any:
        """返回第一个为真的元素（legacy ``vicList.first_true``）。

        Args:
            default: 无匹配时的返回值
            pred: 可选谓词

        Returns:
            第一个为真的元素或 default
        """
        return next(filter(pred, self.collect()), default)

    def dropwhile(self, func) -> 'VList':
        """丢弃开头满足条件的元素（legacy ``vicList.dropwhile``）。"""
        return VList(itertools.dropwhile(func, self.collect()))

    def takewhile(self, func) -> 'VList':
        """取开头满足条件的元素（legacy ``vicList.takewhile``）。"""
        return VList(itertools.takewhile(func, self.collect()))

    def foldLeft(self, initilalValue: Any, mutable: bool = False):
        """左折叠，返回接受折叠函数的 callable（legacy ``vicList.foldLeft``）。

        Args:
            initilalValue: 初始累加值
            mutable: True 时用返回值更新累加值

        Returns:
            接受 ``f2(acc, item)`` 的函数
        """
        data = self.collect()

        def fold(f2):
            acc = initilalValue
            if mutable:
                for item in data:
                    acc = f2(acc, item)
            else:
                for item in data:
                    f2(acc, item)
            return acc
        return fold

    def foldRight(self, initilalValue: Any, mutable: bool = False):
        """右折叠，返回接受折叠函数的 callable（legacy ``vicList.foldRight``）。

        Args:
            initilalValue: 初始累加值
            mutable: True 时用返回值更新累加值

        Returns:
            接受 ``f2(acc, item)`` 的函数
        """
        data = self.collect()

        def fold(f2):
            acc = initilalValue
            if mutable:
                for item in reversed(data):
                    acc = f2(acc, item)
            else:
                for item in reversed(data):
                    f2(acc, item)
            return acc
        return fold

    def swap(self, i: int, j: int) -> 'VList':
        """交换两个位置的元素（legacy ``vicList.swap``）。

        Args:
            i: 第一个索引
            j: 第二个索引

        Returns:
            自身
        """
        if not hasattr(self, '_data'):
            self._data = list(self._evaluate())
        size = len(self._data)
        if i == j or (((i < 0 and j >= 0) or (i >= 0 and j < 0)) and (abs(i) + abs(j) == size)):
            return self
        self._data[i], self._data[j] = self._data[j], self._data[i]
        return self

    @staticmethod
    def accummap_lazy(func, iters):
        """惰性累积映射，func 收到 (索引, 已累积列表)（legacy ``vicList.accummap_lazy``）。"""
        if isinstance(func, str):
            func = create_map_func(func)
        accumulated = []
        for ix, element in enumerate(iters):
            accumulated.append(element)
            yield func(ix, accumulated.copy())

    @staticmethod
    def accummap_lazy_optimized(func, iters, window_selector=None, initial_value=None):
        """带前值缓存的累积映射，func 收到 (索引, 窗口, 前次结果)。

        （legacy ``vicList.accummap_lazy_optimized``）

        Args:
            func: ``func(ix, current_window, prev_result)``
            iters: 输入序列
            window_selector: None / int（取末尾 N 个）/ slice / callable(ix, acc)
            initial_value: 前次结果初值

        Yields:
            每次调用的结果
        """
        if isinstance(func, str):
            func = create_map_func(func)
        accumulated = []
        prev_result = initial_value
        for ix, element in enumerate(iters):
            accumulated.append(element)
            if window_selector is None:
                current_window = accumulated.copy()
            elif isinstance(window_selector, int):
                n = window_selector
                current_window = [] if n <= 0 else accumulated[max(0, len(accumulated) - n):]
            elif isinstance(window_selector, slice):
                current_window = accumulated[window_selector]
            elif callable(window_selector):
                current_window = window_selector(ix, accumulated.copy())
            else:
                raise TypeError("Selector must be int or slice")
            result = func(ix, current_window, prev_result)
            prev_result = result
            yield result

    def accummap(self, func, window_selector=None, initial_value=None) -> 'VList':
        """累积映射（legacy ``vicList.accummap``）。

        Args:
            func: 映射函数；无 window_selector/initial_value 时收到 (ix, 累积列表)
            window_selector: 见 :meth:`accummap_lazy_optimized`
            initial_value: 见 :meth:`accummap_lazy_optimized`

        Returns:
            VList 结果
        """
        if not callable(func):
            raise TypeError(
                f"VList.accummap() 的 func 必须可调用，收到 "
                f"{type(func).__name__}: {func!r}")
        if window_selector is None and initial_value is None:
            return VList(self.accummap_lazy(func, self.collect()))
        return VList(self.accummap_lazy_optimized(func, self.collect(),
                                                  window_selector, initial_value))

    def join(self, sep: str = ",", func=None, prefix: str = "", suffix: str = "") -> Any:
        """用分隔符连接各元素（legacy ``vicList.join``，返回 VText）。

        Args:
            sep: 分隔符
            func: 元素转换函数；None 时用 str
            prefix: 前缀元素
            suffix: 后缀元素

        Returns:
            连接后的 VText
        """
        from .vtext import VText
        items = self.collect()
        if func is None or func == str:
            func = lambda x: str(x)
        elif isinstance(func, str):
            func = create_map_func(func)
        if prefix:
            items = [prefix] + items
        if suffix:
            items = items + [suffix]
        return VText(sep.join(func(x) for x in items))

    def build(self, text: str = "{item}", *args, **kwargs):
        """用元素填充模板（legacy ``vicList.build``，返回 vicQuery）。

        Args:
            text: 模板字符串
            *args, **kwargs: 透传给 vicQuery

        Returns:
            vicQuery 实例

        Raises:
            RuntimeError: BUG-132 - legacy ``vools.pyk.text.vicQuery`` 未随迁移落地，
                当前 vools 包不含 pyk 子包，此方法不可用。
        """
        try:
            from ..pyk.text import vicQuery
        except ImportError as e:
            raise RuntimeError(
                "VList.build 需要 legacy vools.pyk.text.vicQuery，但 vools/pyk 子包不存在（未随迁移落地）。"
                "若需此能力请迁移 legacy vools.pyk 或改用 VList.join/str.format。"
            ) from e
        return vicQuery(text, *self.collect(), *args, **kwargs)

    def sample(self, k: Optional[int] = None) -> 'VList':
        """随机抽样（legacy ``vicList.sample``）。

        Args:
            k: 抽样数量；None 表示全部（即随机打乱）

        Returns:
            抽样结果 VList
        """
        import random as _random
        data = self.collect()
        k = len(data) if k is None else k
        return VList(_random.sample(data, k))

    def __mul__(self, other: Any) -> 'VList':
        """重复序列（legacy ``vicList.__mul__``）。"""
        return VList(self.collect() * other)

    def __rmul__(self, other: Any) -> 'VList':
        """右向重复序列（legacy ``vicList.__rmul__``）。"""
        return VList(other * self.collect())

    # ─── legacy 兼容方法 ───

    def accum(self, func: Union[Callable[[T, T], T], str] = operator.add):
        """累积计算（legacy ``vicList.accum``）。

        Args:
            func: 累积函数或表达式字符串，默认加法。

        Returns:
            itertools.accumulate 迭代器
        """
        if isinstance(func, str):
            func = safe_compile_expression(func, ('x', 'y'))
        return itertools.accumulate(self, func=func)

    def mapmap(self, inner_func, outer_func=None, outer_func_first=False) -> 'VList':
        """双重 map（legacy ``vicList.mapmap``）。

        Args:
            inner_func: 内层函数或表达式字符串
            outer_func: 外层函数或表达式字符串，None 时只做内层
            outer_func_first: True 时先应用 outer_func 再应用 inner_func

        Returns:
            VList
        """
        if self.size == 0:
            return VList([])
        temp = self
        if outer_func is not None and outer_func_first:
            temp = temp.map(outer_func)
        if temp.any_equal(lambda x: not isinstance(x, Iterable)):
            raise TypeError("All items of self must be a Iterable item, check it !!!")
        inner_func = inner_func if callable(inner_func) else (
            create_map_func(inner_func) if isinstance(inner_func, str) else None
        )
        temp = temp.map(lambda it: VList(it).map(inner_func))
        return temp if outer_func is None or outer_func_first else temp.map(outer_func)

    def reduce(self, func: Union[Callable[[T, T], T], str] = operator.add, init=None):
        """聚合操作（legacy ``vicList.reduce``）。

        Args:
            func: 聚合函数或表达式字符串，默认加法
            init: 初始值

        Returns:
            聚合结果
        """
        if isinstance(func, str):
            func = safe_compile_expression(func, ('x', 'y'))
        from functools import reduce as _reduce
        return _reduce(func, self) if init is None else _reduce(func, self, init)

    def zip(self, *iterables) -> 'VList':
        """与另一可迭代对象配对（legacy ``vicList.zip``）。

        Returns:
            VList
        """
        import builtins
        return VList(list(builtins.zip(self, *iterables)))

    def zip_longest(self, *iterables, fillvalue=None) -> 'VList':
        """配对并填充缺失值（legacy ``vicList.zip_longest``）。

        Returns:
            VList
        """
        return VList(list(itertools.zip_longest(self, *iterables, fillvalue=fillvalue)))

    def toDF(self, cols=None, pos_name=None, source_type: str = "hive"):
        """转成 pyspark DataFrame（legacy ``vicList.toDF``）。

        Args:
            cols: 列名
            pos_name: 位置列名
            source_type: 源类型，默认 "hive"

        Returns:
            pyspark.sql.DataFrame；空列表返回 None

        Raises:
            RuntimeError: BUG-132 - legacy ``vools.pyk.df.vDF`` 未随迁移落地，
                当前 vools 包不含 pyk 子包，此方法不可用。
        """
        if self.size == 0:
            return None
        temp = self[0]
        lst = self
        if isinstance(temp, str) or not isinstance(temp, Iterable):
            lst = [(i,) for i in lst]
        try:
            from ..pyk.df import vDF
        except ImportError as e:
            raise RuntimeError(
                "VList.toDF 需要 legacy vools.pyk.df.vDF，但 vools/pyk 子包不存在（未随迁移落地）。"
                "若需此能力请迁移 legacy vools.pyk 或直接用 pyspark.spark.createDataFrame。"
            ) from e
        return vDF(list(lst), cols=cols, pos_name=pos_name, source_type=source_type)

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
