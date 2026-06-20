"""测试清空缓存后对 curry 的影响"""
import sys
sys.path.insert(0, '.')

from vools.cache import get_signature, clear_cache, _preload_builtins
from vools.decorators import curry as curry_decorator

# 先使用 curry
@curry_decorator
def process1(a, b, c):
    return a + b + c

print("第一次定义的函数:")
print("  type:", type(process1).__name__)
result = process1(1)(2)(3)
print("  process1(1)(2)(3) =", result)

# 清空缓存
print("\n清空缓存...")
clear_cache()

# 再次使用 curry
@curry_decorator
def process2(a, b, c):
    return a + b + c

print("\n清空缓存后定义的函数:")
print("  type:", type(process2).__name__)
try:
    result = process2(1)(2)(3)
    print("  process2(1)(2)(3) =", result)
except Exception as e:
    print("  失败:", e)