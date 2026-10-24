from functools import partial, reduce, wraps as _wraps
from collections.abc import Iterable
from .arrow_func import g
from ..core.base import VoolsBase
from datetime import datetime
from typing import Any, Callable, Optional, Union, TypeVar, List

__all__ = ['box', 'Box', 'setattr_box']

R = TypeVar('R')


class _ObjectProxy:
    """Simple ObjectProxy implementation for Python 3.6+ compatibility.
    
    Wraps an object and delegates most operations to the wrapped object.
    """
    def __init__(self, wrapped):
        object.__setattr__(self, '__wrapped__', wrapped)
    
    def __getattr__(self, name):
        return getattr(self.__wrapped__, name)
    
    def __setattr__(self, name, value):
        setattr(self.__wrapped__, name, value)
    
    def __delattr__(self, name):
        delattr(self.__wrapped__, name)
    
    def __repr__(self):
        return repr(self.__wrapped__)
    
    def __str__(self):
        return str(self.__wrapped__)
    
    def __bytes__(self):
        return bytes(self.__wrapped__)
    
    def __hash__(self):
        return hash(self.__wrapped__)
    
    def __bool__(self):
        return bool(self.__wrapped__)
    
    def __int__(self):
        return int(self.__wrapped__)
    
    def __float__(self):
        return float(self.__wrapped__)
    
    def __complex__(self):
        return complex(self.__wrapped__)
    
    def __index__(self):
        return self.__wrapped__.__index__() if hasattr(self.__wrapped__, '__index__') else int(self.__wrapped__)
    
    def __eq__(self, other):
        if isinstance(other, _ObjectProxy):
            return self.__wrapped__ == other.__wrapped__
        return self.__wrapped__ == other
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def __lt__(self, other):
        if isinstance(other, _ObjectProxy):
            return self.__wrapped__ < other.__wrapped__
        return self.__wrapped__ < other
    
    def __le__(self, other):
        if isinstance(other, _ObjectProxy):
            return self.__wrapped__ <= other.__wrapped__
        return self.__wrapped__ <= other
    
    def __gt__(self, other):
        if isinstance(other, _ObjectProxy):
            return self.__wrapped__ > other.__wrapped__
        return self.__wrapped__ > other
    
    def __ge__(self, other):
        if isinstance(other, _ObjectProxy):
            return self.__wrapped__ >= other.__wrapped__
        return self.__wrapped__ >= other
    
    def __call__(self, *args, **kwargs):
        return self.__wrapped__(*args, **kwargs)
    
    def __len__(self):
        return len(self.__wrapped__)
    
    def __iter__(self):
        return iter(self.__wrapped__)
    
    def __contains__(self, item):
        return item in self.__wrapped__
    
    def __getitem__(self, key):
        return self.__wrapped__[key]
    
    def __setitem__(self, key, value):
        self.__wrapped__[key] = value
    
    def __delitem__(self, key):
        del self.__wrapped__[key]
    
    def __enter__(self):
        return self.__wrapped__.__enter__()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.__wrapped__.__exit__(exc_type, exc_val, exc_tb)


# 用别名保持与原代码的接口一致
AOP = _ObjectProxy


_RETURN_TYPE_RESTRICTED_METHODS = {
    '__bool__', '__len__', '__hasattr__', '__contains__',
    '__int__', '__float__', '__complex__', '__index__', '__iter__',
    '__str__', '__repr__', '__format__', '__bytes__', '__fspath__', '__qualname__', '__name__',
    '__hash__',
    '__aiter__', '__anext__', '__await__', '__aenter__', '__aexit__',
    '__ceil__', '__floor__', '__trunc__',
    '__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__',
    '__length_hint__',
}

_MUST_RETURN_NONE = {
    '__setattr__', '__delattr__', '__setitem__', '__delitem__',
    '__set__', '__delete__', '__init__'
}

_OTHER_LIMITATIONS = {
    '__get__',
    '__class__',
    '__dict__',
    '__slots__',
    '__init_class__',
    '__is_subclass__',
    '__getattribute__',
    '__init_subclass__',
    '__subclasshook__',
    '__instancecheck__',
    '__subclasscheck__',
    '__class_getitem__'
}

_is_iterable = lambda obj: isinstance(obj, Iterable) and not isinstance(obj, (str, bytes, bytearray, memoryview))


def _get_methods(type_name):
    """获取指定类型的方法列表（延迟加载避免循环导入）"""
    methods = {}
    types_map = {
        'dict': dict,
        'list': list,
        'str': str,
        'datetime': datetime,
    }
    if type_name in types_map:
        methods = {m: getattr(types_map[type_name], m) for m in dir(types_map[type_name]) if not m.startswith('_')}
    return methods


def box(func: Optional[Callable[..., R]] = None, *, signature_from: Optional[Callable[..., Any]] = None) -> Union[Callable[[Callable[..., R]], Callable[..., 'Box']], Callable[..., 'Box']]:
    """将函数返回值包装为 Box 对象，支持链式调用。
    
    支持两种用法：
    1. 装饰器用法：@box 或 @box(signature_from=...)
    2. 函数调用用法：box(some_func)
    
    Args:
        func: 要包装的函数（装饰器用法时为 None）
        signature_from: 可选，从该函数复制签名信息
        
    Returns:
        装饰后的函数或直接返回 Box 对象
    """
    def _box(wrapped):
        @_wraps(wrapped)
        def wrapper(*args, **kwargs):
            def _nobox(obj):
                if isinstance(obj, Box):
                    return obj.__wrapped__
                else:
                    return obj
            # BUG-140: 必须在解箱之前捕获 Box 实参，否则返回 None 时
            # 无法找回原 Box（args 解箱后 isinstance(..., Box) 恒 False）。
            box_args = [a for a in args if isinstance(a, Box)]
            box_kwargs = [v for v in kwargs.values() if isinstance(v, Box)]
            args = list(map(_nobox, args))
            kwargs = {k: _nobox(v) for k, v in kwargs.items()}
            rs = wrapped(*args, **kwargs)
            if rs is None:
                # 当被装饰的函数返回 None 时，返回包装它的 Box 实例以支持链式调用
                # 优先返回第一个 Box 实参
                if box_args:
                    return box_args[0]
                if box_kwargs:
                    return box_kwargs[0]
                if hasattr(wrapper, '__wrapped__') and isinstance(wrapper.__wrapped__, Box):
                    return wrapper.__wrapped__
                return None
            if isinstance(rs, Box):
                return rs
            
            # 延迟导入避免循环导入
            from ..data.vlist import VList as vicList
            from ..datetime.vdate_class import VDate as vicDate
            from ..data.vtext import VText as vicText
            
            # 使用对应的 vic 类包装返回值
            if isinstance(rs, str):
                return Box(vicText(rs))
            elif isinstance(rs, list):
                return Box(vicList(rs))
            elif isinstance(rs, datetime):
                return Box(vicDate(rs))
            elif isinstance(rs, (tuple, set)):
                return Box(vicList(rs))
            elif isinstance(rs, (int, float, bool, bytes, bytearray, slice, complex, type, object)):
                return Box(rs)
            elif isinstance(rs, Iterable) and not isinstance(rs, (str, bytes)):
                return Box(vicList(list(rs)))
            else:
                return Box(rs)
        return wrapper

    if func is None:
        return _box
    else:
        wrapped = _box(func)
        if signature_from is not None:
            try:
                from functools import update_wrapper
                update_wrapper(wrapped, signature_from)
            except ValueError:
                pass
        return wrapped


@box
def __box_wrapped_call__(self, *args, **kwargs):
    """内部函数，用于处理被 Box 包装的可调用对象的调用。
    
    当通过 __call__ 描述符访问时，实际调用此函数。
    
    Args:
        self: Box 实例
        *args: 位置参数
        **kwargs: 关键字参数
        
    Returns:
        调用结果
    """
    if callable(self):
        return self(*args, **kwargs)
    if not callable(self.__wrapped__):
        raise TypeError(f"'{type(self).__name__}' object is not callable")
    return self.__wrapped__(*args, **kwargs)


class CallableDescriptor(VoolsBase):
    """描述符，控制 __call__ 属性的访问。
    
    用于 Box 类，使其可以像函数一样被调用。
    只有当 __wrapped__ 是可调用对象时，__call__ 才可用。
    """
    def __init__(self) -> None:
        """初始化描述符，禁用状态默认为 False。"""
        self.enabled = False

    def __get__(self, instance, owner):
        if instance is None:
            raise AttributeError("Can only be accessed from an instance")
        if isinstance(instance, Box):
            if callable(instance.__wrapped__):
                self.enable()
            else:
                self.disable()

        if not self.enabled:
            raise TypeError(f"'{type(instance).__name__}' object is not callable")
        return partial(__box_wrapped_call__, instance)

    def enable(self) -> None:
        """启用 __call__ 功能，使 Box 实例可被调用。"""
        self.enabled = True

    def disable(self) -> None:
        """禁用 __call__ 功能，使 Box 实例不可被调用。"""
        self.enabled = False

class Box(AOP):

    __call__ = CallableDescriptor()

    @staticmethod
    def _is_indexable(base):
        """BUG-343: 是否为「可按下标访问」的序列。

        原实现只认 `isinstance(base, (list, tuple))`，但 `_box` 会把函数返回值
        包装成 vools 类型（list -> VList、str -> VText、datetime -> VDate），
        这些类型**支持下标但都不是 list 子类**，导致 Box 自己的产物无法索引：
        `b[0]` / `b._1` / `b[0:2]` 全部抛 "类型 'VList' 不支持数字索引"。
        改为鸭子类型：有 __getitem__ 与 __len__ 且不是 dict 即视为序列。
        """
        return (
            not isinstance(base, dict)
            and hasattr(base, '__getitem__')
            and hasattr(base, '__len__')
        )

    def _get_keys(self):
        """获取 __wrapped__ 的键列表（支持 dict 和任意可索引序列）"""
        base = self.__wrapped__
        if isinstance(base, dict):
            return list(base.keys())
        if self._is_indexable(base):
            return list(range(len(base)))
        return None

    def _getitem_by_index(self, index):
        """根据数字索引获取值"""
        base = self.__wrapped__
        if isinstance(base, dict):
            keys = list(base.keys())
            n = len(keys)
            if index < 0:
                index = n + index
            if index < 0 or index >= n:
                raise IndexError(f"索引 {index} 超出范围 [0, {n-1}] 或 [-{n}, -1]")
            return base[keys[index]]
        elif self._is_indexable(base):
            n = len(base)
            if index < 0:
                index = n + index
            if index < 0 or index >= n:
                raise IndexError(f"索引 {index} 超出范围 [0, {n-1}] 或 [-{n}, -1]")
            return base[index]
        raise TypeError(f"类型 '{type(base).__name__}' 不支持数字索引")

    def _getitem_by_slice(self, key):
        """根据切片获取子字典或子列表"""
        base = self.__wrapped__
        if isinstance(base, dict):
            keys = list(base.keys())
            sliced_keys = keys[key]
            if isinstance(sliced_keys, list):
                return Box({k: base[k] for k in sliced_keys})
            else:
                return Box({sliced_keys: base[sliced_keys]})
        elif self._is_indexable(base):
            return Box(base[key])
        raise TypeError(f"类型 '{type(base).__name__}' 不支持切片")

    def __getitem__(self, key):
        """支持数字索引和切片访问"""
        if isinstance(key, slice):
            return self._getitem_by_slice(key)
        elif isinstance(key, int):
            return self._getitem_by_index(key)
        else:
            base = self.__wrapped__
            if hasattr(base, '__getitem__'):
                return Box(base[key])
            raise TypeError(f"类型 '{type(base).__name__}' 不支持索引访问")

    def __getattr__(self, name):
        """支持 _1, _2, ... 等属性访问（数字索引）"""
        base = self.__wrapped__

        if name.startswith('_') and len(name) > 1 and name[1:].isdigit():
            index = int(name[1:]) - 1
            return self._getitem_by_index(index)

        # BUG-349: `__hasattr__` 文档承诺支持 `_-1` 等负索引属性，但 `__getattr__`
        # 只有正索引分支 —— `b.__hasattr__('_-1')` 为 True 而 `b._-1` 抛
        # AttributeError。补齐负索引（_getitem_by_index 本身已支持负值）。
        if name.startswith('_-') and name[2:].isdigit():
            return self._getitem_by_index(-int(name[2:]))

        if name in ('copy', 'map', 'filter', 'reduce', 'run', '_get_keys', '_getitem_by_index', '_getitem_by_slice'):
            return getattr(type(self), name).__get__(self, type(self))

        if name.startswith('_') and not name.startswith('__'):
            if name[1:].isdigit():
                index = int(name[1:]) - 1
                return self._getitem_by_index(index)

        if not self.__hasattr__(name):
            raise AttributeError(f"type object '{type(self).__name__}' has no attribute '{name}'")

        if hasattr(base, name):
            attr = getattr(base, name)
            if callable(attr) and name not in _RETURN_TYPE_RESTRICTED_METHODS:
                if name in ['append', 'extend', 'insert', 'remove', 'pop', 'clear', 'reverse', 'sort',
                            'update', 'setdefault', 'popitem', '__setitem__', '__delitem__']:
                    def inplace_wrapper(*args, **kwargs):
                        attr(*args, **kwargs)
                        return self
                    return inplace_wrapper
                @box
                def wrapper(*args, **kwargs):
                    return attr(*args, **kwargs)
                return wrapper
            return attr

        if isinstance(base, dict):
            methods = _get_methods('dict')
        elif isinstance(base, Iterable) and not isinstance(base, (str, bytes)):
            methods = _get_methods('list')
        elif isinstance(base, str):
            methods = _get_methods('str')
        elif isinstance(base, datetime):
            methods = _get_methods('datetime')

            if name not in methods:
                try:
                    from ..datetime.vdate_class import VDate as vicDate
                    vic_date_methods = {m: getattr(vicDate, m) for m in dir(vicDate) if not m.startswith('_')}
                    if name in vic_date_methods:
                        method = vic_date_methods[name]
                        if callable(method):
                            @box
                            def wrapper(*args, **kwargs):
                                vd = vicDate(base.strftime('%Y-%m-%d'))
                                return getattr(vd, name)(*args, **kwargs)
                            return wrapper
                except ImportError:
                    pass
        else:
            methods = {}

        if name in methods:
            method = methods[name]
            if name in ['append', 'extend', 'insert', 'remove', 'pop', 'clear', 'reverse', 'sort',
                        'update', 'setdefault', 'popitem']:
                def inplace_wrapper(*args, **kwargs):
                    method(base, *args, **kwargs)
                    return self
                return inplace_wrapper
            @box
            def wrapper(*args, **kwargs):
                return method(base, *args, **kwargs)
            return wrapper

        raise AttributeError(f"type object '{type(self).__name__}' has no attribute '{name}'")

    def copy(self) -> 'Box':
        """返回 Box 的浅拷贝。
        
        Returns:
            包装了 __wrapped__ 副本的新 Box
        """
        cls = type(self)
        return cls(self.__wrapped__.copy())

    def map(self, func: Callable[[Any], Any]) -> 'Box':
        """对 Box 内的可迭代对象执行 map 操作。
        
        Args:
            func: 映射函数，应用于每个元素
            
        Returns:
            映射结果的 Box 包装
            
        Raises:
            TypeError: 当 __wrapped__ 不是可迭代对象时
        """
        # BUG-437: func 必须可调用（原实现直接 func(item)，传 'x' 会抛
        # TypeError: 'str' object is not callable，看不出是参数错误）；
        # 另外 str/bytes 被**有意排除**（避免逐字符映射），原报错却说
        # "只适用于可迭代对象"（str 本就可迭代），信息与行为矛盾。
        if not callable(func):
            raise TypeError(
                f"Box.map() 的 func 必须可调用，收到 "
                f"{type(func).__name__}: {func!r}")
        base = self.__wrapped__
        if isinstance(base, Iterable) and not isinstance(base, (str, bytes)):
            result = [func(item) for item in base]
            return Box(result)
        raise TypeError(
            "Box.map() 只适用于非 str/bytes 的可迭代对象（str/bytes 被排除以"
            "避免逐字符映射）；str 请直接调用其方法或改用 Box(str(...))。")

    def filter(self, func: Callable[[Any], bool]) -> 'Box':
        """对 Box 内的可迭代对象执行过滤操作。
        
        Args:
            func: 过滤函数，返回 True 保留元素，False 丢弃元素
            
        Returns:
            过滤结果的 Box 包装
            
        Raises:
            TypeError: 当 __wrapped__ 不是可迭代对象时
        """
        if not callable(func):
            raise TypeError(
                f"Box.filter() 的 func 必须可调用，收到 "
                f"{type(func).__name__}: {func!r}")
        base = self.__wrapped__
        if isinstance(base, Iterable) and not isinstance(base, (str, bytes)):
            result = [item for item in base if func(item)]
            return Box(result)
        raise TypeError(
            "Box.filter() 只适用于非 str/bytes 的可迭代对象（str/bytes 被排除以"
            "避免逐字符过滤）；str 请直接调用其方法或改用 Box(str(...))。")

    def reduce(self, func: Callable[[Any, Any], Any], initial: Optional[Any] = None) -> 'Box':
        """对 Box 内的可迭代对象执行归约操作。
        
        Args:
            func: 归约函数，接收两个参数（累积值，当前元素）
            initial: 可选的初始值
            
        Returns:
            归约结果的 Box 包装
            
        Raises:
            TypeError: 当 __wrapped__ 不是可迭代对象时
        """
        base = self.__wrapped__
        if isinstance(base, Iterable) and not isinstance(base, (str, bytes)):
            result = reduce(func, base, initial) if initial is not None else reduce(func, base)
            return Box(result)
        raise TypeError("reduce 操作只适用于可迭代对象")

    def run(self, func: Union[Callable[..., Any], str] = print, *args: Any, **kwargs: Any) -> Any:
        """执行函数并返回结果，支持多种调用模式。
        
        Args:
            func: 要执行的函数或字符串（会被 g 函数解析）
            *args: 额外的位置参数
            **kwargs: 额外的关键字参数
            
        Keyword Args:
            nobox: bool, 是否返回原始值（不包装为 Box）
            unpack: str, 解包模式，"*" 解包可迭代对象，"**" 解包字典
            rerun: bool, 是否对每个元素执行函数
            
        Returns:
            函数执行结果（默认包装为 Box，nobox=True 时返回原始值）
            
        Raises:
            TypeError: 当 func 参数类型错误时
        """
        if isinstance(func, str):
            func = g(func)
        if not callable(func):
            raise TypeError(f"func 参数类型错误,只接受类型(callable)")
        nobox = kwargs.pop('nobox', False)
        arg0 = self.__wrapped__
        unpack = kwargs.pop('unpack', "")
        rerun = kwargs.pop('rerun', False)
        if unpack == "*":
            if not isinstance(arg0, Iterable):
                # BUG-344: 原报 "object of type 'int' has no len()"，但问题是
                # unpack='*' 需要可迭代对象（与 len 无关），信息误导。
                raise TypeError(
                    f"unpack='*' 需要可迭代对象，但 __wrapped__ 是 "
                    f"'{type(arg0).__name__}': {arg0!r}")
            result = [func(arg, *args, **kwargs) for arg in arg0] if rerun else func(*arg0, *args, **kwargs)
        elif unpack == "**":
            if not isinstance(arg0, dict):
                # BUG-344: 同上——unpack='**' 需要 dict，报 len() 同样误导。
                raise TypeError(
                    f"unpack='**' 需要字典，但 __wrapped__ 是 "
                    f"'{type(arg0).__name__}': {arg0!r}")
            result = {k: func(v, *args, **kwargs) for k, v in arg0.items()} if rerun else func(*args, **arg0, **kwargs)
        else:
            result = func(arg0, *args, **kwargs)
        
        if nobox:
            return result
        return Box(result)

    def __dir__(self) -> List[str]:
        """返回 Box 对象的目录列表。
        
        包括 __wrapped__ 的所有属性，以及 Box 特有方法（map, filter, reduce, copy, run）
        和数字索引访问属性（_1, _2, ...）。
        
        Returns:
            排序后的属性名字符串列表
        """
        base = self.__wrapped__
        rs = dir(base)
        st = set(rs)

        box_methods = {'map', 'filter', 'reduce', 'copy', 'run'}
        st = st | box_methods

        # BUG-349: 原只认 (dict, list, tuple)，而 Box 包装结果是 VList/VText 等
        # 非 list 子类 —— 文档承诺的 `_1, _2, ...` 属性在 dir() 里根本看不到。
        if (isinstance(base, dict) or self._is_indexable(base)) and len(base) > 0:
            max_items = min(len(base), 100)
            for i in range(1, max_items + 1):
                st.add(f'_{i}')

        if isinstance(base, dict):
            ks = set(_get_methods('dict').keys())
        elif isinstance(base, Iterable) and not isinstance(base, (str, bytes)):
            ks = set(_get_methods('list').keys())
        elif isinstance(base, str):
            ks = set(_get_methods('str').keys())
        elif isinstance(base, datetime):
            ks = set(_get_methods('datetime').keys())
            try:
                from ..datetime.vdate_class import VDate as vicDate
                ks = ks | {m for m in dir(vicDate) if not m.startswith('_')}
            except ImportError:
                pass
        else:
            ks = set()
        rs = st | ks
        if '__call__' in rs and not callable(self.__wrapped__):
            rs -= set(['__call__'])
        return list(sorted(rs))

    def __hasattr__(self, name: str) -> bool:
        """检查 Box 对象是否具有指定名称的属性。
        
        支持数字索引属性（如 _1, _2, _-1 等）的动态检查。
        
        Args:
            name: 属性名称
            
        Returns:
            如果属性存在则返回 True，否则返回 False
        """
        base = self.__wrapped__
        # BUG-349: 数值索引属性（_1/_2/_-1）的可访问性判定必须与 `__getattr__`
        # 一致——原实现只认 (dict, list, tuple)，而包装结果是 VList，
        # 导致 `b._1` 能取到值、`b.__hasattr__('_1')` 却返回 False。
        _n = None
        if isinstance(base, dict) or self._is_indexable(base):
            _n = len(base)
        if _n is not None and name.startswith('_') and len(name) > 1:
            if name[1:].isdigit():
                index = int(name[1:]) - 1
                return 0 <= index < _n
            if name.startswith('_-') and name[2:].isdigit():
                index = -int(name[2:])
                return -_n <= index < 0

        return name in self.__dir__()

    def do(self, f: Callable[..., Any] = print, pre_f: Optional[Callable[..., Any]] = None, sub_f: Optional[Callable[..., Any]] = None) -> 'Box':
        """对 Box 执行副作用函数，返回 self 以支持链式调用。
        
        Args:
            f: 要执行的函数（默认为 print）
            pre_f: 执行前的预处理函数
            sub_f: 执行后的后处理函数（不关心返回值）
            
        Returns:
            self 本身，用于链式调用
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self


def setattr_box(func: Callable[..., Any], attr_name: str, cover: bool = True) -> Optional[bool]:
    """将函数设置为 Box 类的方法。
    
    Args:
        func: 要设置为 Box 方法的函数
        attr_name: 方法名称
        cover: 是否覆盖已存在的属性，默认为 True
        
    Returns:
        成功返回 True，失败返回 None
        
    Raises:
        AttributeError: 当 cover=False 且属性已存在时
    """
    if not callable(func):
        return None

    if not cover and hasattr(Box, attr_name):
        raise AttributeError(f"Box类已存在属性 '{attr_name}'")

    def wrapped_func(self, *args, **kwargs):
        result = func(self, *args, **kwargs)
        if result is None:
            return self
        if isinstance(result, Box):
            return result
        return Box(result)

    setattr(Box, attr_name, wrapped_func)
    return True