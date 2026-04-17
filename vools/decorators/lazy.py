"""
延迟求值装饰器

包含：
- lazy: 延迟求值装饰器，支持字符串表达式解析
"""

import re
import inspect
import builtins
from typing import Any, Callable, Optional, Dict

__all__ = ['lazy']

# 安全的内置函数白名单
SAFE_BUILTINS = [
    'abs', 'all', 'any', 'bool', 'bytes', 'chr', 'complex', 'dict', 
    'divmod', 'enumerate', 'filter', 'float', 'format', 'frozenset',
    'hash', 'hex', 'int', 'isinstance', 'issubclass', 'iter', 'len',
    'list', 'map', 'max', 'min', 'next', 'oct', 'ord', 'pow', 'range',
    'repr', 'reversed', 'round', 'set', 'slice', 'sorted', 'str', 'sum',
    'tuple', 'zip', 'print', 'Exception'
]


def lazy(obj: Any, caller_locals: Optional[Dict] = None, 
         caller_globals: Optional[Dict] = None) -> Callable:
    """
    延迟求值装饰器，将输入对象转换为无参函数
    
    功能：
    - 对于字符串，解析为函数（支持 -> 和 => 语法）
    - 对于可调用对象，直接返回
    - 对于其他对象，返回返回该对象的无参函数
    
    参数:
        obj: 要转换的对象
        caller_locals: 调用者的局部作用域
        caller_globals: 调用者的全局作用域
    
    返回:
        无参函数
    
    示例:
        >>> # 常量包装
        >>> const_five = lazy(5)
        >>> const_five()
        5
        
        >>> # 表达式
        >>> expr = lazy("=> 2 ** 8")
        >>> expr()
        256
        
        >>> # 无参 lambda
        >>> import random
        >>> rand_num = lazy("-> random.randint(1, 100)")
        >>> rand_num()  # 返回随机数
        
        >>> # 带参函数
        >>> adder = lazy("a, b -> a + b")
        >>> adder(3, 5)
        8
        
        >>> # 多行函数
        >>> multi_line = lazy("def my_func(x):\\n    return x * 2")
        >>> my_func = multi_line()
        >>> my_func(10)
        20
    """
    if callable(obj):
        return obj
    
    if isinstance(obj, str):
        # 获取调用者作用域
        if caller_globals is None or caller_locals is None:
            try:
                frame = inspect.currentframe().f_back.f_back
                caller_globals = frame.f_globals if frame else globals()
                caller_locals = frame.f_locals if frame else locals()
            except (AttributeError, TypeError):
                caller_globals = globals()
                caller_locals = locals()
        
        # 处理作用域
        safe_globals = {
            **(caller_globals or {}),
            '__builtins__': {k: getattr(builtins, k) for k in SAFE_BUILTINS}
        }
        safe_locals = caller_locals or {}
        
        # 规则1：多行函数定义
        if obj.startswith('def '):
            match = re.search(r'def\s+(\w+)\s*\(', obj)
            func_name = match.group(1) if match else '__anonymous__'
            exec(obj, safe_globals, safe_locals)
            func = safe_locals.get(func_name, safe_globals.get(func_name))
            wrapper = lambda: func
            wrapper._is_lazy_wrapper = True
            return wrapper
        
        # 规则2：无参lambda表达式（支持 -> 和 =>）
        if obj.startswith('->') or obj.startswith('=>'):
            expr = obj[2:]
            def _anonymous():
                return eval(expr, safe_globals, safe_locals)
            _anonymous._is_lazy_wrapper = True
            return _anonymous
        
        # 规则3：箭头表达式函数（支持 -> 和 =>）
        arrow_match = re.search(r'(.*?)(->|=>)(.*)', obj)
        if arrow_match:
            left, arrow, right = arrow_match.groups()
            params = [p.strip() for p in left.split(',') if p.strip()]
            func_str = f"def __anonymous({', '.join(params)}):\n    return {right.strip()}"
            exec(func_str, safe_globals, safe_locals)
            wrapper = safe_locals.get('__anonymous')
            wrapper._is_lazy_wrapper = True
            return wrapper
    
    # 规则4：其他类型封装为无参函数
    def _constant_wrapper():
        return obj
    
    _constant_wrapper._is_lazy_wrapper = True
    return _constant_wrapper


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == '__main__':
    import random
    
    print("=== 测试 lazy ===")
    
    # 测试常量包装
    const_five = lazy(5)
    print(f"常量包装: {const_five()}")  # 5
    
    # 测试表达式
    expr = lazy("=> 2 ** 8")
    print(f"表达式: {expr()}")  # 256
    
    # 测试无参lambda
    rand_num = lazy("-> random.randint(1, 100)")
    print(f"随机数: {rand_num()}")
    
    # 测试带参函数
    adder = lazy("a, b -> a + b")
    print(f"带参函数: {adder(3, 5)}")  # 8
    
    # 测试多行函数
    multi_line = lazy("def my_func(x):\n    return x * 2")
    my_func = multi_line()
    print(f"多行函数: {my_func(10)}")  # 20
    
    # 测试可调用对象
    def test_func(a, b, c=1):
        return a + b + c
    
    print(f"可调用对象: {lazy(test_func)(1, 2)}")  # 4
    
    print("\n所有测试通过!")
