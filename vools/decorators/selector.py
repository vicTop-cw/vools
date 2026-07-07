from typing import Any, Callable, List, Optional, Tuple, Union, Iterator, TypeVar

from .curry_core import curry, is_curried

__all__ = ['select', 'Overloads', 'Selector']

F = TypeVar('F', bound=Callable[..., Any])
_is_curried = lambda f : isinstance(f,(Selector,Overloads)) or is_curried(f)


class Selector:
    """函数选择器，支持多个函数的链式调用和结果聚合。
    
    Selector 接受多个函数并返回一个可调用对象，该对象在调用时
    会依次尝试每个函数，返回第一个成功执行的结果。
    
    Attributes:
        funcs: 已注册的函数列表
        _is_init: 是否处于初始化状态
    """
    
    def __init__(self, *funcs: Callable[..., Any]) -> None:
        """初始化 Selector。
        
        Args:
            *funcs: 初始注册的函数列表
            
        Raises:
            ValueError: 当 funcs 为空时
        """
        if not funcs:
            raise ValueError("At least one function is required")
        def gen(fs):
            for f in fs :
                if _is_curried(f):
                    f.delaied = True
                    f.is_strict = True
                    yield f
                elif callable(f):
                    yield curry(f,delaied=True,is_strict=True)
                # 如果 f 不是可调用的对象，直接 yield 它
                else:
                    yield f
                    
        self.funcs = list(gen(funcs))
        self._is_init = True
    
    def first_result(self, *args: Any, **kwargs: Any) -> Any:
        """获取第一个成功执行函数的结果。
        
        Args:
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            第一个成功执行的函数的结果
        """
        result = self(*args, **kwargs)[0]
        if result.is_ready:
            return result()
        return result
    
    def get_result(self, shoud_full: bool = False) -> Tuple[Any, ...]:
        """获取所有函数的结果。
        
        Args:
            shoud_full: 是否要求所有函数都已完全绑定参数
            
        Returns:
            所有函数结果的元组
            
        Raises:
            ValueError: 没有注册任何函数
            TypeError: 不是所有函数都已准备好或已满
        """
        if not self.funcs:
            raise ValueError("No function is registered")
        b = lambda f :  f.is_full if shoud_full else f.is_ready
        if all(b(f) for f in self.funcs):
            return tuple(f() for f in self.funcs)
        raise TypeError(f"Not all functions are {'ready' if not shoud_full else 'full'}")
    
    
    def __getstate__(self) -> dict:
        """返回序列化状态。"""
        return {'funcs': self.funcs, '_is_init': self._is_init}

    def __setstate__(self, state: dict) -> None:
        """从序列化状态恢复。"""
        self.funcs = state['funcs']
        self._is_init = state.get('_is_init', True)

    def __str__(self) -> str:
        return "Selector(" + '\n==========================\n'.join(map(str,self.funcs)) + ")"
    
    @staticmethod
    def _try_bound(curried_func: Callable[..., Any], args: Tuple[Any, ...], kwargs: dict) -> Optional[Any]:
        """尝试绑定参数到函数。
        
        Args:
            curried_func: 柯里化函数
            args: 位置参数
            kwargs: 关键字参数
            
        Returns:
            如果绑定成功返回结果，否则返回 None
        """
        try:
            return curried_func(*args,**kwargs)
        except TypeError:
            return None
    
    def register(self, func: Optional[Callable[..., Any]] = None, returnCurried: bool = False) -> Union[Callable[[F], F], F]:
        """注册新函数到选择器。
        
        Args:
            func: 要注册的函数，如果为 None 则返回装饰器
            returnCurried: 是否返回柯里化后的函数
            
        Returns:
            如果 func 为 None 返回装饰器，否则返回原函数
            
        Raises:
            ValueError: Selector 已使用过（_is_init 为 False）
        """
        if not self._is_init:
            raise ValueError("Selector is already used")
        if func is None:
            return lambda f : self.register(f,returnCurried)
        # 检查函数是否已经被柯里化
        if not is_curried(func):
            # 对函数进行 curry 处理
            curried_func = curry(func, delaied=True, is_strict=True)
            self.funcs.append(curried_func)
            if returnCurried:
                return curry(func)
        else:
            # 函数已经被柯里化，直接添加到列表中
            self.funcs.append(func)
            if returnCurried:
                return func
        return func
    
    def add(self, *funcs: Callable[..., Any]) -> "Selector":
        """添加多个函数到选择器。
        
        Args:
            *funcs: 要添加的函数列表
            
        Returns:
            返回 self 以支持链式调用
        """
        for f in funcs:
            self.register(f,returnCurried=False)
        return self
    
    @property
    def size(self) -> int:
        """返回已注册函数的数量。"""
        return len(self.funcs)
    
    def __call__(self, *args: Any, **kwargs: Any) -> Union["Selector", Any]:
        """调用选择器，尝试用参数调用每个注册的函数。
        
        Args:
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            返回新的 Selector 包装结果，或直接返回结果
            
        Raises:
            TypeError: 没有函数能处理给定的参数
        """
        self._is_init = False
        cls = self.__class__
        
        def gen():
            for f in self.funcs:
                result = cls._try_bound(f,args,kwargs)
                if result is not None:
                    yield result
        rs = list(gen())
        
        l = len(rs)
        if l == 0:
            raise TypeError("No function can handle the arguments")
        
        # 处理只有一个结果的情况
        if l == 1:
            # 检查结果是否是 Curried 或 CurryDescriptor 对象
            if is_curried(rs[0]):
                # 检查是否已经有足够的参数（is_ready 为 True）
                is_ready = getattr(rs[0], 'is_ready', False)
                if is_ready:
                    # 如果已经有足够的参数，执行函数并返回结果
                    return rs[0]()
                else:
                    # 如果没有足够的参数，将结果包装在一个新的 cls 对象中返回
                    return cls(*rs)
            else:
                # 如果结果不是 Curried 或 CurryDescriptor 对象，直接返回结果
                return rs[0]
        
        # 否则，将结果包装在一个新的 cls 对象中返回
        return cls(*rs)
    
    def __getitem__(self, index: int) -> Callable[..., Any]:
        """通过索引获取函数。"""
        return self.funcs[index]
    
    def __len__(self) -> int:
        """返回已注册函数的数量。"""
        return len(self.funcs)
    
    def __iter__(self) -> Iterator[Callable[..., Any]]:
        """返回函数的迭代器。"""
        return iter(self.funcs)
    
    def __repr__(self) -> str:
        return str(self)
    
    def __eq__(self, other: object) -> bool:
        """检查与另一个 Selector 是否相等。"""
        if not isinstance(other, Selector):
            return False
        return self.funcs == other.funcs
    
    def __hash__(self) -> int:
        """返回对象的哈希值。"""
        return hash(tuple(self.funcs))
    
    def __add__(self, other: "Selector") -> "Selector":
        """合并两个选择器的函数。"""
        if not isinstance(other, Selector):
            return NotImplemented
        return self.__class__(*self.funcs, *other.funcs)
    
    def __radd__(self, other: "Selector") -> "Selector":
        """右侧合并选择器的函数。"""
        if not isinstance(other, Selector):
            return NotImplemented
        return self.__class__(*other.funcs, *self.funcs)
    
    def __mul__(self, other: int) -> "Selector":
        """重复选择器的函数。"""
        if not isinstance(other, int):
            return NotImplemented
        return self.__class__(*self.funcs * other)



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
    def toOverloads(self, delaied: bool = False) -> "Overloads":
        """转换为 Overloads 对象。
        
        Args:
            delaied: 是否使用延迟模式
            
        Returns:
            新的 Overloads 对象
        """
        return Overloads(*self.funcs, delaied=delaied)

# fs = Selector(lambda x : x+1,lambda x : x*2,lambda x ,y=2: x**2 + 2*y)
# print(fs(7).get_result(0,1))


class Overloads(Selector):
    """函数重载选择器，继承自 Selector 但行为略有不同。
    
    Overloads 在找不到匹配的处理函数时会报错，而不是跳过。
    
    Attributes:
        delaied: 是否使用延迟模式
    """

    def __init__(self, *funcs: Callable[..., Any], delaied: bool = False) -> None:
        """初始化 Overloads。
        
        Args:
            *funcs: 初始注册的函数列表
            delaied: 是否使用延迟模式
        """
        super().__init__(*funcs)
        self.delaied = delaied
        
    def register(self, func: Optional[Callable[..., Any]] = None, returnOverload: bool = False) -> Union[Callable[[F], F], F]:
        """注册新函数到重载选择器。
        
        Args:
            func: 要注册的函数，如果为 None 则返回装饰器
            returnOverload: 是否返回重载包装后的函数
            
        Returns:
            如果 func 为 None 返回装饰器，否则返回原函数或重载包装
        """
        if func is None:
            return lambda f: self.register(f, returnOverload)
        cls = self.__class__
        result = super().register(func, returnCurried=returnOverload)
        if returnOverload:
            return cls(result)
        return result
    def __getstate__(self) -> dict:
        """返回序列化状态。"""
        base = super().__getstate__()
        base['delaied'] = self.delaied
        return base

    def __setstate__(self, state: dict) -> None:
        """从序列化状态恢复。"""
        super().__setstate__(state)
        self.delaied = state.get('delaied', False)

    def __str__(self) -> str:
        return "Overloads(" + '\n==========================\n'.join(map(str,self.funcs)) + ")"
    
    def __call__(self, *args: Any, **kwargs: Any) -> Union["Overloads", Any]:
        """调用重载选择器。
        
        Args:
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            返回结果或新的 Overloads 对象
            
        Raises:
            TypeError: 多个或没有函数能处理给定的参数
        """
        cls = self.__class__
        if self.delaied:
            if any([args,kwargs]):
                result = super().__call__(*args, **kwargs)
                # 检查 result 是否是 Overloads 对象
                if isinstance(result, cls):
                    # print('-----------',len(result))
                    return cls(*result.funcs,delaied=True)
                else:
                    # 如果 result 不是 Overloads 对象，直接返回它
                    return result
            else:
                funcs = [f for f in self.funcs if hasattr(f, 'is_ready') and f.is_ready]
                if len(funcs) > 1:
                    raise TypeError("Multiple functions can handle the arguments")
                elif len(funcs) == 0:
                    # no one can handle the arguments
                    raise TypeError("No function can handle the arguments")
                return  funcs[0]()
        else:
            result = super().__call__(*args, **kwargs)
            # 检查 result 是否是 Overloads 对象
            if isinstance(result, cls):
                if len(result.funcs) >  1:
                    funcs = [f for f in result.funcs if hasattr(f, 'is_ready') and f.is_ready]
                    if len(funcs) > 1:
                        raise TypeError("Multiple functions can handle the arguments")
                    elif len(funcs) == 0:
                        # no one can handle the arguments
                        return cls(*result.funcs)
                    result = funcs[0]
                else:
                    result = result.funcs[0]
                
                if is_curried(result):
                    return result() if result.is_ready else result
                return result
            else:
                # 如果 result 不是 Overloads 对象，直接返回它
                return result

    def toSelector(self) -> Selector:
        """转换为 Selector 对象。
        
        Returns:
            新的 Selector 对象
        """
        return Selector(*self.funcs)
    def do(self, f: Callable[..., Any] = print, pre_f: Optional[Callable[..., Any]] = None, 
            sub_f: Optional[Callable[..., Any]] = None) -> "Overloads":
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

    
    

def select(*funcs: Callable[..., Any], delayed: bool = False) -> Union[Overloads, Callable[[F], Overloads]]:
    """函数选择器，接受多个函数并返回 Overloads 实例。
    
    Args:
        *funcs: 要注册的函数列表
        delayed: 是否使用延迟模式
        
    Returns:
        如果没有提供函数，返回装饰器；否则返回 Overloads 实例
    """
    if not funcs:
        return lambda f: select(f, delayed=delayed)
    return Overloads(*funcs, delaied=delayed)

