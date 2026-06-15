"""调试 pytest 运行时的 curry 问题"""
import sys
sys.path.insert(0, '.')

from vools.decorators import curry as curry_decorator

print(f"curry_decorator type: {type(curry_decorator)}")
print(f"curry_decorator: {curry_decorator}")

@curry_decorator
def process(a, b, c):
    return a + b + c

print(f"\nprocess type: {type(process)}")
print(f"process.__class__.__name__: {process.__class__.__name__}")

if hasattr(process, 'pre_attrs'):
    print(f"\npre_attrs:")
    for k, v in process.pre_attrs.items():
        print(f"  {k}: {v}")

if hasattr(process, 'bound_args'):
    print(f"\nbound_args: {process.bound_args}")
    print(f"required_args: {getattr(process, 'required_args', 'N/A')}")

print("\n=== 尝试调用 ===")
try:
    p1 = process(1)
    print(f"p1 = {p1}")
    print(f"p1.bound_args: {p1.bound_args}")
    print(f"p1.required_args: {p1.required_args}")
except Exception as e:
    import traceback
    print(f"错误: {e}")
    traceback.print_exc()
