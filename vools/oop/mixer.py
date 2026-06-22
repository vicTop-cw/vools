"""
对象混合器模块

提供 Mixer 类，用于混合多个对象的属性和方法。
"""

from collections import namedtuple
from enum import IntFlag
from functools import partial, lru_cache
from typing import Any, List, Optional, Tuple, Union, Callable, Type

__all__ = ['Mixer', 'Mixer_', 'attr_Enum']


class attr_Enum(IntFlag):
    """属性枚举类，用于控制 __dir__ 返回的元组格式。
    
    属性:
        WITH_NAME: 包含属性名
        WITH_CLS_NAME: 包含类名
        WITH_STR_VALUE: 包含字符串值
    """
    WITH_NAME = 1
    WITH_CLS_NAME = 2
    WITH_STR_VALUE = 4
    
    def do(self, f: Callable[..., Any] = print, 
           pre_f: Optional[Callable[..., Any]] = None, 
           sub_f: Optional[Callable[..., Any]] = None) -> "attr_Enum":
        """应用函数进行副作用处理，返回 self 以支持链式调用。
        
        Args:
            f: 要应用的函数（默认 print）
            pre_f: 在 f 之前应用的预处理函数
            sub_f: 在 f 之后应用的后处理函数
            
        Returns:
            self，用于链式调用
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self



class Mixer_:
    """基础混合器类，支持将多个对象的属性和方法合并。
    
    Mixer_ 将多个对象的属性和方法组合在一起，支持按优先级
    访问和动态优先级调整。
    
    Attributes:
        _objs: 组合对象列表
        _priority_map: 对象优先级映射
        _attr_cache: 属性缓存
        _attr_code: 额外代码字典
    """
    def __init__(self, *objs: Any) -> None:
        """初始化 Mixer_ 混合器。
        
        Args:
            *objs: 要混合的对象列表
        """
        self._objs = list(objs)  # 存储组合对象
        self._priority_map = {id(obj): i for i, obj in enumerate(objs)}  # 对象优先级映射
        self._ObjInfo = namedtuple('ObjInfo', 'obj priority')  # 对象信息元组
        self.dir_tuple = attr_Enum.WITH_NAME | attr_Enum.WITH_CLS_NAME  # | attr_Enum.WITH_STR_VALUE
        self._attr_cache = {}  # 属性缓存
        self._attr_code = {}  # 额外代码

    def __getstate__(self) -> dict:
        """返回序列化状态。"""
        return {'_objs': self._objs, '_priority_map': self._priority_map,
                '_attr_cache': {}, '_attr_code': self._attr_code}
    
    def __setstate__(self, state: dict) -> None:
        """从序列化状态恢复。"""
        self._objs = state['_objs']
        self._priority_map = state['_priority_map']
        self._attr_cache = {}
        self._attr_code = state.get('_attr_code', {})
        self._ObjInfo = namedtuple('ObjInfo', 'obj priority')
        self.dir_tuple = attr_Enum.WITH_NAME | attr_Enum.WITH_CLS_NAME

    @property
    def dir_tuple(self) -> Type:
        """返回 dir_tuple 属性的类型。"""
        return self._dir_tuple

    @dir_tuple.setter
    def dir_tuple(self, v: Optional[attr_Enum] = None) -> None:
        """设置 dir_tuple 属性。
        
        Args:
            v: 属性枚举值
        """
        self._attr_v = v
        if v == 1:
            self._dir_tuple = namedtuple('DirTuple', 'name')
        elif v == 2:
            self._dir_tuple = namedtuple('DirTuple', 'cls_name')
        elif v == 4:
            self._dir_tuple = namedtuple('DirTuple', 'str_value')
        elif v == 5:
            self._dir_tuple = namedtuple('DirTuple', 'name str_value')
        elif v == 6:
            self._dir_tuple = namedtuple('DirTuple', 'cls_name str_value')
        elif v == 3:
            self._dir_tuple = namedtuple('DirTuple', 'name cls_name')
        else:
            self._dir_tuple = namedtuple('DirTuple', 'name cls_name str_value')

    def __dir__(self) -> List[Any]:
        """返回(属性名, 来源对象)的双字段列表。"""
        def __inner(*tp: Any) -> Any:
            p = self.dir_tuple
            v = self._attr_v
            if v == 1:
                return p(name=tp[0])
            elif v == 2:
                return p(cls_name=tp[1])
            elif v == 4:
                return p(str_value=tp[2])
            elif v == 5:
                return p(name=tp[0], str_value=tp[2])
            elif v == 6:
                return p(cls_name=tp[1], str_value=tp[2])
            elif v == 3:
                return p(name=tp[0], cls_name=tp[1])
            else:
                return p(name=tp[0], cls_name=tp[1], str_value=tp[2])

        dir_list = [__inner(i, self.__class__.__name__, str(self)) for i in dir(super())]
        # 添加当前对象属性（避免重复）
        for obj in self.get_priority_objs():
            for attr in dir(obj):
                if attr not in [i[0] for i in dir_list] and not attr.startswith('__'):
                    dir_list.append(__inner(attr, obj.__class__.__name__, str(obj)))
        return dir_list

    def get_priority_objs(self) -> List[Any]:
        """按优先级排序的对象列表。
        
        Returns:
            按优先级排序的对象列表
        """
        i = 0

        def __order(obj: Any) -> Tuple[int, int]:
            nonlocal i
            i += 1
            return self._priority_map.get(id(obj), float('inf')), i

        return sorted(self._objs, key=__order)

    # ===== 动态优先级控制 =====
    def update_priority(self, obj: Any, new_priority: int) -> None:
        """动态修改对象优先级。
        
        Args:
            obj: 要修改优先级的对象
            new_priority: 新的优先级值
            
        Raises:
            ValueError: 当对象不在 Mixer 中时
        """
        if obj not in self._objs:
            raise ValueError("Object not in Mixer")
        self._priority_map[id(obj)] = new_priority
        self._invalidate_cache()  # 清除缓存

    def add_object(self, obj: Any, priority: Optional[int] = None) -> None:
        """添加新对象并设置优先级。
        
        Args:
            obj: 要添加的对象
            priority: 优先级，如果为 None 则添加到最后
        """
        self._objs.append(obj)
        priority = priority if priority is not None else len(self._objs)
        self._priority_map[id(obj)] = priority
        self._invalidate_cache()

    def remove_object(self, obj: Any) -> None:
        """移除对象并清除相关缓存。
        
        Args:
            obj: 要移除的对象
        """
        if obj in self._objs:
            self._objs.remove(obj)
            obj_id = id(obj)
            if obj_id in self._priority_map:
                del self._priority_map[obj_id]
            self._invalidate_cache(obj=obj)

    def _invalidate_cache(self, obj: Optional[Any] = None) -> None:
        """缓存失效机制。
        
        Args:
            obj: 如果为 None 清除全部缓存，否则清除特定对象的缓存
        """
        if obj is None:  # 清除全部缓存
            self._attr_cache.clear()
        else:  # 清除特定对象相关的缓存
            keys_to_delete = [
                attr for attr, (_, source) in self._attr_cache.items()
                if source is obj
            ]
            for key in keys_to_delete:
                del self._attr_cache[key]

    def do(self, f: Callable[..., Any] = print, 
           pre_f: Optional[Callable[..., Any]] = None, 
           sub_f: Optional[Callable[..., Any]] = None) -> "Mixer_":
        """应用函数进行副作用处理，返回 self 以支持链式调用。
        
        Args:
            f: 要应用的函数（默认 print）
            pre_f: 在 f 之前应用的预处理函数
            sub_f: 在 f 之后应用的后处理函数
            
        Returns:
            self，用于链式调用
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self

    # ===== 缓存优化 =====
    @lru_cache(maxsize=256)
    def _get_cached_attr(self, name: str) -> Any:
        """LRU缓存优化方法（内部使用）。
        
        Args:
            name: 属性名
            
        Returns:
            属性的值
        """
        return self.__getattr__(name)


class Mixer(Mixer_):
    """增强版混合器类，在 Mixer_ 基础上支持额外的代码修饰功能。
    
    Mixer 允许为混合的属性和方法添加装饰器、代码片段等额外功能。
    """

    def remove_extra_code(self, func_name: str) -> None:
        """移除额外代码。
        
        Args:
            func_name: 函数名
        """
        self._attr_code.pop(func_name)

    def add_extra_code(self, func_name: str, 
                      func_shell: Optional[Callable[[Callable[..., Any]], Callable[..., Any]]] = None,
                      result_shell: Optional[Callable[[Any], Any]] = None,
                      code_first: Optional[str] = None,
                      code_last: Optional[str] = None,
                      partial_args: Optional[Union[List[Any], Tuple[Any, ...]]] = None,
                      partial_kwargs: Optional[dict] = None) -> None:
        """修饰原函数，添加额外的代码，并绑定到 Mixer 对象上。
        
        Args:
            func_name: 绑定的函数名，不能是属性名，也不能是魔法函数 __xx__
            func_shell: 对原来运行的函数套个壳，进行修饰，必须是单参函数的装饰器，
                       参数即是原函数本身，并返回一个函数
            result_shell: 对原来运行的函数结果套个壳，进行修饰，必须是单参数函数，
                          参数即是原函数的返回值，并返回一个值
            code_first: 额外要运行的代码，运行在原来要运行的函数之前
            code_last: 额外要运行的代码：运行在原来要运行的函数之后
            partial_args: 对原函数进行部分应用，传入的 args
            partial_kwargs: 对原函数进行部分应用，传入的 kwargs
            
        Raises:
            ValueError: func_name 为魔法函数名或所有参数都为空/False
            TypeError: 参数类型不正确
        """
        if func_name.startswith("___") and func_name.endswith("__"):
            raise ValueError(f"func_name must not be a magical name :{func_name}")
        if all(bool(i) == False for i in (func_shell, result_shell, code_first, code_last, partial_args, partial_kwargs)):
            raise ValueError(f"func_shell,result_shell,code_first,code_last,partial_args,partial_kwargs  at least one is not None or Blank !!!")
        if func_shell is not None:
            if callable(func_shell):
                pass
            else:
                raise TypeError("func_shell must be a function decorator!!!")
        if result_shell is not None:
            if callable(result_shell):
                pass
            elif isinstance(result_shell, str):
                result_shell = lambda x: eval(result_shell, globals(), locals())
            else:
                raise TypeError("result_shell must be a function !!!")
        if partial_args and not isinstance(partial_args, (list, tuple)):
            raise TypeError("partial_args must be a list or tuple !!!")
        if partial_kwargs and not isinstance(partial_kwargs, dict):
            raise TypeError("partial_kwargs must be a dict !!!")
        self._attr_code[func_name] = {
            'func_shell': func_shell,
            'result_shell': result_shell,
            'code_first': code_first if code_first else '',
            'code_last': code_last if code_last else '',
            'partial_args': partial_args if partial_args else [],
            'partial_kwargs': partial_kwargs if partial_kwargs else {}
        }

    def __getattr__(self, name: str) -> Any:
        """获取属性，优先从缓存获取，然后从组合对象中查找。
        
        Args:
            name: 属性名
            
        Returns:
            属性的值
            
        Raises:
            AttributeError: 当属性在所有组件中都找不到时
        """
        def generate_deco_attr(sf: "Mixer", attr: Callable[..., Any], 
                              func_shell: Optional[Callable],
                              result_shell: Optional[Callable],
                              code_first: str, code_last: str,
                              partial_args: Optional[List[Any]],
                              partial_kwargs: Optional[dict]) -> Callable[..., Any]:
            def meerge_method(*gs: Any, **kws: Any) -> Any:
                nonlocal sf, attr, func_shell, result_shell, code_first, code_last, partial_args, partial_kwargs
                if code_first:
                    exec(code_first.replace('self', 'sf'), globals(), locals())
                result = attr(*gs, **kws)
                if code_last:
                    exec(code_last.replace('self', 'sf'), globals(), locals())
                return result_shell(result) if result_shell else result

            if partial_args and partial_kwargs:
                meerge_method = partial(meerge_method, *partial_args, **partial_kwargs)
            elif partial_args:
                meerge_method = partial(meerge_method, *partial_args)
            elif partial_kwargs:
                meerge_method = partial(meerge_method, **partial_kwargs)
            return func_shell(meerge_method) if func_shell else meerge_method

        # 1. 通过基类安全获取缓存（绕过__getattr__）
        try:
            if name in ("_attr_cache", "_attr_code"):
                return super().__getattribute__(name)
            attr_cache = super().__getattribute__('_attr_cache')
            attr_code = super().__getattribute__('_attr_code')
            flag = name in attr_code
            if name in attr_cache:
                attr = attr_cache[name][0]
                if flag and callable(attr):
                    return generate_deco_attr(self, attr, **attr_code[name])
                return attr
        except AttributeError:
            pass  # 缓存未命中则继续

        # 2. 安全获取对象列表（直接调用基类方法）
        objs = super().get_priority_objs()

        # 3. 遍历对象查找属性
        for obj in objs:
            try:
                attr = getattr(obj, name)
                # 更新缓存时同样使用基类方法
                if flag and callable(attr):
                    attr = generate_deco_attr(self, attr, **attr_code[name])
                super().__getattribute__('_attr_cache')[name] = (attr, obj)
                return attr
            except AttributeError:
                continue

        raise AttributeError(f"'{name}' not found in Mixer components")

    def do(self, f: Callable[..., Any] = print, 
           pre_f: Optional[Callable[..., Any]] = None, 
           sub_f: Optional[Callable[..., Any]] = None) -> "Mixer":
        """应用函数进行副作用处理，返回 self 以支持链式调用。
        
        Args:
            f: 要应用的函数（默认 print）
            pre_f: 在 f 之前应用的预处理函数
            sub_f: 在 f 之后应用的后处理函数
            
        Returns:
            self，用于链式调用
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self


# 别名
mixer = Mixer