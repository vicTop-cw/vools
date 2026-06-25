"""
Functional Programming Toolkit - Pipe Operations

This module provides a set of functional programming utilities inspired by
Haskell's pipes and Clojure's transducers. It allows for building composable
data processing pipelines using operator overloading and currying.
"""

from typing import Iterable, Callable, Any, Optional, Tuple, List, TypeVar, Generic, Union
from functools import reduce, singledispatch
import itertools
import heapq
import bisect
import re
import math
import time
import inspect
from ..cache.sigcache import get_signature

if not hasattr(itertools, 'pairwise'):
    def _pairwise(iterable):
        a, b = itertools.tee(iterable)
        try:
            next(b)
        except StopIteration:
            pass
        return zip(a, b)
    itertools.pairwise = _pairwise

from ..data import Seq, NONE
from ..decorators import curry
from .arrow_func import g

__all__ = ['P', 'Ops', 'O']


def _pipe(*funcs):
    """Creates a pipeline function by composing multiple functions"""
    def _inn(source):
        return reduce(lambda x, f: f(x), funcs, source)
    return _inn


def _not(pred):
    return lambda *a, **k: not pred(*a, **k)


filter_not = _pipe(filter, _not)


def static_pipe1(f):
    return staticmethod(P(f, ix=1))


def static_pipe2(f):
    return staticmethod(P(f, ix=2))


def static_pipe3(f):
    return staticmethod(P(f, ix=3))


def static_pipe_last(f):
    return staticmethod(P(f, ix=-1))


def static_pipe_last2(f):
    return staticmethod(P(f, ix=-2))


def static_pipe_last3(f):
    return staticmethod(P(f, ix=-3))


class P:
    """Pipeable function wrapper - supports pipe operations via | operator"""
    
    __slots__ = ('func', 'args', 'kwargs', 'ix', 'factory', 'collect_factory')

    def __init__(self, func: Any, *args: Any, **kwargs: Any) -> None:
        ix = kwargs.pop('ix', 1)
        self.factory = kwargs.pop('factory', None)
        self.collect_factory = kwargs.pop('collect_factory', list)
        ix = int(ix)
        if ix not in (1, 2, 3, -1, -2, -3):
            raise ValueError("pipe param index must be 1,2,3 or -1,-2,-3")
        self.ix = ix
        if isinstance(func, str):
            self.func = g(func)
        else:
            self.func = func
        self.args = args or tuple()
        self.kwargs = kwargs or {}

    def __ror__(self, other: Any) -> 'P':
        """支持管道操作: other | P(func)"""
        if self.ix == 1:
            args = (other,) + self.args
        elif self.ix == 2:
            args = (self.args[0], other) + self.args[1:]
        elif self.ix == 3:
            args = (self.args[0], self.args[1], other) + self.args[2:]
        elif self.ix == -1:
            args = self.args + (other,)
        elif self.ix == -2:
            args = self.args[:-1] + (other, self.args[-1])
        elif self.ix == -3:
            args = self.args[:-2] + (other, self.args[-2], self.args[-1])
        else:
            raise ValueError("pipe param index must be 1,2,3")
        rs = self.func(*args, **self.kwargs)
        return self._apply_factory(rs)

    def __rrshift__(self, other: Iterable[Any]) -> 'P':
        """支持批量管道操作: iterable >> P(func)"""
        if not isinstance(other, Iterable):
            raise TypeError(f"unsupported operand type(s) for >>: '{type(other).__name__}' and 'P'")
        rs = ((x | self) for x in other)
        return self._apply_factory(rs)

    def __rshift__(self, other: Any) -> 'P':
        """支持管道组合: P(func1) >> P(func2)"""
        if isinstance(other, P):
            func = _pipe(self.func, other.func)
            k = self.kwargs.copy()
            k['ix'] = self.ix
            k['factory'] = other.factory if other.factory else self.factory
            return self.__class__(func, *self.args, *other.args, **k)
        elif callable(other):
            func = _pipe(self.func, other)
            k = self.kwargs.copy()
            k['ix'] = self.ix
            k['factory'] = self.factory
            return self.__class__(func, *self.args, **k)
        raise TypeError(f"unsupported operand type(s) for >>: 'P' and '{type(other).__name__}'")
    
    def _apply_factory(self, result: Any) -> Any:
        """Applies result transformation factories"""
        f = self.collect_factory
        if f and callable(f) and isinstance(result, Iterable) and not isinstance(result, str):
            result = f(result)
        if self.factory:
            return self.factory(result)
        return result
    
    def __call__(self, *a: Any, **k: Any) -> 'P':
        args = []
        for arg in a:
            if isinstance(arg, str):
                args.append(g(arg))
            else:
                args.append(arg)
        args = self.args + tuple(args)
        kwargs = self.kwargs.copy()
        kwargs['factory'] = self.factory
        kwargs['collect_factory'] = self.collect_factory
        kwargs.update(k)
        kwargs['ix'] = self.ix
        exe = kwargs.pop('exe', False)
        if exe:
            return self._apply_factory(self.func(*args, **kwargs))
        return self.__class__(self.func, *args, **kwargs)

    def __signature__(self) -> Any:
        return get_signature(self.func)

    def __name__(self) -> str:
        name = getattr(self.func, '__name__', None)
        return name or getattr(self.func, '__qualname__', '<unknown_func>')

    def __str__(self) -> str:
        return f"pipe_func<{self.__name__()}>params{self.__signature__()}<param_index={self.ix}>"


class Ops:
    """Functional operations registry"""
    __slots__ = ()

    def __getattr__(self, name: str) -> Callable[[Any], 'P']:
        if name.startswith('__'):
            raise AttributeError(name)
        def _apply(x: Any, *a: Any, **k: Any) -> Any:
            return getattr(x, name)(*a, **k)
        return P(_apply, ix=1)
    
    def __getitem__(self, key: Any) -> Callable[[Any], 'P']:
        def _apply(x: Any, *a: Any, **k: Any) -> Any:
            if callable(x):
                x = x(*a, **k)
            return x | self.__class__.get(key)
        return P(_apply, ix=1)
    
    def __call__(self, f: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(f, str):
            f = g(f)
        def _apply(x, *a, **k):
            return f(x, *a, **k)
        return P(_apply, ix=1)(*args, **kwargs)
    

    # ========== Core operations ==========
    where = filter = static_pipe2(filter)
    filter_not = static_pipe2(filter_not)
    map = select = static_pipe2(map)
    zip = static_pipe1(zip)
    enumerate = static_pipe1(enumerate)
    sorted = static_pipe1(sorted)
    reversed = static_pipe1(reversed)
    all = static_pipe1(all)
    any = static_pipe1(any)
    sum = static_pipe1(sum)
    add = static_pipe1(lambda a, b: a + b)
    mul = static_pipe1(lambda a, b: a * b)
    sub = static_pipe1(lambda a, b: a - b)
    div = static_pipe1(lambda a, b: a / b)
    mod = static_pipe1(lambda a, b: a % b)
    pow = static_pipe1(lambda a, b: a ** b)
    neg = static_pipe1(lambda a: -a)
    abs = static_pipe1(abs)

    starmap = static_pipe2(itertools.starmap)
    reduce = static_pipe2(reduce)
    accumulate = static_pipe1(itertools.accumulate)
    chain = static_pipe1(itertools.chain)
    compress = static_pipe2(itertools.compress)
    cycle = static_pipe1(itertools.cycle)
    dropwhile = static_pipe2(itertools.dropwhile)
    filterfalse = static_pipe2(itertools.filterfalse)
    groupby = static_pipe1(itertools.groupby)
    pairwise = static_pipe1(itertools.pairwise)
    product = static_pipe1(itertools.product)
    tee = static_pipe1(itertools.tee)
    zip_longest = static_pipe1(itertools.zip_longest)

    # heapq
    heapify = static_pipe1(heapq.heapify)
    heappop = static_pipe1(heapq.heappop)
    heappush = static_pipe1(heapq.heappush)
    heapreplace = static_pipe1(heapq.heapreplace)
    heapmerge = static_pipe2(heapq.merge)
    nlargest = static_pipe2(heapq.nlargest)
    nsmallest = static_pipe2(heapq.nsmallest)

    # bisect
    bisect_left = static_pipe1(bisect.bisect_left)
    bisect_right = static_pipe1(bisect.bisect_right)
    insort_left = static_pipe1(bisect.insort_left)
    insort_right = static_pipe1(bisect.insort_right)

    # re
    regexp_match = rlike = static_pipe2(re.match)
    regexp_search = static_pipe2(re.search)
    regexp_replace = static_pipe3(re.sub)
    regexp_fullmatch = static_pipe2(re.fullmatch)
    regexp_split = static_pipe2(re.split)
    regexp_findall = static_pipe2(re.findall)
    regexp_finditer = static_pipe2(re.finditer)

    @static_pipe1
    def flatten(it: Iterable[Iterable[Any]]) -> Any:
        return (x for xs in it for x in xs)

    @static_pipe1
    def flat_map(it: Iterable[Any], func: Callable[[Any], Iterable[Any]]) -> Any:
        return (x for xs in it for x in func(xs))

    @static_pipe1
    def fold(it: Iterable[Any], init: Any, binop: Callable[[Any, Any], Any]) -> Any:
        return reduce(binop, it, init)

    @static_pipe1
    def each(it: Iterable[Any], func: Callable[..., Any] = print, *args: Any, **kwargs: Any) -> List[Any]:
        need_result = kwargs.pop('need_result', False)

        def gen():
            for x in it:
                rs = func(x, *args, **kwargs)
                yield rs if need_result else x
        return list(gen())

    @static_pipe1
    def get(obj: Any, key: Any, default: Any = None) -> Any:
        if isinstance(obj, dict):
            if isinstance(key, (str, int, frozenset, tuple)):
                return obj.get(key, default)
            elif isinstance(key, Iterable):
                return [(obj | Ops.get(k, default)) for k in key]
            else:
                raise TypeError(f"unsupported key type: '{type(key).__name__}'")
        elif isinstance(obj, Iterable):
            if isinstance(key, (int, slice)):
                try:
                    return list(obj)[key]
                except IndexError:
                    return default
            elif isinstance(key, Iterable):
                return [(obj | Ops.get(k, default)) for k in key]
            else:
                raise TypeError(f"unsupported key type: '{type(key).__name__}'")
        else:
            if isinstance(key, str):
                return getattr(obj, key, default)
            else:
                raise TypeError(f"unsupported key type: '{type(key).__name__}'")

    @static_pipe1
    def do(x: Any, func: Callable[..., Any] = print, *args: Any, **kwargs: Any) -> Any:
        need_result = kwargs.pop('need_result', False)
        rs = func(x, *args, **kwargs)
        return rs if need_result else x

    @static_pipe1
    def interval(func: Callable[..., Any], interval: float = 5, terminate: Optional[Callable[[Any], bool]] = None, *args: Any, **kwargs: Any) -> None:
        while True:
            rs = func(*args, **kwargs)
            time.sleep(interval)
            if terminate and terminate(rs):
                break

    # Collection operations
    @static_pipe1
    def count(it: Iterable[Any]) -> int:
        return sum(1 for _ in it)

    @static_pipe1
    def distinct(it: Iterable[Any]) -> List[Any]:
        seen = set()
        result = []
        for item in it:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    @static_pipe2
    def take(n: int, it: Iterable[Any]) -> List[Any]:
        return list(itertools.islice(it, n))

    @static_pipe2
    def drop(n: int, it: Iterable[Any]) -> List[Any]:
        return list(itertools.islice(it, n, None))

    @static_pipe2
    def take_while(pred: Callable[[Any], bool], it: Iterable[Any]) -> List[Any]:
        return list(itertools.takewhile(pred, it))

    @static_pipe2
    def drop_while(pred: Callable[[Any], bool], it: Iterable[Any]) -> List[Any]:
        return list(itertools.dropwhile(pred, it))

    @static_pipe2
    def partition(pred: Callable[[Any], bool], it: Iterable[Any]) -> Tuple[List[Any], List[Any]]:
        true_vals = []
        false_vals = []
        for item in it:
            if pred(item):
                true_vals.append(item)
            else:
                false_vals.append(item)
        return true_vals, false_vals

    # Mathematical operations
    prod = static_pipe1(lambda it: reduce(lambda x, y: x * y, it, 1))
    mean = static_pipe1(lambda it: sum(it) / sum(1 for _ in it))
    min = static_pipe1(min)
    max = static_pipe1(max)

    # String operations
    @static_pipe1
    def split(x: str, sep: Optional[str] = None, maxsplit: int = -1) -> List[str]:
        return x.split(sep, maxsplit)

    @static_pipe1
    def join(it: Iterable[Any], sep: str) -> str:
        @singledispatch
        def _join(it: Iterable, sep):
            return sep.join(str(x) for x in it)

        @_join.register(str)
        def _(sep: str, it):
            return sep.join(str(x) for x in it)

        return _join(it, sep)
    
    @static_pipe1
    def upper(s: str) -> str:
        return s.upper()

    @static_pipe1
    def lower(s: str) -> str:
        return s.lower()

    @static_pipe1
    def title(s: str) -> str:
        return s.title()

    @static_pipe1
    def capitalize(s: str) -> str:
        return s.capitalize()

    @static_pipe1
    def strip(s: str, chars: Optional[str] = None) -> str:
        return s.strip(chars)

    @static_pipe1
    def lstrip(s: str, chars: Optional[str] = None) -> str:
        return s.lstrip(chars)

    @static_pipe1
    def rstrip(s: str, chars: Optional[str] = None) -> str:
        return s.rstrip(chars)

    @static_pipe1
    def replace(s: str, old: str, new: str, count: int = -1) -> str:
        return s.replace(old, new, count)

    # Mathematical functions
    sqrt = static_pipe1(math.sqrt)
    sin = static_pipe1(math.sin)
    cos = static_pipe1(math.cos)
    tan = static_pipe1(math.tan)
    log = static_pipe1(math.log)
    exp = static_pipe1(math.exp)
    ceil = static_pipe1(math.ceil)
    floor = static_pipe1(math.floor)

    # Utility operations
    @static_pipe1
    def inc(x: Any) -> Any:
        return x + 1

    @static_pipe1
    def dec(x: Any) -> Any:
        return x - 1

    @static_pipe1
    def identity(x: Any) -> Any:
        return x

    @static_pipe1
    def round(x: float, ndigits: Optional[int] = None) -> Any:
        return round(x, ndigits)

    # Factory methods
    @staticmethod
    def pipe(func: Callable[..., Any], *args: Any, **kwargs: Any) -> 'P':
        return P(func, *args, **kwargs)

    @staticmethod
    def pipe_last(func: Callable[..., Any], *args: Any, **kwargs: Any) -> 'P':
        return P(func, *args, **kwargs, ix=-1)

    @staticmethod
    def pipe_last2(func: Callable[..., Any], *args: Any, **kwargs: Any) -> 'P':
        return P(func, *args, **kwargs, ix=-2)

    @staticmethod
    def pipe_last3(func: Callable[..., Any], *args: Any, **kwargs: Any) -> 'P':
        return P(func, *args, **kwargs, ix=-3)

    @staticmethod
    def pipe_first(func: Callable[..., Any], *args: Any, **kwargs: Any) -> 'P':
        return P(func, *args, **kwargs, ix=1)

    @staticmethod
    def pipe_second(func: Callable[..., Any], *args: Any, **kwargs: Any) -> 'P':
        return P(func, *args, **kwargs, ix=2)

    @staticmethod
    def pipe_third(func: Callable[..., Any], *args: Any, **kwargs: Any) -> 'P':
        return P(func, *args, **kwargs, ix=3)

    @static_pipe1
    def accum(it: Iterable[Any], func: Callable[[Any, Any], Any], initial: Any = None) -> Any:
        return Seq(it).accum(func, initial)

    @static_pipe1
    def take_while(it: Iterable[Any], func: Callable[[Any], bool]) -> List[Any]:
        return Seq(it).take_while(func)

    @static_pipe1
    def drop_while(it: Iterable[Any], func: Callable[[Any], bool]) -> List[Any]:
        return Seq(it).drop_while(func)

    @static_pipe1
    def as_list(it: Iterable[Any]) -> List[Any]:
        return Seq(it).as_list()

    @static_pipe1
    def flatmap_ex(it: Iterable[Any], before_func: Optional[Callable[[Any], Any]] = None, after_func: Optional[Callable[[Any], Any]] = None) -> List[Any]:
        return Seq(it).flatmap_ex(before_func, after_func)

    @static_pipe1
    def register(it: Iterable[Any], func: Callable[[Any], Any]) -> Iterable[Any]:
        return Seq(it).register(func)

    @static_pipe1
    def run(it: Iterable[Any], func: Callable[[Any], Any]) -> Iterable[Any]:
        return Seq(it).run(func)

    @static_pipe1
    def find(it: Iterable[Any], func: Optional[Callable[[Any], bool]] = None) -> Optional[Any]:
        return Seq(it).find(func)

    @static_pipe1
    def find_index(it: Iterable[Any], func: Optional[Callable[[Any], bool]] = None) -> Optional[int]:
        return Seq(it).find_index(func)

    @static_pipe1
    def count_by(it: Iterable[Any], key: Optional[Callable[[Any], Any]] = None) -> Any:
        return Seq(it).count_by(key)

    @static_pipe1
    def reduce_by(it: Iterable[Any], key: Optional[Callable[[Any], Any]] = None, func: Optional[Callable[[Any, Any], Any]] = None) -> Any:
        return Seq(it).reduce_by(key, func)

    @static_pipe1
    def group_by(it: Iterable[Any], key: Optional[Callable[[Any], Any]] = None) -> Any:
        return Seq(it).group_by(key)

    @static_pipe1
    def grouper(it: Iterable[Any], n: int, fillvalue: Any = None) -> Any:
        return Seq(it).grouper(n, fillvalue)

    @static_pipe1    
    def sort_by(it: Iterable[Any], key: Optional[Callable[[Any], Any]] = None, reverse: bool = False) -> List[Any]:
        return Seq(it).sort_by(key, reverse)

    @static_pipe1
    def reverse(it: Iterable[Any]) -> List[Any]:
        return Seq(it).reverse()


O = Ops()
