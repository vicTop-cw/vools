"""
详细调试：检查 ClassFusion.wrap_method
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

# 调试：检查 ClassFusion 内部状态
print("调试：检查 ClassFusion 内部状态")
fusion = ClassFusion(A, B)

def my_before(self, *args, **kwargs):
    print(f"  [before] x={self.x}")

fusion.wrap_method('foo', before=my_before)

print(f"  fusion._method_wrappers = {fusion._method_wrappers}")
print(f"  fusion._method_wrappers['foo'] = {fusion._method_wrappers.get('foo')}")
print(f"  before = {fusion._method_wrappers.get('foo', {}).get('before')}")

# 执行融合
print("\n执行融合...")
AB = fusion.fuse()

# 检查 foo 方法的闭包
foo_method = getattr(AB, 'foo')
print(f"\n检查融合后的 foo 方法:")
print(f"  foo = {foo_method}")
if hasattr(foo_method, '__closure__') and foo_method.__closure__:
    print(f"  闭包变量:")
    for i, cell in enumerate(foo_method.__closure__):
        try:
            content = cell.cell_contents
            print(f"    [{i}] {content}")
        except Exception as e:
            print(f"    [{i}] Error: {e}")

# 测试调用
print("\n测试调用...")
obj = AB(x=10, y=20)
try:
    result = obj.foo()
    print(f"  obj.foo() = {result}")
except Exception as e:
    print(f"  调用失败: {e}")

print("\n调试完成")
