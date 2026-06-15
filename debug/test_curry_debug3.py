"""调试 curry 装饰器问题 - 详细版"""
import sys
sys.path.insert(0, '.')

from vools.decorators import curry as curry_decorator
from vools.decorators.curry_core import CurryDescriptor, Curried, _get_func_info

def test_func():
    @curry_decorator
    def process(a, b, c):
        return a + b + c
    
    print(f"process type: {type(process).__name__}")
    print(f"is CurryDescriptor: {isinstance(process, CurryDescriptor)}")
    
    if isinstance(process, CurryDescriptor):
        print(f"\n=== CurryDescriptor pre_attrs ===")
        for k, v in process.pre_attrs.items():
            if k == 'params':
                print(f"  {k}: {list(v.keys())}")
            elif k == 'required_args':
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {v}")
        
        print(f"\n=== 调用 process(1) ===")
        # 模拟 CurryDescriptor.__call__
        from vools.decorators.curry_core import Curried
        new_curried = Curried(process.func, is_strict=process.is_strict, delaied=process.delaied, **process.pre_attrs)
        print(f"新 Curried 对象:")
        print(f"  bound_args: {new_curried.bound_args}")
        print(f"  required_args: {new_curried.required_args}")
        print(f"  params: {list(new_curried.params.keys())}")
        
        print(f"\n=== 调用 new_curried(1) ===")
        try:
            p1 = new_curried(1)
            print(f"成功创建 p1")
            print(f"p1.bound_args: {p1.bound_args}")
            print(f"p1.required_args: {p1.required_args}")
        except Exception as e:
            import traceback
            print(f"错误: {e}")
            traceback.print_exc()

test_func()