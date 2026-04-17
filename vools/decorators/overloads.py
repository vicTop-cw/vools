import inspect
from typing import Any, Callable, Optional, List, Tuple, Union, Dict
import wrapt


"""参数个数相同的情况，*args, **kws 不要指望只靠数据类型 来选择执行的函数"""
__all__ = ['overloads']
"""
    python
    使用 wrapt 库 写个 装饰器 overloads ,使其能实现 类似 scala 中的重载

    示例1、
        
    @overloads
    def add(a,b):
        pass

    @overloads
    def add(a,b,c):
        pass
        

    示例2、
        
    @overloads
    def add(a:int,b:int):
        pass

    @overloads
    def add(a:str,b:str):
        pass


    示例3、
        
    @overloads
    def add(a:int,b:int):
        pass

    @overloads
    def add(a,b):
        pass

    当调用 add(1,2) =>  报错，ambiguous 


    示例4、
        
    @overloads
    def add(a:int,b:int):
        pass

    @overloads
    def add(a:str,b:str):
        pass


    @overloads
    def add1(a:int,b:int):
        pass

    @overloads
    def add1(a:str,b:str):
        pass

    class Add:
        
        @staticmethod
        @overloads
        def add(a:str,b:str):
            pass
            
        @staticmethod
        @overloads
        def add(a:int,b:int):
            pass
        
        
        
        @overloads
        def add1(self,a:str,b:str):
            pass
            

        @overloads
        def add1(self,a:int,b:int):
            pass


    def outer():
        
        @overloads
        def add1(self,a:str,b:str):
            pass
            

        @overloads
        def add1(self,a:int,b:int):
            pass


    同级作用域的同名函数才是多个重载

    示例5、



    @overloads
    def add1(a，b):
        pass
        

    @overloads
    def add1(a,b):
        pass
        
        
    同级作用域，同名函数 还签名都相同， 不调用不报错，一调用准报错， 报错，ambiguous； 因为都符合2个函数的原则


    示例6、



    @overloads
    def add1(a，b):
        pass
        

    @overloads
    def add1(a,b，c=None):
        pass


    add1(a，b) 永远都是报错 ambiguous ；因为 add1(a,b，c=None) 也能 调用



"""
# 注册表：(module, scope) -> {func_name: [impl1, impl2, ...]}
_registry: Dict[Tuple[str, str], Dict[str, List[Callable]]] = {}
# 包装器缓存：避免重复创建
_wrappers_cache: Dict[Tuple[str, str], Dict[str, Callable]] = {}

def overloads(func):
    """装饰器：注册函数重载，返回统一的调用分发器"""
    module = func.__module__
    qualname = func.__qualname__
    func_name = func.__name__
    scope = qualname.rpartition('.')[0]          # 类名或空字符串
    key = (module, scope)

    # 注册当前实现
    scope_dict = _registry.setdefault(key, {})
    impls = scope_dict.setdefault(func_name, [])
    impls.append(func)

    # 如果已经存在包装器，直接返回（保证同名函数共享同一分发器）
    cache_scope = _wrappers_cache.setdefault(key, {})
    if func_name in cache_scope:
        return cache_scope[func_name]

    # 定义分发器（包装函数，在每次调用时执行）
    def dispatcher(wrapped, instance, args, kwargs):
        # 获取该作用域下该函数的所有重载实现
        current_impls = _registry[key][func_name]
        matches = []
        # 构建实际调用参数：实例方法时 instance 作为第一个参数
        call_args = (instance,) + args if instance is not None else args

        for impl in current_impls:
            sig = inspect.signature(impl)
            try:
                bound = sig.bind(*call_args, **kwargs)
                bound.apply_defaults()
                # 检查类型注解
                type_ok = True
                for param_name, arg in bound.arguments.items():
                    param = sig.parameters[param_name]
                    if param.annotation != inspect.Parameter.empty:
                        if not isinstance(arg, param.annotation):
                            type_ok = False
                            break
                if type_ok:
                    matches.append(impl)
            except TypeError:
                # 参数数量不匹配，跳过
                continue

        if len(matches) == 0:
            raise TypeError(f"No matching overload for {func_name}({call_args}, {kwargs})")
        if len(matches) > 1:
            raise TypeError(f"Ambiguous call to overloaded function {func_name}")

        # 调用匹配的实现
        if instance is not None:
            return matches[0](instance, *args, **kwargs)
        else:
            return matches[0](*args, **kwargs)

    # 使用 wrapt.FunctionWrapper 创建包装器，保留原始函数的元数据
    wrapper = wrapt.FunctionWrapper(func, dispatcher)
    cache_scope[func_name] = wrapper
    return wrapper

# 测试辅助：清除注册表，用于隔离每个示例
def reset_overloads():
    """重置全局注册表，用于测试隔离"""
    global _registry, _wrappers_cache
    _registry.clear()
    _wrappers_cache.clear()

def test_main():
    # 示例1
    reset_overloads()
    @overloads
    def add(a, b):
        return a + b

    @overloads
    def add(a, b, c):
        return a + b + c

    print("="*60)
    print("Example 1")
    print(add(1, 2))       # 3
    print(add(1, 2, 3))    # 6
    print("="*60)

    # 示例2
    reset_overloads()
    @overloads
    def add(a: int, b: int):
        return a + b

    @overloads
    def add(a: str, b: str):
        return a + b

    print("="*60)
    print("Example 2")
    print(add(1, 2))       # 3
    print(add("x", "y"))   # "xy"
    print("="*60)

    # 示例3
    reset_overloads()
    @overloads
    def add(a: int, b: int):
        return a + b

    @overloads
    def add(a, b):         # 无注解，匹配任何类型
        return a + b

    print("="*60)
    print("Example 3")
    try:
        add(1, 2)   # TypeError: Ambiguous call...
    except TypeError as e:
        print(e)
    print("="*60)

    # 示例4
    reset_overloads()
    class Add:
        @staticmethod
        @overloads
        def add(a: str, b: str):
            return a + b

        @staticmethod
        @overloads
        def add(a: int, b: int):
            return a + b

        @overloads
        def add1(self, a: str, b: str):
            return a + b

        @overloads
        def add1(self, a: int, b: int):
            return a + b

    def outer():
        @overloads
        def add1(a: str, b: str):
            return a + b

        @overloads
        def add1(a: int, b: int):
            return a + b
        return add1

    print("="*60)
    print("Example 4")
    print(Add.add(10, 20))          # 30
    print(Add.add("a", "b"))        # "ab"
    obj = Add()
    print(obj.add1(100, 200))       # 300
    print(obj.add1("x", "y"))       # "xy"

    inner_add = outer()
    print(inner_add(5, 6))          # 11
    print(inner_add("c", "d"))      # "cd"
    print("="*60)

    # 示例5
    reset_overloads()
    @overloads
    def add1(a, b):
        return a + b

    @overloads
    def add1(a, b):   # 签名相同
        return a - b

    print("="*60)
    print("Example 5")
    try:
        add1(3, 2)   # TypeError: Ambiguous call...
    except TypeError as e:
        print(e)
    print("="*60)

    # 示例6
    reset_overloads()
    @overloads
    def add1(a, b):
        return a + b

    @overloads
    def add1(a, b, c=None):
        return a + b + (c or 0)

    print("="*60)
    print("Example 6")
    print(add1(1, 2,3))       # 3
    try:
        add1(1, 2)   # TypeError: Ambiguous call...
    except TypeError as e:
        print(e)
    print("="*60)

if __name__ == '__main__':
    test_main()
    