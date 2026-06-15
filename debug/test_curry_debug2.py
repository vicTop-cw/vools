"""调试 curry 装饰器问题"""
import sys
sys.path.insert(0, '.')

from vools.decorators import curry as curry_decorator
from vools.decorators.curry_core import CurryDescriptor, Curried

def outer_func():
    """外部函数，用于创建 __qualname__ 包含 '.' 的函数"""
    @curry_decorator
    def process(a, b, c):
        return a + b + c
    return process

process = outer_func()

print(f"process type: {type(process)}")
print(f"process.__class__.__name__: {process.__class__.__name__}")
print(f"is CurryDescriptor: {isinstance(process, CurryDescriptor)}")
print(f"is Curried: {isinstance(process, Curried)}")

if isinstance(process, CurryDescriptor):
    print(f"\npre_attrs:")
    for k, v in process.pre_attrs.items():
        if k == 'params':
            print(f"  {k}: {list(v.keys())}")
        elif k == 'required_args':
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")

print("\n=== 尝试调用 process(1) ===")
try:
    p1 = process(1)
    print(f"成功创建 p1")
    print(f"p1 type: {type(p1)}")
    print(f"p1.bound_args: {p1.bound_args}")
    print(f"p1.required_args: {p1.required_args}")
    print(f"p1.params: {list(p1.params.keys())}")
except Exception as e:
    import traceback
    print(f"错误: {e}")
    traceback.print_exc()