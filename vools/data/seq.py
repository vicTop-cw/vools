from itertools import chain,zip_longest,groupby
import itertools
from sys import maxsize as maxint
from typing import Iterable, Callable, Iterator, List, Tuple, Optional, Any, TypeVar, Generic, Generator, Type, Union

T = TypeVar('T')
R = TypeVar('R')
K = TypeVar('K')
S = TypeVar('S')
from functools import reduce,wraps
from inspect import isgeneratorfunction,signature
from collections import deque
from operator import itemgetter
from ..functional.placeholder import _
from ..config import config

__all__ = ['Seq','NONE','collect']
_expr = _.__expr__
_NONE_is_None = config.other['NONE_is_None']

class _NONE:
    __slots__ = ()
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __eq__(self, other):
        if other is None:
            return _NONE_is_None
        return other is NONE
    
    def __bool__(self):
        return False
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __repr__(self):
        return "NONE"

    def __lt__(self, other):
        return False
    
    def __gt__(self, other):
        return False
    
    def __ge__(self, other):
        return self == other 
    
    def __le__(self, other):
        return self == other 

    def __hash__(self):
        return hash(None)
    
    def __str__(self):
        return "NONE"
    
    def __iter__(self):
        return self
    
    def __next__(self):
        raise StopIteration()

    def __len__(self):
        return 0
    
    def __getitem__(self,_):
        return self
    
    def __getattr__(self,_):
        return self

    def __call__(self,*_,**__):
        return self

    def __add__(self, other):
        return self
    
    def __radd__(self, other):
        return self

    def __mul__(self, other):
        return self
        
    def __rmul__(self, other):
        return self


    def __rshift__(self, other):
        return self

    def __lshift__(self, other):
        return self
    
    def __sub__(self, other):
        return self
    
    def __rsub__(self, other):
        return self
    
    def __mod__(self, other):
        return self
    
    def __pow__(self, other):
        return self
    
    def __div__(self, other):
        return self
        
    def __rdiv__(self, other):
        return self
    
    def __truediv__(self, other):
        return self

    def __rtruediv__(self, other):
        return self

    def __rmod__(self, other):
        return self
    
    def __rpow__(self, other):
        return self
    
    def __neg__(self):
        return self
    
    def __pos__(self):
        return self

    def __and__(self, other):
        return self
    
    def __or__(self, other):
        return self

    def __xor__(self, other):
        return self
    
    def __rand__(self, other):
        return self
    
    def __ror__(self, other):
        return self

    def __matmul__(self, other):
        return self

NONE = _NONE()



class SeqBase:
    __slots__ = ['_last','_collection','_origin','_current']
    
    class _SeqIterator:
        __slots__ = ['_seq','_position']
        
        def __init__(self, it: 'SeqBase') -> None:
            """初始化迭代器。
            
            Args:
                it: 要迭代的 SeqBase 实例
            """
            self._seq = it
            self._position = -1
        
        def __next__(self) -> T:
            """返回序列中的下一个元素。
            
            Returns:
                序列中的下一个元素
                
            Raises:
                StopIteration: 当序列耗尽时
            """
            self._position += 1
            if (len(self._seq._collection) > self._position or
                self._seq._fill_to(self._position)):
                return self._seq._collection[self._position]
            raise StopIteration()
            
    def __init__(self, *origins: Any) -> None:
        """初始化 SeqBase 实例。
        
        Args:
            *origins: 可变参数，接受单个可迭代对象、多个值或空参数
        """
        self._collection = []
        self._last = -1
        self._current = -1
        l = len(origins)
        if l == 1:
            if hasattr(origins[0],"collect"):
                self._origin = iter(origins[0].collect())
            else:
                self._origin = iter(origins[0]) if origins[0] else iter([])
        elif l == 0:
            self._origin = iter([])
        else:
            self._origin = iter(origins)

    def __lshift__(self, rv: Any) -> 'SeqBase':
        """左移运算符 (<<) 支持惰性追加。
        
        Args:
            rv: 要追加的值或函数。若为单参数函数，则对每个元素应用该函数；
               若为无参数函数，则调用该函数生成序列；若为可迭代对象，则直接追加。
               
        Returns:
            self
        """
        if callable(rv):
            cnt= len(signature(rv).parameters)
            if cnt ==0:
                it = rv()
                self._origin = chain(self._origin,it)
                return self
            return self.__class__(rv(i) for i in self._evaluate())
        self._origin = chain(self._origin,rv)
        return self
    
    def cursor(self) -> int:
        """返回当前游标位置。
        
        Returns:
            已评估的元素数量
        """
        return self._last + 1
    
    def _fill_to(self, ix: int) -> bool:
        """惰性填充集合到指定索引。
        
        Args:
            ix: 目标索引位置
            
        Returns:
            若成功填充到指定位置返回 True，否则返回 False
        """
        if self._last >= ix:
            return True
        
        while self._last < ix:
            try:
                n = next(self._origin)
            except StopIteration:
                return False
            self._last += 1
            self._collection.append(n)
        
        return True
    
    def __iter__(self):
        return self._SeqIterator(self)
    
    def __next__(self):
        self._current += 1
        if not self._fill_to(self._current):
            raise StopIteration()
        return self._collection[self._current]   
    
    def __getitem__(self,ix):
        if isinstance(ix,int):
            if ix < 0 : raise TypeError("invalid argument negative value")
            self._fill_to(ix)
        elif isinstance(ix,slice):
            l,h,s = ix.indices(maxint)
            if s == 0 :raise ValueError('Step must not be 0')
            return self.__class__() << map(self.__getitem__,range(l,h,s or 1))
        else:
            raise TypeError('invalid argument type')
        
        return self._collection.__getitem__(ix)
    
    @classmethod    
    def of(cls: Type[S], *args: T) -> S:
        """从参数创建 Seq。
        
        单参数时返回包含单个值的 Seq，多参数时返回包含这些值的序列。
        
        Args:
            *args: 单个值或多个值
            
        Returns:
            Seq 实例
        """
        if len(args) == 1:
            return cls.from_callable(lambda:args[0],stop_func=lambda x:x is not NONE)
        return cls(*args)
    
    @classmethod
    def range(cls: Type[S], start: int, stop: Optional[int] = None, step: int = 1) -> S:
        """创建整数范围序列，类似 Python 的 range。
        
        Args:
            start: 起始值（包含）
            stop: 结束值（不包含），若为 None 则 start 为 stop，start 设为 0
            step: 步长，默认为 1
            
        Returns:
            整数范围的 Seq 实例
        """
        if stop is None:
            stop = start
            start = 0
        return cls(range(start,stop,step))
    
    @classmethod
    def cycle(cls: Type[S], func: Callable[[], T], times: Optional[int] = None) -> S:
        """循环调用函数生成无限（或有限）序列。
        
        Args:
            func: 无参数函数，每次调用生成一个元素
            times: 循环次数，若为 None 则无限循环
            
        Returns:
            循环生成的 Seq 实例
            
        Raises:
            ValueError: times 为负数时
        """
        if isgeneratorfunction(func):
            return cls(func())
        if times is None:
            times = float('inf')
        else:
            times = int(times)
            if times < 0:
                raise ValueError('times must be non-negative')
        def gen():
            nonlocal times
            while True:
                yield func()
                times -= 1
                if times == 0:
                    break
        return cls(gen())
    
    @classmethod
    def from_callable(cls: Type[S], gen: Callable[..., T], *args: Any, stop_func: Optional[Callable[[T], bool]] = None, **kwargs: Any) -> S:
        """从可调用对象生成惰性序列。
        
        Args:
            gen: 生成函数或生成器函数
            *args: 传递给 gen 的位置参数（首个值作为初始值）
            stop_func: 停止条件函数，接收元素返回 bool
            **kwargs: 传递给 gen 的关键字参数
            
        Returns:
            生成的 Seq 实例
            
        Raises:
            TypeError: gen 不可调用且无初始值时
        """
        stop = lambda x : x is NONE if stop_func is None else stop_func(x)
        if isgeneratorfunction(gen):
            def g():
                for v in gen(*args,**kwargs):
                    yield v
                    if stop(v):
                        break
            return cls(g())
        init_value = args[0] if args else NONE
        if init_value is NONE:
            if not callable(gen):
                raise TypeError('invalid argument Type,must callable or gen ')
            def g():
                while True:
                    v = gen()
                    yield v
                    if stop(v):
                        break
            return cls(g())
        params = signature(gen).parameters
        if len(params) == 0:
            def g():
                nonlocal init_value
                yield init_value
                while True:
                    init_value = gen()
                    if stop(init_value):
                        break
                    yield init_value
            return cls(g())
        elif len(params) == 1:
            def g():
                nonlocal init_value
                yield init_value
                while True:
                    init_value = gen(init_value)
                    if stop(init_value):
                        break
                    yield init_value
            return cls(g())
        else:
            def g():
                nonlocal init_value
                yield init_value
                while True:
                    init_value = gen(init_value,*args[1:],**kwargs)
                    if stop(init_value):
                        break
                    yield init_value
            return cls(g())

_yib = lambda x:isinstance(x, Iterable) and not isinstance(x, (str,bytes,bytearray))
_identify = lambda x : x
_compact = lambda x : x is not None
def _pipe(*funcs):
    def _inn(source):
        return reduce(lambda x,f:f(x),funcs,source)
    return _inn

def _compose(*funcs):
    return _pipe(*funcs[::-1])

class Seq(SeqBase):
    def __init__(self, *origins: Any) -> None:
        """初始化 Seq 实例。
        
        Args:
            *origins: 可变参数，接受单个可迭代对象、多个值或空参数
        """
        super().__init__(*origins)
        self._ops: List[Tuple[Callable[..., Any], bool]] = []
        self._active_op: Callable[[Any], Any] = _identify
    
    def _add_op(self, op: Callable[[Any], Any], is_filter: bool = False) -> 'Seq':
        """添加操作到操作管道。
        
        Args:
            op: 操作函数
            is_filter: 是否为过滤操作
            
        Returns:
            self
        """
        self._ops.append((op, is_filter))
        o = (lambda x: x if op(x) else NONE ) if is_filter else op
        self._active_op = o if not self._active_op else _pipe(self._active_op, o)
        return self
    
    @property
    def unique(self) -> List[T]:
        """返回去重后的列表。
        
        Returns:
            去重后的列表
        """
        rs: List[T] = []
        s = set()
        d = s.add
        for i in self._evaluate():
            if i not in s:
                d(i)
                rs.append(i)
        return rs
    
    def distinct(self, key: Optional[Callable[[T], K]] = None) -> 'Seq':
        """返回去重后的序列。
        
        Args:
            key: 可选的 key 函数，用于根据 key 去重
            
        Returns:
            新的去重后的 Seq 实例
        """
        if key is None:
            key = _identify
        def gen():
            s = set()
            d = s.add
            for i in self._evaluate():
                k = key(i)
                if k not in s:
                    d(k)
                    yield i
        return self.__class__(gen())
    
    def group_by(self, key: Optional[Callable[[T], K]] = None) -> 'Seq':
        """按 key 分组。
        
        Args:
            key: 分组 key 函数，默认为恒等函数
            
        Returns:
            (key, group_list) 元组序列的 Seq 实例
        """
        if key is None:
            key = _identify
        def gen():
            for k, g in groupby(sorted(self._evaluate(), key=key), key=key):
                yield k, list(map(itemgetter(1), g))
        return self.__class__(gen())
    
    def grouper(self, n: int, fillvalue: Any = None) -> 'Seq':
        """按固定大小分组。
        
        Args:
            n: 每组元素个数
            fillvalue: 填充值，用于填充最后一组
            
        Returns:
            分组后的 Seq 实例
        """
        def gen():
            args = [iter(self._evaluate())] * n
            for i in zip_longest(*args, fillvalue=fillvalue):
                yield i
        return self.__class__(gen())
    
    def prepend(self, *args: Any) -> 'Seq':
        """在序列前插入元素。
        
        Args:
            *args: 要插入的元素，可迭代对象会被展开
            
        Returns:
            新的 Seq 实例
        """
        return self.__class__(chain(*[iter(a) if isinstance(a, Iterable) else [a] for a in args], self._evaluate()))
    
    def extend(self, *args: Any) -> 'Seq':
        """在序列末尾追加元素。
        
        Args:
            *args: 要追加的元素，可迭代对象会被展开
            
        Returns:
            新的 Seq 实例
        """
        return self.__class__(chain(self._evaluate(), *[iter(a) if isinstance(a, Iterable) else [a] for a in args]))
    
    def add(self, *args: Any, **kwargs: Any) -> 'Seq':
        """追加元素到序列。
        
        Args:
            *args: 要追加的位置参数
            **kwargs: 要追加的关键字参数的值
            
        Returns:
            新的 Seq 实例
        """
        return self.__class__(chain(self._evaluate(), args, kwargs.values()))
    
    def add_reversed(self, *args: Any, **kwargs: Any) -> 'Seq':
        """反向追加元素（kwargs 在前）。
        
        Args:
            *args: 要追加的位置参数（在 kwargs 之后）
            **kwargs: 要追加的关键字参数的值（在最前面）
            
        Returns:
            新的 Seq 实例
        """
        return self.__class__(chain(args, kwargs.values(), self._evaluate()))
    
    def sort_by(self, key: Optional[Callable[[T], Any]] = None, reverse: bool = False) -> 'Seq':
        """排序序列。
        
        Args:
            key: 排序 key 函数
            reverse: 是否反向排序
            
        Returns:
            排序后的新 Seq 实例
        """
        return self.__class__(sorted(self._evaluate(), key=key, reverse=reverse))
    
    def reverse(self) -> 'Seq':
        """反转序列。
        
        Returns:
            反转后的新 Seq 实例
        """
        return self.__class__(reversed(list(self._evaluate())))
    
    def sorted(self, key: Optional[Callable[[T], Any]] = None, reverse: bool = False) -> List[T]:
        """返回排序后的列表。
        
        Args:
            key: 排序 key 函数
            reverse: 是否反向排序
            
        Returns:
            排序后的列表
        """
        return list(sorted(self._evaluate(), key=key, reverse=reverse))
    
    def count_by(self, key: Optional[Callable[[T], K]] = None) -> 'Seq':
        """按 key 计数。
        
        Args:
            key: 分组 key 函数，默认为恒等函数
            
        Returns:
            (key, count) 元组序列的 Seq 实例
        """
        if key is None:
            key = _identify
        def gen():
            for k, g in groupby(sorted(self._evaluate(), key=key), key=key):
                yield k, len(list(g))
        return self.__class__(gen())
    
    def reduce_by(self, key: Optional[Callable[[T], K]] = None, func: Optional[Callable[[T, T], T]] = None) -> 'Seq':
        """按 key 分组后 reduce。
        
        Args:
            key: 分组 key 函数，默认为恒等函数
            func: 聚合函数，默认为加法
            
        Returns:
            (key, reduced_value) 元组序列的 Seq 实例
        """
        if key is None:
            key = _identify
        if func is None:
            func = lambda x, y: x + y
        def gen():
            for k, g in groupby(sorted(self._evaluate(), key=key), key=key):
                yield k, reduce(func, g)
        return self.__class__(gen())
    
    def any(self, func: Optional[Callable[[T], bool]] = None) -> bool:
        """是否有任意元素满足条件。
        
        Args:
            func: 条件函数，默认为检查非 None
            
        Returns:
            若有任意元素满足条件返回 True，否则返回 False
        """
        if func is None:
            func = _compact
        return any(func(i) for i in self._evaluate())
    
    def all(self, func: Optional[Callable[[T], bool]] = None) -> bool:
        """是否所有元素满足条件。
        
        Args:
            func: 条件函数，默认为检查非 None
            
        Returns:
            若所有元素满足条件返回 True，否则返回 False
        """
        if func is None:
            func = _compact
        return all(func(i) for i in self._evaluate())
    
    def find(self, func: Optional[Callable[[T], bool]] = None) -> Any:
        """查找第一个满足条件的元素。
        
        Args:
            func: 条件函数，默认为检查非 None
            
        Returns:
            第一个满足条件的元素，若无则返回 NONE
        """
        if func is None:
            func = _compact
        for i in self._evaluate():
            if func(i):
                return i
        return NONE
    
    def find_index(self, func: Optional[Callable[[T], bool]] = None) -> Any:
        """查找第一个满足条件的元素索引。
        
        Args:
            func: 条件函数，默认为检查非 None
            
        Returns:
            第一个满足条件的元素索引，若无则返回 NONE
        """
        if func is None:
            func = _compact
        for i, v in enumerate(self._evaluate()):
            if func(v):
                return i
        return NONE
    
    def accum(self, func: Callable[[T, T], T], initial: Optional[T] = None) -> 'Seq':
        """累积计算。
        
        Args:
            func: 累积函数
            initial: 初始值
            
        Returns:
            累积计算结果序列的 Seq 实例
        """
        if initial is None:
            return self.__class__(itertools.accumulate(self._evaluate(), func))
        else:
            return self.__class__(itertools.accumulate(self._evaluate(), func, initial))
    
    def __iadd__(self, other: Any) -> 'Seq':
        """+= 运算符。
        
        Args:
            other: 要追加的元素
            
        Returns:
            self
        """
        return self.add(other)
    
    def __rshift__(self, func: Callable[[T], Any]) -> 'Seq':
        """>>= 运算符（映射操作）。
        
        Args:
            func: 映射函数
            
        Returns:
            映射后的 Seq 实例
        """
        return self.map(func)
    
    def __or__(self, other: Callable[[Iterable[T]], R]) -> R:
        """ | 运算符（立即求值）。
        
        Args:
            other: 处理函数
            
        Returns:
            处理函数作用在序列上的结果
            
        Raises:
            TypeError: other 不可调用时
        """
        if not callable(other):
            raise TypeError('unsupported operand type(s) for |: \'{}\' and \'{}\''.format(type(self).__name__, type(other).__name__))
        return other(self._evaluate())
    
    def run(self, func: Callable[['Seq'], R]) -> R:
        """运行函数并返回结果。
        
        Args:
            func: 要执行的函数
            
        Returns:
            函数执行结果
            
        Raises:
            TypeError: func 不可调用时
        """
        if not callable(func):
            raise TypeError('func must be callable')
        return func(self)
    
    def __add__(self, other: Any) -> 'Seq':
        """ + 运算符。
        
        Args:
            other: 要追加的元素
            
        Returns:
            新的 Seq 实例
        """
        return self.add(other)
    
    def __radd__(self, other: Any) -> 'Seq':
        """反向 + 运算符。
        
        Args:
            other: 要在前面追加的元素
            
        Returns:
            新的 Seq 实例
        """
        return self.add_reversed(other)
    
    def __len__(self) -> int:
        """序列长度（惰性求值）。
        
        Returns:
            序列长度
        """
        return sum(1 for _ in self._evaluate())
    
    def __bool__(self) -> bool:
        """序列是否有元素。
        
        Returns:
            若有元素返回 True，否则返回 False
        """
        return any(True for _ in self._evaluate())
    
    def __repr__(self) -> str:
        """字符串表示。
        
        Returns:
            Seq 的字符串表示
        """
        s = self.take(21, True)
        if len(s) == 21:
            s.append('...')
        return f"Seq({s})"
    
    def __str__(self) -> str:
        """字符串表示。
        
        Returns:
            Seq 的字符串表示
        """
        s = self.take(21, True)
        if len(s) == 21:
            s.append('...')
        return f"Seq({s})"
    
    def _evaluate(self) -> Generator[T, None, None]:
        """惰性求值核心。
        
        Yields:
            应用当前操作管道后的元素
        """
        op = self._active_op
        for i in self:
            x = op(i)
            if x is not NONE:
                yield x

    def map(self, *funcs: Callable[[T], Any]) -> 'Seq':
        """映射操作。
        
        Args:
            *funcs: 一个或多个映射函数
            
        Returns:
            self
        """
        for m in funcs:
            f = lambda x: NONE if x is NONE else m(x)
            self._add_op(f)
        return self
    
    def filter(self, *funcs: Callable[[T], bool]) -> 'Seq':
        """过滤操作。
        
        Args:
            *funcs: 一个或多个过滤函数
            
        Returns:
            self
        """
        for m in funcs:
            f = lambda x: NONE if (x is NONE if not _NONE_is_None else x is None or x is NONE) or not m(x) else x
            self._add_op(f, True)
        return self
    
    def filterfalse(self, *funcs: Callable[[T], bool]) -> 'Seq':
        """过滤掉满足条件的元素。
        
        Args:
            *funcs: 一个或多个过滤函数
            
        Returns:
            self
        """
        for m in funcs:
            f = lambda x: NONE if (x is NONE if not _NONE_is_None else x is None or x is NONE) or m(x) else x
            self._add_op(f, True)
        return self
    
    filter_not = filternot = filter_false = filterfalse

    def _starmap(self, *funcs: Callable[[Any], Any]) -> 'Seq':
        """内部 starmap 实现。
        
        Args:
            *funcs: 一个或多个函数
            
        Returns:
            self
        """
        funcs = list(funcs)
        while funcs:
            k = funcs.pop(0)
            f = lambda x: NONE if x is NONE else (k(*x) if _yib(x) else k(x))
            self._add_op(f)
        return self
    
    def _mapmap(self, *funcs: Callable[[Any], Any]) -> 'Seq':
        """内部 mapmap 实现。
        
        Args:
            *funcs: 一个或多个函数
            
        Returns:
            self
        """
        if len(funcs) == 1:
            func = funcs[0]
            f = lambda x: NONE if x is NONE else ([NONE if i is NONE else func(i) for i in x] if _yib(x) else func(x))
            self._add_op(f)
            return self
        elif len(funcs) == 0:
            return self
        
        def _inner(x):
            nonlocal funcs
            if _yib(x):
                it = zip_longest(x, funcs, fillvalue=NONE)
                return [NONE if i is NONE or f is NONE else f(i) for i, f in it]
            return [f(x) for f in funcs]
        self._add_op(_inner)
        return self

    def where(self, *funcs: Any, mode: str = 'single', func_type: str = 'lambda') -> 'Seq':
        """LINQ 风格 filter。
        
        Args:
            *funcs: 过滤函数
            mode: 表达式模式
            func_type: 函数类型
            
        Returns:
            self
        """
        f = lambda ff: _expr(ff, mode, func_type)
        return self.filter(*map(f, funcs))
    
    def wherenot(self, *funcs: Any, mode: str = 'single', func_type: str = 'lambda') -> 'Seq':
        """LINQ 风格 filter_not。
        
        Args:
            *funcs: 过滤函数
            mode: 表达式模式
            func_type: 函数类型
            
        Returns:
            self
        """
        f = lambda ff: _expr(ff, mode, func_type)
        return self.filterfalse(*map(f, funcs))

    def select(self, *funcs: Any, mode: str = 'single', func_type: str = 'lambda') -> 'Seq':
        """LINQ 风格 map。
        
        Args:
            *funcs: 映射函数
            mode: 表达式模式
            func_type: 函数类型
            
        Returns:
            self
        """
        f = lambda ff: _expr(ff, mode, func_type)
        return self.map(*map(f, funcs))

    def starmap(self, *funcs: Any, mode: str = 'single', func_type: str = 'lambda') -> 'Seq':
        """LINQ 风格 starmap。
        
        Args:
            *funcs: 函数
            mode: 表达式模式
            func_type: 函数类型
            
        Returns:
            self
        """
        f = lambda ff: _expr(ff, mode, func_type)
        return self._starmap(*map(f, funcs))

    def mapmap(self, *funcs: Any, mode: str = 'single', func_type: str = 'lambda') -> 'Seq':
        """双重 map。
        
        Args:
            *funcs: 函数
            mode: 表达式模式
            func_type: 函数类型
            
        Returns:
            self
        """
        f = lambda ff: _expr(ff, mode, func_type)
        return self._mapmap(*map(f, funcs))

    def collect(self) -> List[T]:
        """将惰性序列物化为列表。
        
        Returns:
            包含所有元素的列表
        """
        return list(self._evaluate())
    
    def reduce(self, func: Callable[[T, T], T], init: Optional[T] = None) -> T:
        """聚合操作。
        
        Args:
            func: 聚合函数
            init: 初始值
            
        Returns:
            聚合结果
        """
        if init is None:
            return reduce(func, self._evaluate())
        else:
            return reduce(func, self._evaluate(), init)
    
    def take_while(self, func: Callable[[T], bool]) -> 'Seq':
        """满足条件时取元素。
        
        Args:
            func: 条件函数
            
        Returns:
            新的 Seq 实例
        """
        return self.__class__(itertools.takewhile(func, self._evaluate()))
    
    def drop_while(self, func: Callable[[T], bool]) -> 'Seq':
        """跳过满足条件的元素。
        
        Args:
            func: 条件函数
            
        Returns:
            新的 Seq 实例
        """
        return self.__class__(itertools.dropwhile(func, self._evaluate()))
    
    def take(self, n: int, action: bool = False) -> Union[List[T], 'Seq']:
        """取前 n 个元素。
        
        Args:
            n: 要取的元素个数
            action: 若为 True，返回列表；否则返回 Seq 实例
            
        Returns:
            列表或 Seq 实例
        """
        if action:
            rs: List[T] = []
            d = rs.append
            for i, v in enumerate(self._evaluate()):
                if i < n:
                    d(v)
                else:
                    break
            return rs

        def gen():
            for i, v in enumerate(self._evaluate()):
                if i < n:
                    yield v
                else:
                    break
        return self.__class__(gen())

    def tee(self, n: int = 2, fillvalue: Any = None) -> 'Seq':
        """将序列 tee 成 n 路并行迭代器。
        
        Args:
            n: 并行路数，默认为 2
            fillvalue: 填充值
            
        Returns:
            新的 Seq 实例
        """
        def gen():
            q = deque(maxlen=n)
            d = q.append
            for i in self._evaluate():
                d(i)
                if len(q) == n:
                    yield tuple(q)
            else:
                for i in range(n - 1):
                    d(fillvalue)
                    yield tuple(q)
        return self.__class__(gen())
    
    def skip(self, n: int) -> 'Seq':
        """跳过前 n 个元素。
        
        Args:
            n: 要跳过的元素个数
            
        Returns:
            新的 Seq 实例
        """
        def gen():
            for i, v in enumerate(self._evaluate()):
                if i >= n:
                    yield v
        return self.__class__(gen())
    
    def enumerate(self, n: int = 0) -> 'Seq':
        """带索引的迭代。
        
        Args:
            n: 起始索引，默认为 0
            
        Returns:
            (index, value) 元组序列的 Seq 实例
        """
        def gen():
            for i, v in enumerate(self._evaluate(), n):
                yield i, v
        return self.__class__(gen())
    
    def zip(self, *its: Iterable[Any]) -> 'Seq':
        """与另一可迭代对象配对。
        
        Args:
            *its: 一个或多个可迭代对象
            
        Returns:
            配对后的 Seq 实例
        """
        def gen():
            for i in zip(self._evaluate(), *its):
                yield i
        return self.__class__(gen())
    
    def zip_longest(self, *its: Iterable[Any], fillvalue: Any = None) -> 'Seq':
        """配对并填充缺失值。
        
        Args:
            *its: 一个或多个可迭代对象
            fillvalue: 填充值
            
        Returns:
            配对后的 Seq 实例
        """
        def gen():
            for i in zip_longest(self._evaluate(), *its, fillvalue=fillvalue):
                yield i
        return self.__class__(gen())
    
    def flatten(self) -> 'Seq':
        """展平嵌套可迭代对象。
        
        Returns:
            展平后的 Seq 实例
        """
        def gen():
            for i in self._evaluate():
                if _yib(i):
                    for j in i:
                        yield j
                else:
                    yield i
        return self.__class__(gen())
                
    def as_list(self) -> List[T]:
        """别名 collect。
        
        Returns:
            列表
        """
        return list(self._evaluate())
    
    def flatmap(self, func: Callable[[T], Any] = _identify, mode: str = 'before') -> 'Seq':
        """映射后展平。
        
        Args:
            func: 映射函数
            mode: 'before' 表示先映射后展平，'after' 表示先展平后映射
            
        Returns:
            新的 Seq 实例
            
        Raises:
            ValueError: mode 不是 'before' 或 'after' 时
        """
        def gen():
            if mode == 'before':
                for i in self._evaluate():
                    i = func(i)
                    if _yib(i):
                        for j in i:
                            yield j
                    else:
                        yield i
            elif mode == 'after':
                for i in self._evaluate():
                    if _yib(i):
                        for j in i:
                            yield func(j)
                    else:
                        yield func(i)
            else:
                raise ValueError('mode must be <before> or <after>')
        return self.__class__(gen())

    def flatmap_ex1(self,
                    map_before: Callable[[T], T] = _identify,
                    map_after: Callable[[T], T] = _identify,
                    filter_before_before: Callable[[T], bool] = _compact,
                    filter_before_after: Callable[[T], bool] = _compact,
                    filter_after_before: Callable[[T], bool] = _compact,
                    filter_after_after: Callable[[T], bool] = _compact) -> 'Seq':
        """高级 flatmap（含多层 filter）。
        
        自动过滤 None 值。
        
        Args:
            map_before: 第一次映射函数
            map_after: 第二次映射函数
            filter_before_before: 第一次映射前的过滤函数
            filter_before_after: 第一次映射后的过滤函数
            filter_after_before: 第二次映射前的过滤函数
            filter_after_after: 第二次映射后的过滤函数
            
        Returns:
            新的 Seq 实例
        """
        def _before(i):
            if filter_before_before(i):
                i = map_before(i)
                if filter_before_after(i):
                    return True, i
            return False, None
        
        def _after(j):
            if filter_after_before(j):
                j = map_after(j)
                if filter_after_after(j):
                    return True, j
            return False, None
        
        def gen():
            for i in self._evaluate():
                p, i = _before(i)
                if p:
                    if _yib(i):
                        for j in i:
                            p1, j = _after(j)
                            if p1: yield j
                    else:
                        if p1: yield i
        return self.__class__(gen())
    
    def flatmap_ex(self, before_func: Optional[Callable[[T], Tuple[bool, T]]] = None, after_func: Optional[Callable[[T], Tuple[bool, T]]] = None) -> 'Seq':
        """通用 flatmap，支持 before_func/after_func。
        
        before_func: 单参函数并返回 tuple2(bool p, value v)，对每个元素迭代形成的值
            p 为假丢弃，为真保留 v
        after_func: 单参函数并返回 tuple2(bool p, value v)，对步骤一保留下来的值进行处理
            p 为假丢弃，为真保留 v
        
        Args:
            before_func: 前置处理函数，默认为检查非 None
            after_func: 后置处理函数，默认为检查非 None
            
        Returns:
            新的 Seq 实例
        """
        before_func = (lambda x: (x is not None, x)) if before_func is None else before_func
        after_func = (lambda x: (x is not None, x)) if after_func is None else after_func
        def gen():
            for i in self._evaluate():
                p, i = before_func(i)
                if p:
                    if _yib(i):
                        for j in i:
                            p1, j = after_func(j)
                            if p1: yield j
                    else:
                        if p1: yield i
        return self.__class__(gen())
    
    @property
    def size(self) -> int:
        """序列大小（惰性求值，遍历一次）。
        
        Returns:
            序列元素个数
        """
        return sum(1 for _ in self._evaluate())
    
    def join(self, sep: str = ',') -> str:
        """用分隔符连接元素为字符串。
        
        Args:
            sep: 分隔符，默认为逗号
            
        Returns:
            连接后的字符串
        """
        return sep.join(str(i) for i in self._evaluate())
    @classmethod 
    def ensure_seq(cls,func):
        """ ensure func is a generator function ,then return a Seq result """
        if not callable(func):
            raise TypeError('func must be callable or generator function')
        @wraps(func)
        def _inner(*args,**kwargs):
            return cls(func(*args,**kwargs))
        return _inner
            
    def register(self,func):
        """ register a function to Seq instance """
        if not callable(func):
            @property
            def _prop(self):
                return func
            setattr(self,func.__name__ or str(func) ,_prop)
            return _prop
        @wraps(func)
        def _inner(self,*args,**kwargs):
            return func(self,*args,**kwargs)
        setattr(self,func.__name__,_inner)

    # ---- serialization support ----

    def __getstate__(self):
        """返回序列化状态：将延迟求值的数据物化为列表保存"""
        # 物化数据：触发实际求值，保存结果列表
        data = list(self._evaluate())
        return {'_data': data}


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
    def __setstate__(self, state):
        """从序列化状态恢复：从物化数据重建 Seq"""
        data = state.get('_data', [])
        self._collection = list(data)
        self._last = len(data) - 1
        self._current = -1
        self._origin = iter([])  # empty origin, data already in _collection
        self._ops = []
        self._active_op = _identify


def collect(xs,f=None,factory=Seq) :
    """_summary_

    Args:
        xs (Iterable[T]): an iterable of type T
        f (Callable[[T],R]): a function that takes an argument of type T and returns an object of type R or None
        factory (type, optional): the type of the return value. Defaults to list.

    Raises:
        TypeError: if f is not a callable or xs is not an iterable

    Returns:
        Iterable[R]: an iterable of type R

    Yields:
        R: the result of applying f to each element of xs that is not None and is greater than 3
    """
    if f is None:
        f = _identify
    if not callable(f):
        raise TypeError("f must be a callable")
    if not isinstance(xs,Iterable):
        raise TypeError("xs must be an iterable")
    def gen():
        lmd= lambda x : x is not NONE if not _NONE_is_None else x is not None and x is not NONE
        for x in xs:
            fx = f(x)
            if lmd(fx):
                yield fx
    return factory(gen()) if factory is not None else gen()
