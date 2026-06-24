"""测试 vools 主模块导入"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("测试 vools 主模块导入")
print("=" * 60)

# 测试主模块导入
print("\n=== 测试主模块导入 ===")
import vools

print(f"vools version: {vools.__version__}")
print(f"Available exports: {len(vools.__all__)} items")

# 测试装饰器
print("\n=== 测试装饰器 ===")
from vools import memorize, once, lazy, smart_partial, overload

print(f"memorize: {memorize}")
print(f"once: {once}")
print(f"lazy: {lazy}")
print(f"smart_partial: {smart_partial}")    
print(f"overload: {overload}")

print("[OK] 装饰器导入成功")

# 测试函数式编程工具
print("\n=== 测试函数式编程工具 ===")
from vools import Pipe, Ops, Seq, P

print(f"Pipe: {Pipe}")
print(f"Ops: {Ops}")
print(f"Seq: {Seq}")
print(f"P: {P}")

print("[OK] 函数式编程工具导入成功")

# 测试通用工具
print("\n=== 测试通用工具 ===")
from vools import stuff, identity, const, compose, pipe

print(f"stuff: {stuff}")
print(f"identity: {identity}")
print(f"const: {const}")
print(f"compose: {compose}")
print(f"pipe: {pipe}")

print("[OK] 通用工具导入成功")

# 测试可选模块
print("\n=== 测试可选模块 ===")
print(f"DATA_AVAILABLE: {vools.DATA_AVAILABLE}")
print(f"OOP_AVAILABLE: {vools.OOP_AVAILABLE}")
print(f"DATETIME_AVAILABLE: {vools.DATETIME_AVAILABLE}")

if vools.DATA_AVAILABLE:
    print(f"data module: {vools.data}")
if vools.OOP_AVAILABLE:
    print(f"oop module: {vools.oop}")
if vools.DATETIME_AVAILABLE:
    print(f"datetime module: {vools.datetime}")

print("[OK] 可选模块检查成功")

print("\n" + "=" * 60)
print("[SUCCESS] 所有导入测试通过!")
print("=" * 60)
