"""
柯里化类装饰器 - 优化版本

主要优化：
1. 将方法处理从实例级别移到类级别
2. 使用 __slots__ 优化内存
3. 预计算参数信息
"""
import inspect
from functools import wraps
from typing import Callable, Any, Dict, List

__all__ = ['curry_class']


# 缓存类方法的参数信息
_class_method_info_cache = {}


def _get_method_info(method):
    """获取方法签名信息，缓存结果"""
    if method not in _class_method_info_cache:
        sig = inspect.signature(method)
        params = list(sig.parameters.values())
        
        required_params = []
        all_param_names = []
        has_varargs = False
        has_varkw = False
        
        for param in params[1:]:  # 排除self
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                has_varargs = True
            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                has_varkw = True
            else:
                all_param_names.append(param.name)
                if param.default == inspect.Parameter.empty:
                    required_params.append(param.name)
        
        _class_method_info_cache[method] = {
            'required_params': required_params,
            'all_param_names': all_param_names,
            'has_varargs': has_varargs,
            'has_varkw': has_varkw,
        }
    
    return _class_method_info_cache[method]


class CurriedMethod:
    """
    柯里化方法包装类，支持同一方法的链式参数收集
    """
    __slots__ = ('func', 'instance', 'required_params', 'has_varargs', 
                 'has_varkw', 'all_param_names', 'collected_args', 'collected_kwargs')
    
    def __init__(self, func: Callable, instance: Any, 
                 required_params: List[str], has_varargs: bool, has_varkw: bool,
                 all_param_names: List[str], collected_args=None, collected_kwargs=None):
        self.func = func
        self.instance = instance
        self.required_params = required_params
        self.has_varargs = has_varargs
        self.has_varkw = has_varkw
        self.all_param_names = all_param_names
        self.collected_args = collected_args or []
        self.collected_kwargs = collected_kwargs or {}
    
    def _check_params_complete(self, args=None, kwargs=None):
        """检查参数是否收集完整"""
        check_args = args if args is not None else self.collected_args
        check_kwargs = kwargs if kwargs is not None else self.collected_kwargs
        
        filled = set(check_kwargs.keys())
        arg_index = 0
        
        for param in self.required_params:
            if param not in filled:
                if arg_index < len(check_args):
                    filled.add(param)
                    arg_index += 1
        
        return filled == set(self.required_params)
    
    def __call__(self, *args, **kwargs):
        new_args = self.collected_args + list(args)
        new_kwargs = {**self.collected_kwargs, **kwargs}
        
        is_empty_call = len(args) == 0 and len(kwargs) == 0
        params_complete = self._check_params_complete(new_args, new_kwargs)
        
        # 如果必需参数完整且没有可变参数，立即执行
        if params_complete and not (self.has_varargs or self.has_varkw):
            final_kwargs = dict(new_kwargs)
            arg_idx = 0
            
            for param in self.all_param_names:
                if param not in final_kwargs and arg_idx < len(new_args):
                    final_kwargs[param] = new_args[arg_idx]
                    arg_idx += 1
            
            return self.func(self.instance, **final_kwargs)
        
        # 如果有可变参数且是空调用，执行方法
        if (self.has_varargs or self.has_varkw) and is_empty_call:
            return self.func(self.instance, *new_args, **new_kwargs)
        
        # 继续收集参数
        return CurriedMethod(
            self.func, self.instance, self.required_params,
            self.has_varargs, self.has_varkw, self.all_param_names,
            new_args, new_kwargs
        )


def curry_class(cls: type):
    """
    柯里化类装饰器 - 优化版本
    将方法处理移到类级别，避免每个实例重复处理
    """
    if not inspect.isclass(cls):
        raise TypeError(f"@curry_class 装饰器仅允许应用于类，当前类型为: {type(cls).__name__}")
    
    allowed_magic_methods = {
        '__call__', '__add__', '__sub__', '__mul__', '__truediv__', '__floordiv__',
        '__mod__', '__divmod__', '__pow__', '__lshift__', '__rshift__',
        '__and__', '__or__', '__xor__', '__lt__', '__le__', '__eq__', '__ne__',
        '__gt__', '__ge__', '__neg__', '__pos__', '__abs__', '__invert__',
        '__getitem__', '__contains__', '__iadd__', '__isub__', '__imul__',
        '__itruediv__', '__ifloordiv__', '__imod__', '__ipow__', '__ilshift__',
        '__irshift__', '__iand__', '__ior__', '__ixor__',
    }
    
    excluded_methods = {
        '__init__', '__new__', '__del__', '__getattribute__', '__getattr__',
        '__setattr__', '__delattr__', '__repr__', '__str__', '__format__',
        '__len__', '__bool__', '__enter__', '__exit__', '__iter__', '__next__',
        '__hash__', '__dir__', '__sizeof__',
    }
    
    # 预计算所有方法的参数信息（类级别）
    method_info_map = {}
    
    for name, method in cls.__dict__.items():
        if not inspect.isfunction(method):
            continue
        if name in excluded_methods:
            continue
        if name.startswith('__') and name.endswith('__') and name not in allowed_magic_methods:
            continue
        
        method_info_map[name] = _get_method_info(method)
    
    original_init = cls.__init__
    
    def new_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        
        for name, info in method_info_map.items():
            method = cls.__dict__[name]
            
            @wraps(method)
            def create_curried(meth=method, req_params=info['required_params'], 
                              varargs=info['has_varargs'], varkw=info['has_varkw'], 
                              all_params=info['all_param_names']):
                def curried_wrapper(*args_inner, **kwargs_inner):
                    temp_curried = CurriedMethod(
                        meth, self, req_params, varargs, varkw, all_params, 
                        list(args_inner), kwargs_inner
                    )
                    
                    if temp_curried._check_params_complete():
                        return temp_curried.__call__()
                    
                    return temp_curried
                return curried_wrapper
            
            setattr(self, name, create_curried())
    
    cls.__init__ = new_init
    return cls


@curry_class
class T:
    """示例类，使用 @curry_class 装饰器"""
    
    def __init__(self):
        self.result = 0
        self.data = []
    
    def add(self, a: int, b: int, c: int) -> int:
        """加法方法，将三个数相加"""
        self.result = a + b + c
        return self.result
    
    def multiply(self, x: int, y: int) -> int:
        """乘法方法，将两个数相乘"""
        self.result = x * y
        return self.result
    
    def sum_all(self, a: int, b: int, *c, **k) -> int:
        """求和方法，支持可变参数"""
        total = a + b + sum(c)
        if k:
            total += sum(k.values())
        self.result = total
        return total
    
    def __call__(self, x, y, z):
        """调用方法，支持柯里化"""
        self.result = x * y + z
        return self.result
    
    def __add__(self, a, b):
        """加法运算符重载"""
        self.result = a + b
        return self.result
    
    def __getitem__(self, index, default=None):
        """获取列表项"""
        if index < len(self.data):
            return self.data[index]
        return default
    
    def __lt__(self, a, b):
        """小于比较"""
        return a < b


def test_curry_decorator():
    """测试用例验证"""
    print("=== 测试柯里化装饰器 ===\n")
    
    t = T()
    print("[OK] 成功实例化类T")
    
    t1 = T()
    result1 = t1.add(1).add(2).add(3)
    assert result1 == 6
    
    t2 = T()
    result2 = t2.add(1, 2).add(3)
    assert result2 == 6
    
    t3 = T()
    result3 = t3.add(1, 2, 3)
    assert result3 == 6
    
    t4 = T()
    result4 = t4.add(a=1).add(b=2).add(c=3)
    assert result4 == 6
    
    t5 = T()
    result5 = t5.add(1).add(b=2, c=3)
    assert result5 == 6
    
    t6 = T()
    result6 = t6.add(a=1).add(2, c=3)
    assert result6 == 6
    
    t7 = T()
    result7 = t7.multiply(5).multiply(6)
    assert result7 == 30
    
    t8 = T()
    result8 = t8.multiply(x=7).multiply(y=8)
    assert result8 == 56
    
    t9 = T()
    result9 = t9.sum_all(1, 2)
    assert result9 == 3
    
    t10 = T()
    result10 = t10.sum_all(1).sum_all(2).sum_all(3, 4).sum_all()
    assert result10 == 10
    
    t11 = T()
    result11 = t11.sum_all(1, 2, 3, x=4, y=5)
    assert result11 == 15
    
    t12 = T()
    result12 = t12.sum_all(1).sum_all(2, x=3).sum_all(y=4).sum_all()
    assert result12 == 10
    
    try:
        @curry_class
        def not_a_class():
            pass
        assert False
    except TypeError:
        pass
    
    t14 = T()
    result14 = t14.__call__(2, 3, 4)
    assert result14 == 10
    
    t15 = T()
    result15 = t15.__call__(2).__call__(3).__call__(4)
    assert result15 == 10
    
    t16 = T()
    result16 = t16.__add__(5).__add__(3)
    assert result16 == 8
    
    t17 = T()
    t17.data = [10, 20, 30]
    result17 = t17.__getitem__(2)
    assert result17 == 30
    
    t18 = T()
    t18.data = [10, 20, 30]
    result18 = t18.__getitem__(5, -1)
    assert result18 == -1
    
    t19 = T()
    curried = t19.__call__(2)
    curried = curried.__call__(3)
    result19 = curried.__call__(4)
    assert result19 == 10
    
    t20 = T()
    result20 = t20.__call__(x=2).__call__(3).__call__(z=4)
    assert result20 == 10
    
    print("=== 所有测试通过 ===")


if __name__ == "__main__":
    test_curry_decorator()