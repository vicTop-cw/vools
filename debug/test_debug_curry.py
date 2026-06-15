"""调试 curry 装饰器问题"""
import sys
sys.path.insert(0, '.')

from vools import curry
from vools.decorators.curry_core import CurryDescriptor, Curried

@curry
def process(a, b, c):
    return a + b + c

print("=== 初始状态 ===")
print(f"process type: {type(process)}")
print(f"process.__class__.__name__: {process.__class__.__name__}")
print(f"is CurryDescriptor: {isinstance(process, CurryDescriptor)}")
print(f"is Curried: {isinstance(process, Curried)}")

if isinstance(process, CurryDescriptor):
    print(f"\nCurryDescriptor pre_attrs:")
    for k, v in process.pre_attrs.items():
        if k == 'params':
            print(f"  {k}: {list(v.keys())}")
        elif k == 'required_args':
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")

print("\n=== 第一次调用 process(1) ===")
try:
    p1 = process(1)
    print(f"成功创建 p1")
    print(f"p1 type: {type(p1)}")
    print(f"p1.bound_args: {p1.bound_args}")
    print(f"p1.required_args: {p1.required_args}")
    print(f"p1.params: {list(p1.params.keys())}")
except Exception as e:
    print(f"失败: {e}")
