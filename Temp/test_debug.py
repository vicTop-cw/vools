"""
简化测试：专门测试 wrap_method 功能
"""
import sys
sys.path.insert(0, r'E:\IDEProjects\AI\vools')

from Temp.class_fusion import fuse_classes, ClassFusion

# 定义测试类
class A:
    def __init__(self, x=0, **kwargs):
        self.x = x
    
    def foo(self):
        return f"A.foo (x={self.x})"

class B:
    def __init__(self, y=0, **kwargs):
        self.y = y
    
    def bar(self):
        return f"B.bar (y={self.y})"

# 测试 1: 使用 fuse_classes 和 method_wrappers
print("测试 1: fuse_classes with method_wrappers")
try:
    def my_before(self, *args, **kwargs):
        print(f"  [before] self.x={self.x}, self.y={self.y}")
    
    AB = fuse_classes(
        A, B,
        name="AB",
        method_wrappers={'foo': {'before': my_before}}
    )
    
    obj = AB(x=10, y=20)
    print(f"  obj.foo() = {obj.foo()}")
    print("测试 1 通过\n")
except Exception as e:
    print(f"测试 1 失败: {e}\n")

# 测试 2: 使用 ClassFusion
print("测试 2: ClassFusion with wrap_method")
try:
    fusion = ClassFusion(A, B)
    
    def my_before2(self, *args, **kwargs):
        print(f"  [before2] x={self.x}, y={self.y}")
    
    fusion.wrap_method('foo', before=my_before2)
    
    AB2 = fusion.fuse()
    obj2 = AB2(x=100, y=200)
    print(f"  obj2.foo() = {obj2.foo()}")
    print("测试 2 通过\n")
except Exception as e:
    print(f"测试 2 失败: {e}\n")

# 测试 3: 检查 wrapped_method 的闭包
print("测试 3: 检查闭包变量")
try:
    AB3 = fuse_classes(
        A, B,
        name="AB3",
        method_wrappers={'foo': {'before': lambda self: print("hello")}}
    )
    
    # 检查 foo 方法的闭包
    foo_method = getattr(AB3, 'foo')
    if hasattr(foo_method, '__closure__') and foo_method.__closure__:
        print(f"  foo 方法的闭包变量:")
        for cell in foo_method.__closure__:
            print(f"    {cell.cell_contents}")
    else:
        print("  foo 方法没有闭包（可能是 lambda）")
    
    print("测试 3 完成\n")
except Exception as e:
    print(f"测试 3 失败: {e}\n")

print("所有测试完成")
