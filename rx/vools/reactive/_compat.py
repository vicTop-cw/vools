"""
vools.reactive internal compatibility layer.

Provides minimal implementations of utilities previously imported from
vools.decorators, vools.functional and vools.data, so that the reactive
sub-package can be distributed independently as vools-rx without depending
on the rest of the vools package.
"""

import builtins
import inspect
import re
from functools import reduce as _reduce
from itertools import groupby
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, TypeVar

__all__ = ['curry', 'lazy', 'g', 'iif', 'Seq']

T = TypeVar('T')
K = TypeVar('K')


# =============================================================================
# curry
# =============================================================================

class _Curried:
    """Lightweight curried wrapper supporting partial application."""

    __slots__ = ('func', 'bound_args', 'bound_kwargs', '_name', '_doc')

    def __init__(self, func: Callable, bound_args: Tuple[Any, ...] = (),
                 bound_kwargs: Optional[Dict[str, Any]] = None) -> None:
        self.func = func
        self.bound_args = bound_args
        self.bound_kwargs = bound_kwargs or {}
        self._name = getattr(func, '__name__', '<curried>')
        self._doc = getattr(func, '__doc__', None)

    @property
    def __name__(self) -> str:
        return self._name

    @__name__.setter
    def __name__(self, value: str) -> None:
        self._name = value

    @property
    def __doc__(self) -> Optional[str]:
        return self._doc

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        new_args = self.bound_args + args
        new_kwargs = {**self.bound_kwargs, **kwargs}

        try:
            sig = inspect.signature(self.func)
        except (ValueError, TypeError):
            return self.func(*new_args, **new_kwargs)

        params = sig.parameters
        required = [
            name for name, param in params.items()
            if param.default is inspect.Parameter.empty
            and param.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        ]

        provided = set(new_kwargs.keys())
        pos_params = [
            name for name, param in params.items()
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and name not in provided
        ]
        for i, _ in enumerate(new_args):
            if i < len(pos_params):
                provided.add(pos_params[i])

        if all(name in provided for name in required):
            return self.func(*new_args, **new_kwargs)

        return _Curried(self.func, new_args, new_kwargs)


def curry(func: Optional[Callable] = None, *args: Any, **kwargs: Any) -> Any:
    """Minimal curry decorator."""
    if func is None:
        return lambda f: _Curried(f, args, kwargs)
    return _Curried(func, args, kwargs)


# =============================================================================
# lazy
# =============================================================================

_SAFE_BUILTINS = [
    'abs', 'all', 'any', 'bool', 'bytes', 'chr', 'complex', 'dict',
    'divmod', 'enumerate', 'filter', 'float', 'format', 'frozenset',
    'hash', 'hex', 'int', 'isinstance', 'issubclass', 'iter', 'len',
    'list', 'map', 'max', 'min', 'next', 'oct', 'ord', 'pow', 'range',
    'repr', 'reversed', 'round', 'set', 'slice', 'sorted', 'str', 'sum',
    'tuple', 'zip', 'print', 'Exception'
]


def lazy(obj: Any, caller_locals: Optional[Dict] = None,
         caller_globals: Optional[Dict] = None) -> Callable:
    """Minimal lazy evaluator."""
    if callable(obj):
        return obj

    if isinstance(obj, str):
        if caller_globals is None or caller_locals is None:
            try:
                frame = inspect.currentframe().f_back.f_back
                caller_globals = frame.f_globals if frame else globals()
                caller_locals = frame.f_locals if frame else locals()
            except (AttributeError, TypeError):
                caller_globals = globals()
                caller_locals = locals()

        safe_globals = {
            **(caller_globals or {}),
            '__builtins__': {k: getattr(builtins, k) for k in _SAFE_BUILTINS}
        }
        safe_locals = caller_locals or {}

        if obj.startswith('def '):
            match = re.search(r'def\s+(\w+)\s*\(', obj)
            func_name = match.group(1) if match else '__anonymous__'
            exec(obj, safe_globals, safe_locals)
            func = safe_locals.get(func_name, safe_globals.get(func_name))
            wrapper = lambda: func
            wrapper._is_lazy = True
            return wrapper

        if obj.startswith('->') or obj.startswith('=>'):
            expr = obj[2:]
            def _anonymous():
                return eval(expr, safe_globals, safe_locals)
            _anonymous._is_lazy = True
            return _anonymous

        arrow_match = re.search(r'(.*?)(->|=>)(.*)', obj)
        if arrow_match:
            left, _, right = arrow_match.groups()
            params = [p.strip() for p in left.split(',') if p.strip()]
            func_str = f"def __anonymous({', '.join(params)}):\n    return {right.strip()}"
            exec(func_str, safe_globals, safe_locals)
            wrapper = safe_locals.get('__anonymous')
            wrapper._is_lazy = True
            return wrapper

    def _constant_wrapper():
        return obj

    _constant_wrapper._is_lazy = True
    return _constant_wrapper


# =============================================================================
# arrow expression parser (g)
# =============================================================================

def g(expr: str, env: Optional[Dict[str, Any]] = None) -> Callable:
    """Minimal arrow expression parser."""
    if env is None:
        env = {}
    env = dict(env)
    if '__builtins__' not in env:
        env['__builtins__'] = __builtins__

    expr = expr.strip()

    match = re.match(r'^\s*(.*?)\s*(=>|->)\s*(.+)$', expr, re.DOTALL)
    if match:
        params_str, _, body = match.groups()
        params = [p.strip() for p in params_str.split(',') if p.strip()]
        func_str = f"def __arrow_func({', '.join(params)}):\n    return {body.strip()}"
        local_env: Dict[str, Any] = {}
        exec(func_str, env, local_env)
        return local_env['__arrow_func']

    if expr.startswith('lambda'):
        return eval(expr, env)

    return lambda: eval(expr, env)


# =============================================================================
# iif
# =============================================================================

_UNSET = object()


class _ConditionBuilder:
    """Minimal condition builder for iif."""

    _OPERATORS = {
        '==': lambda x, y: x == y,
        '!=': lambda x, y: x != y,
        '>':  lambda x, y: x > y,
        '>=': lambda x, y: x >= y,
        '<':  lambda x, y: x < y,
        '<=': lambda x, y: x <= y,
        'in': lambda x, y: x in y,
    }

    def __init__(self, base_value: Any, comp: Callable = '==') -> None:
        self.base = base_value
        self._comp = self._OPERATORS.get(comp, comp if callable(comp) else self._OPERATORS['=='])
        self._conditions: List[Tuple[Callable, Any]] = []
        self._default: Any = _UNSET
        self._chain_locked = False

    def case(self, value: Any, result: Any) -> '_ConditionBuilder':
        if self._chain_locked:
            raise RuntimeError("chain locked by otherwise()")
        self._conditions.append((self._create_condition(value), result))
        return self

    def when(self, value: Any, result: Any, logic: Optional[str] = None) -> '_ConditionBuilder':
        if self._chain_locked:
            raise RuntimeError("chain locked by otherwise()")
        cond = self._create_condition(value)
        if logic is None or not self._conditions:
            self._conditions.append((cond, result))
        else:
            prev_cond, _ = self._conditions[-1]
            if logic == 'and':
                new_cond = lambda x, pc=prev_cond, cf=cond: pc(x) and cf(x)
            elif logic == 'or':
                new_cond = lambda x, pc=prev_cond, cf=cond: pc(x) or cf(x)
            else:
                raise ValueError(f"unsupported logic: {logic}")
            self._conditions[-1] = (new_cond, result)
        return self

    def default(self, value: Any) -> '_ConditionBuilder':
        if self._chain_locked:
            raise RuntimeError("chain locked by otherwise()")
        self._default = value
        return self

    def otherwise(self, value: Any) -> '_ConditionBuilder':
        self._default = value
        self._chain_locked = True
        return self

    def _create_condition(self, value: Any) -> Callable:
        if callable(value):
            return value
        return lambda x, v=value: self._comp(x, v)

    def _execute_single(self, target: Any) -> Any:
        for cond, result in self._conditions:
            if cond(target):
                return result(target) if callable(result) else result
        if self._default is not _UNSET:
            return self._default(target) if callable(self._default) else self._default
        return None

    def __call__(self, value: Any = _UNSET, data: Any = None) -> Any:
        target = data if data is not None else (value if value is not _UNSET else self.base)
        return self._execute_single(target)


def iif(condition: Any = None, true_body: Any = None, false_body: Any = None,
        data: Any = None, supp: bool = True, whens: Optional[List[Tuple[Any, ...]]] = None) -> Any:
    """Minimal iif implementation for reactive usage."""
    if condition is None and true_body is None and whens is None:
        return _ConditionBuilder(None)

    if whens is not None:
        cb = _ConditionBuilder(data if data is not None else condition)
        for w in whens:
            if not isinstance(w, (list, tuple)):
                raise TypeError(f"whens item must be list or tuple, got {type(w).__name__}")
            if len(w) == 2:
                cb.when(w[0], w[1])
            elif len(w) == 3:
                cb.when(w[0], w[1], w[2])
            else:
                raise ValueError(f"whens item length must be 2 or 3, got {len(w)}")
        return cb(data)

    if data is None:
        cond_result = condition() if callable(condition) else bool(condition)
        result = true_body if cond_result else false_body
        return result() if callable(result) else result

    if callable(condition):
        cond_result = condition(data)
    elif isinstance(condition, str):
        cond_result = _eval_string_condition(condition, data)
    else:
        cond_result = bool(condition) if condition is not None else False

    result = true_body if cond_result else (false_body if false_body is not None else None)
    if callable(result):
        return result(data)
    return result


def _eval_string_condition(condition: str, data: Any) -> bool:
    expr = condition[2:] if condition.startswith('->') else condition
    try:
        func = eval(f"lambda x: {expr}", {"__builtins__": {}}, {})
        return bool(func(data))
    except Exception:
        return bool(condition)


# =============================================================================
# Seq
# =============================================================================

class Seq:
    """Minimal Seq compatible wrapper for seq_bridge."""

    def __init__(self, iterable: Iterable[Any] = ()) -> None:
        if isinstance(iterable, Seq):
            self._data: List[Any] = list(iterable._data)
        else:
            self._data = list(iterable)

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, index):
        return self._data[index]

    def __repr__(self) -> str:
        return f"Seq({self._data!r})"

    def __bool__(self) -> bool:
        return bool(self._data)

    def map(self, func: Callable[[T], Any]) -> 'Seq':
        return Seq(map(func, self._data))

    def filter(self, func: Callable[[T], bool]) -> 'Seq':
        return Seq(filter(func, self._data))

    def reduce(self, func: Callable[[Any, T], Any], initial: Any = _UNSET) -> Any:
        if initial is _UNSET:
            return _reduce(func, self._data)
        return _reduce(func, self._data, initial)

    def distinct(self, key: Optional[Callable[[T], K]] = None) -> 'Seq':
        seen: set = set()
        result: List[T] = []
        for item in self._data:
            k = item if key is None else key(item)
            if k not in seen:
                seen.add(k)
                result.append(item)
        return Seq(result)

    def sort_by(self, key: Optional[Callable[[T], Any]] = None, reverse: bool = False) -> 'Seq':
        return Seq(sorted(self._data, key=key, reverse=reverse))

    def sorted(self, key: Optional[Callable[[T], Any]] = None, reverse: bool = False) -> List[T]:
        return sorted(self._data, key=key, reverse=reverse)

    def reverse(self) -> 'Seq':
        return Seq(reversed(self._data))

    def group_by(self, key: Optional[Callable[[T], K]] = None) -> 'Seq':
        if key is None:
            key = lambda x: x
        sorted_data = sorted(self._data, key=key)
        return Seq((k, list(g)) for k, g in groupby(sorted_data, key=key))

    def count_by(self, key: Optional[Callable[[T], K]] = None) -> 'Seq':
        return self.group_by(key).map(lambda kg: (kg[0], len(kg[1])))

    def grouper(self, n: int, fillvalue: Any = None) -> 'Seq':
        from itertools import zip_longest
        args = [iter(self._data)] * n
        return Seq(zip_longest(*args, fillvalue=fillvalue))

    def prepend(self, *args: Any) -> 'Seq':
        from itertools import chain
        items = []
        for a in args:
            items.extend(iter(a) if isinstance(a, Iterable) and not isinstance(a, (str, bytes)) else [a])
        return Seq(chain(items, self._data))

    def extend(self, *args: Any) -> 'Seq':
        from itertools import chain
        items = []
        for a in args:
            items.extend(iter(a) if isinstance(a, Iterable) and not isinstance(a, (str, bytes)) else [a])
        return Seq(chain(self._data, items))

    def add(self, *args: Any, **kwargs: Any) -> 'Seq':
        from itertools import chain
        return Seq(chain(self._data, args, kwargs.values()))

    def any(self, func: Optional[Callable[[T], bool]] = None) -> bool:
        return any(func(x) for x in self._data) if func else any(self._data)

    def all(self, func: Optional[Callable[[T], bool]] = None) -> bool:
        return all(func(x) for x in self._data) if func else all(self._data)

    def to_list(self) -> List[T]:
        return list(self._data)

    @property
    def unique(self) -> List[T]:
        seen: set = set()
        result: List[T] = []
        for item in self._data:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result
