from functools import partial, reduce
from collections.abc import Iterable
from wrapt import decorator as wdeco, ObjectProxy as AOP
from .arrow_func import g
from datetime import datetime

__all__ = ['box', 'Box', 'setattr_box']


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


def box(func=None, *, signature_from=None):
    if func is None:
        return lambda f: box(f, signature_from=signature_from)
    @wdeco
    def _box(wrapped, instance, args, kwargs):
        def _nobox(obj):
            if isinstance(obj, Box):
                return obj.__wrapped__
            else:
                return obj
        args = list(map(_nobox, args))
        kwargs = {k: _nobox(v) for k, v in kwargs.items()}
        rs = wrapped(*args, **kwargs)
        if rs is None:
            return instance
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

    if signature_from is not None:
        try:
            from functools import update_wrapper
            update_wrapper(_box, signature_from)
        except ValueError:
            pass
    return _box(func)


@box
def __box_wrapped_call__(self, *args, **kwargs):
    if callable(self):
        return self(*args, **kwargs)
    if not callable(self.__wrapped__):
        raise TypeError(f"'{type(self).__name__}' object is not callable")
    return self.__wrapped__(*args, **kwargs)


class CallableDescriptor:
    """描述符，控制__call__属性的访问"""
    def __init__(self):
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

    def enable(self):
        self.enabled = True


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

    def disable(self):
        self.enabled = False


class Box(AOP):

    __call__ = CallableDescriptor()

    def _get_keys(self):
        """获取 __wrapped__ 的键列表（支持 dict 和 列表类型）"""
        base = self.__wrapped__
        if isinstance(base, dict):
            return list(base.keys())
        elif isinstance(base, (list, tuple)):
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
        elif isinstance(base, (list, tuple)):
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
        elif isinstance(base, (list, tuple)):
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

    def copy(self):
        cls = type(self)
        return cls(self.__wrapped__.copy())

    @box
    def map(self, func):
        """映射操作"""
        base = self.__wrapped__
        if isinstance(base, Iterable) and not isinstance(base, (str, bytes)):
            return [func(item) for item in base]
        raise TypeError("map 操作只适用于可迭代对象")

    @box
    def filter(self, func):
        """过滤操作"""
        base = self.__wrapped__
        if isinstance(base, Iterable) and not isinstance(base, (str, bytes)):
            return [item for item in base if func(item)]
        raise TypeError("filter 操作只适用于可迭代对象")

    @box
    def reduce(self, func, initial=None):
        """归约操作"""
        base = self.__wrapped__
        if isinstance(base, Iterable) and not isinstance(base, (str, bytes)):
            return reduce(func, base, initial) if initial is not None else reduce(func, base)
        raise TypeError("reduce 操作只适用于可迭代对象")

    @box
    def run(self, func=print, *args, **kwargs):
        if isinstance(func, str):
            func = g(func)
        if not callable(func):
            raise TypeError(f"func 参数类型错误,只接受类型(callable)")
        nobox = kwargs.pop('nobox', False)
        arg0 = self if nobox else self.__wrapped__
        unpack = kwargs.pop('unpack', "")
        rerun = kwargs.pop('rerun', False)
        if unpack == "*":
            if not isinstance(arg0, Iterable):
                raise TypeError(f"object of type '{type(arg0).__name__}' has no len()")
            return [func(arg, *args, **kwargs) for arg in arg0] if rerun else func(*arg0, *args, **kwargs)
        elif unpack == "**":
            if not isinstance(arg0, dict):
                raise TypeError(f"object of type '{type(arg0).__name__}' has no len()")
            return {k: func(v, *args, **kwargs) for k, v in arg0.items()} if rerun else func(*args, **arg0, **kwargs)
        else:
            return func(arg0, *args, **kwargs)

    @box
    def __dir__(self):
        base = self.__wrapped__
        rs = dir(base)
        st = set(rs)

        box_methods = {'map', 'filter', 'reduce', 'copy', 'run'}
        st = st | box_methods

        if isinstance(base, (dict, list, tuple)) and len(base) > 0:
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

    def __hasattr__(self, name):
        if name.startswith('_') and len(name) > 1:
            if name[1:].isdigit():
                index = int(name[1:]) - 1
                base = self.__wrapped__
                if isinstance(base, (dict, list, tuple)):
                    return 0 <= index < len(base)
            if name.startswith('_-') and name[2:].isdigit():
                index = -int(name[2:])
                base = self.__wrapped__
                if isinstance(base, (dict, list, tuple)):
                    return -len(base) <= index < 0

        return name in self.__dir__()


def setattr_box(func, attr_name, cover=True):
    """将函数设置为 Box 类的方法"""
    if not callable(func):
        return None

    if not cover and hasattr(Box, attr_name):
        raise AttributeError(f"Box类已存在属性 '{attr_name}'")

    @box
    def wrapped_func(self, *args, **kwargs):
        return func(self, *args, **kwargs)

    setattr(Box, attr_name, wrapped_func)
    return True