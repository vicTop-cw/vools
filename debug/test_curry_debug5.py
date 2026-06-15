"""调试 CurryDescriptor 创建的 Curried 对象"""
import sys
sys.path.insert(0, '.')

from vools.decorators import curry as curry_decorator
from vools.decorators.curry_core import Curried, CurryDescriptor

def test_func():
    @curry_decorator
    def process(a, b, c):
        return a + b + c
    
    print("process type:", type(process).__name__)
    print("is CurryDescriptor:", isinstance(process, CurryDescriptor))
    
    if isinstance(process, CurryDescriptor):
        print("\npre_attrs params type:", type(process.pre_attrs["params"]))
        print("pre_attrs params:", process.pre_attrs["params"])
        print("pre_attrs required_args:", process.pre_attrs["required_args"])
        
        print("\n创建新的 Curried 对象...")
        new_curried = Curried(process.func, is_strict=process.is_strict, delaied=process.delaied,** process.pre_attrs)
        print("new_curried.params type:", type(new_curried.params))
        print("new_curried.params:", new_curried.params)
        print("new_curried.required_args:", new_curried.required_args)
        print("new_curried.bound_args:", new_curried.bound_args)

test_func()