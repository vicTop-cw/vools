"""
测试 _copy_methods_from_parents 函数
"""
import sys
sys.path.insert(0, r'E:\IDEProjects\AI\vools')

from Temp.class_fusion import fuse_classes

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

# 测试：检查融合类的方法
print("测试：检查融合类的方法")
AB = fuse_classes(A, B, name="AB")

print(f"\n融合类 AB 的方法:")
for attr_name in dir(AB):
    if not attr_name.startswith('_'):
        attr = getattr(AB, attr_name, None)
        if callable(attr):
            print(f"  {attr_name}: {attr}")

print(f"\n测试调用:")
obj = AB(x=10, y=20)
print(f"  obj.foo() = {obj.foo()}")
print(f"  obj.bar() = {obj.bar()}")
