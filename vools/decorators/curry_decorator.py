"""
柯里化类装饰器，实现方法的链式调用
支持位置参数、关键字参数、可变参数(*args, **kwargs)的柯里化
"""
import inspect
from functools import wraps
from typing import Callable, Any, Dict, List
from vools.sig_cache import get_signature

__all__ = ['curry_class']

class CurriedMethod:
    """
    柯里化方法包装类，支持同一方法的链式参数收集
    支持位置参数、关键字参数和可变参数
    """
    def __init__(self, func: Callable, instance: Any, 
                 required_params: List[str], has_varargs: bool, has_varkw: bool,
                 all_param_names: List[str], method_name: str, 
                 collected_args=None, collected_kwargs=None):
        self.func = func
        self.instance = instance
        self.required_params = required_params  # 需要的参数名列表（不含self）
        self.has_varargs = has_varargs          # 是否有 *args
        self.has_varkw = has_varkw              # 是否有 **kwargs
        self.all_param_names = all_param_names  # 所有参数名列表（除了 self, *args, **kwargs）
        self.method_name = method_name
        self.collected_args = collected_args or []
        self.collected_kwargs = collected_kwargs or {}
    
    def _check_params_complete(self, args=None, kwargs=None):
        """检查参数是否收集完整"""
        check_args = args if args is not None else self.collected_args
        check_kwargs = kwargs if kwargs is not None else self.collected_kwargs
        
        # 创建已填充参数的集合（从关键字参数）
        filled = set()
        for param in check_kwargs:
            if param in self.required_params:
                filled.add(param)
        
        # 位置参数按顺序填充
        arg_index = 0
        for param in self.required_params:
            if param not in filled:
                if arg_index < len(check_args):
                    filled.add(param)
                    arg_index += 1
        
        # 检查所有必需参数是否都被填充
        return filled == set(self.required_params)
    
    def __call__(self, *args, **kwargs):
        new_args = self.collected_args + list(args)
        new_kwargs = {**self.collected_kwargs, **kwargs}
        
        # 空调用时执行（用于可变参数方法的显式执行）
        is_empty_call = len(args) == 0 and len(kwargs) == 0
        
        # 检查必需参数是否完整
        params_complete = self._check_params_complete(new_args, new_kwargs)
        
        # 如果必需参数完整且没有可变参数，立即执行
        if params_complete and not (self.has_varargs or self.has_varkw):
            # 把所有参数转换为关键字参数，避免冲突
            final_kwargs = dict(new_kwargs)
            arg_idx = 0
            
            # 填充位置参数到关键字参数中
            for param in self.all_param_names:
                if param not in final_kwargs and arg_idx < len(new_args):
                    final_kwargs[param] = new_args[arg_idx]
                    arg_idx += 1
            
            # 可变位置参数（如果有）
            extra_args = new_args[arg_idx:]
            
            # 调用
            return self.func(self.instance, *extra_args, **final_kwargs)
        
        # 如果有可变参数且是空调用（没有新参数），执行方法
        if (self.has_varargs or self.has_varkw) and is_empty_call:
            # 对于可变参数，直接位置参数和关键字参数调用
            # 但先检查关键字和位置冲突
            # 检查是否有冲突
            num_pos_for_required = min(len(new_args), len(self.required_params))
            conflict = False
            for i in range(num_pos_for_required):
                if self.required_params[i] in new_kwargs:
                    conflict = True
                    break
            
            if conflict:
                # 有冲突，需要处理冲突：把位置参数对应的关键字参数移除
                # 先收集需要的参数
                used_keywords = set()
                for i in range(num_pos_for_required):
                    if self.required_params[i] in new_kwargs:
                        used_keywords.add(self.required_params[i])
                
                # 构建不带冲突关键字的kwargs
                final_kwargs = {}
                for k, v in new_kwargs.items():
                    if k not in used_keywords:
                        final_kwargs[k] = v
                
                return self.func(self.instance, *new_args, **final_kwargs)
            else:
                return self.func(self.instance, *new_args, **new_kwargs)
        
        # 继续收集参数
        return CurriedMethod(
            self.func, self.instance, self.required_params,
            self.has_varargs, self.has_varkw, self.all_param_names,
            self.method_name, new_args, new_kwargs
        )
    
    def __getattr__(self, name):
        if name == self.method_name:
            return lambda *args, **kwargs: self.__call__(*args, **kwargs)
        if hasattr(self.instance, name):
            attr = getattr(self.instance, name)
            if callable(attr):
                return attr
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


def curry_class(cls: type):
    """
    柯里化类装饰器
    对类中所有非魔法实例方法进行柯里化转换，支持链式调用
    支持位置参数、关键字参数和可变参数(*args, **kwargs)的柯里化
    
    用法示例:
    @curry_class
    class T:
        def add(self, a, b, c):
            return a + b + c
        
        def sum_all(self, a, b, *c, **k):
            total = a + b + sum(c)
            if k:
                total += sum(k.values())
            return total
    
    t = T()
    t.add(1).add(2).add(3)        # 返回 6
    t.sum_all(1).sum_all(2).sum_all(3, 4)  # 返回 10
    """
    if not inspect.isclass(cls):
        raise TypeError(f"@curry_class 装饰器仅允许应用于类，当前类型为: {type(cls).__name__}")
    
    original_init = cls.__init__
    
    def new_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        
        # 应该支持柯里化的魔法方法列表
        allowed_magic_methods = {
            # 调用相关（注意：__call__ 会在下面单独处理）
            '__call__',
            # 运算符重载
            '__add__', '__sub__', '__mul__', '__truediv__', '__floordiv__',
            '__mod__', '__divmod__', '__pow__', '__lshift__', '__rshift__',
            '__and__', '__or__', '__xor__',
            # 比较运算符
            '__lt__', '__le__', '__eq__', '__ne__', '__gt__', '__ge__',
            # 一元运算符
            '__neg__', '__pos__', '__abs__', '__invert__',
            # 序列/映射操作
            '__getitem__', '__contains__',
            # 原地操作
            '__iadd__', '__isub__', '__imul__', '__itruediv__', '__ifloordiv__',
            '__imod__', '__ipow__', '__ilshift__', '__irshift__',
            '__iand__', '__ior__', '__ixor__',
        }
        
        for name, method in cls.__dict__.items():
            if inspect.isfunction(method):
                # 排除特殊初始化相关的魔法方法
                if name in ('__init__', '__new__', '__del__', 
                           '__getattribute__', '__getattr__', '__setattr__', '__delattr__',
                           '__repr__', '__str__', '__format__',
                           '__len__', '__bool__',
                           '__enter__', '__exit__',
                           '__iter__', '__next__',
                           '__hash__', '__dir__', '__sizeof__'):
                    continue
                # 其他魔法方法检查是否在允许列表中
                if name.startswith('__') and name.endswith('__'):
                    if name not in allowed_magic_methods:
                        continue
                sig = get_signature(method)
                params = list(sig.parameters.values())
                
                # 获取需要的参数名列表（排除self、默认值参数、*args、**kwargs）
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
                
                @wraps(method)
                def create_curried(meth=method, req_params=required_params, 
                                  varargs=has_varargs, varkw=has_varkw, all_params=all_param_names, nm=name):
                    def curried_wrapper(*args, **kwargs):
                        # 创建临时柯里化对象来检查参数是否完整
                        temp_curried = CurriedMethod(
                            meth, self, req_params, varargs, varkw, all_params, nm, 
                            list(args), kwargs
                        )
                        
                        # 如果必需参数已经完整，执行方法
                        if temp_curried._check_params_complete():
                            return temp_curried.__call__()
                        
                        # 否则继续收集参数
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
    
    # ================= 魔法方法 =================
    
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
    
    # 测试1: 位置参数链式调用
    t1 = T()
    result1 = t1.add(1).add(2).add(3)
    print(f"测试 t.add(1).add(2).add(3) = {result1} (期望: 6)")
    assert result1 == 6, f"期望 6，实际 {result1}"
    
    # 测试2: 位置参数分组调用
    t2 = T()
    result2 = t2.add(1, 2).add(3)
    print(f"测试 t.add(1,2).add(3) = {result2} (期望: 6)")
    assert result2 == 6, f"期望 6，实际 {result2}"
    
    # 测试3: 直接调用
    t3 = T()
    result3 = t3.add(1, 2, 3)
    print(f"测试 t.add(1,2,3) = {result3} (期望: 6)")
    assert result3 == 6, f"期望 6，实际 {result3}"
    
    # 测试4: 关键字参数链式调用
    t4 = T()
    result4 = t4.add(a=1).add(b=2).add(c=3)
    print(f"测试 t.add(a=1).add(b=2).add(c=3) = {result4} (期望: 6)")
    assert result4 == 6, f"期望 6，实际 {result4}"
    
    # 测试5: 混合位置参数和关键字参数
    t5 = T()
    result5 = t5.add(1).add(b=2, c=3)
    print(f"测试 t.add(1).add(b=2, c=3) = {result5} (期望: 6)")
    assert result5 == 6, f"期望 6，实际 {result5}"
    
    # 测试6: 先关键字后位置参数
    t6 = T()
    result6 = t6.add(a=1).add(2, c=3)
    print(f"测试 t.add(a=1).add(2, c=3) = {result6} (期望: 6)")
    assert result6 == 6, f"期望 6，实际 {result6}"
    
    # 测试7: 乘法方法
    t7 = T()
    result7 = t7.multiply(5).multiply(6)
    print(f"测试 t.multiply(5).multiply(6) = {result7} (期望: 30)")
    assert result7 == 30, f"期望 30，实际 {result7}"
    
    # 测试8: 乘法方法关键字参数
    t8 = T()
    result8 = t8.multiply(x=7).multiply(y=8)
    print(f"测试 t.multiply(x=7).multiply(y=8) = {result8} (期望: 56)")
    assert result8 == 56, f"期望 56，实际 {result8}"
    
    # 测试9: 可变参数方法 - 基础调用
    t9 = T()
    result9 = t9.sum_all(1, 2)
    print(f"测试 t.sum_all(1, 2) = {result9} (期望: 3)")
    assert result9 == 3, f"期望 3，实际 {result9}"
    
    # 测试10: 可变参数方法 - 链式调用（使用空括号触发执行）
    t10 = T()
    result10 = t10.sum_all(1).sum_all(2).sum_all(3, 4).sum_all()
    print(f"测试 t.sum_all(1).sum_all(2).sum_all(3, 4).sum_all() = {result10} (期望: 10)")
    assert result10 == 10, f"期望 10，实际 {result10}"
    
    # 测试11: 可变参数方法 - 带关键字参数
    t11 = T()
    result11 = t11.sum_all(1, 2, 3, x=4, y=5)
    print(f"测试 t.sum_all(1, 2, 3, x=4, y=5) = {result11} (期望: 15)")
    assert result11 == 15, f"期望 15，实际 {result11}"
    
    # 测试12: 可变参数方法 - 链式关键字参数（使用空括号触发执行）
    t12 = T()
    result12 = t12.sum_all(1).sum_all(2, x=3).sum_all(y=4).sum_all()
    print(f"测试 t.sum_all(1).sum_all(2, x=3).sum_all(y=4).sum_all() = {result12} (期望: 10)")
    assert result12 == 10, f"期望 10，实际 {result12}"
    
    # 测试13: 装饰器错误处理（非类）
    try:
        @curry_class
        def not_a_class():
            pass
        print("[FAIL] 应该抛出错误")
        assert False, "装饰器应对非类对象抛出错误"
    except TypeError as e:
        print(f"[OK] 正确处理了非类装饰，错误: {e}")
    
    # ================ 魔法方法测试 ================
    
    # 测试14: __call__ 方法基础调用
    t14 = T()
    result14 = t14.__call__(2, 3, 4)
    print(f"测试 t.__call__(2, 3, 4) = {result14} (期望: 10)")
    assert result14 == 10, f"期望 10，实际 {result14}"
    
    # 测试15: __call__ 方法链式调用
    t15 = T()
    result15 = t15.__call__(2).__call__(3).__call__(4)
    print(f"测试 t.__call__(2).__call__(3).__call__(4) = {result15} (期望: 10)")
    assert result15 == 10, f"期望 10，实际 {result15}"
    
    # 测试16: __add__ 方法链式调用
    t16 = T()
    result16 = t16.__add__(5).__add__(3)
    print(f"测试 t.__add__(5).__add__(3) = {result16} (期望: 8)")
    assert result16 == 8, f"期望 8，实际 {result16}"
    
    # 测试17: __getitem__ 方法链式调用参数
    t17 = T()
    t17.data = [10, 20, 30]
    result17 = t17.__getitem__(2)
    print(f"测试 t.__getitem__(2) = {result17} (期望: 30)")
    assert result17 == 30, f"期望 30, 实际 {result17}"
    
    # 测试18: __getitem__ 直接调用带默认值
    t18 = T()
    t18.data = [10, 20, 30]
    result18 = t18.__getitem__(5, -1)
    print(f"测试 t.__getitem__(5, -1) = {result18} (期望: -1)")
    assert result18 == -1, f"期望 -1, 实际 {result18}"
    
    # 测试19: 分步演示__call__ 的使用方式
    t19 = T()
    curried = t19.__call__(2)
    curried = curried.__call__(3)
    result19 = curried.__call__(4)
    print(f"分步测试 t.__call__(2).__call__(3).__call__(4) = {result19} (期望: 10)")
    assert result19 == 10, f"期望 10, 实际 {result19}"
    
    # 测试20: 混合位置参数和关键字参数
    t20 = T()
    result20 = t20.__call__(x=2).__call__(3).__call__(z=4)
    # result21 = t20(x=2)(z=4)(3) 
    # result21 = t20(2,3)(4)
    print(f"混合测试 t.__call__(x=2).__call__(3).__call__(z=4) = {result20} (期望: 10)")
    assert result20 == 10, f"期望 10, 实际 {result20}"
    
    print("\n=== 所有测试通过 ===")


if __name__ == "__main__":
    test_curry_decorator()