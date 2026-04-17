"""
测试通用工具模块
"""

import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.utils import stuff, identity, const, compose, pipe


def test_basic_functions():
    """测试基础工具函数"""
    print("=== 测试基础工具函数 ===")
    
    # identity
    assert identity(5) == 5
    assert identity("hello") == "hello"
    assert identity([1, 2, 3]) == [1, 2, 3]
    
    # const
    f = const(10)
    assert f() == 10
    assert f(1, 2, 3) == 10
    assert f(a=1, b=2) == 10
    
    # compose
    f = compose(lambda x: x + 1, lambda x: x * 2)
    assert f(3) == 7  # (3 * 2) + 1
    
    f = compose(lambda x: x * 3, lambda x: x + 1, lambda x: x * 2)
    assert f(2) == 15  # ((2 * 2) + 1) * 3
    
    # pipe
    f = pipe(lambda x: x * 2, lambda x: x + 1)
    assert f(3) == 7  # (3 * 2) + 1
    
    f = pipe(lambda x: x * 2, lambda x: x + 1, lambda x: x * 3)
    assert f(2) == 15  # ((2 * 2) + 1) * 3
    
    print("[OK] 基础工具函数测试通过")


def test_stuff():
    """测试 stuff 类"""
        
    print("=" * 60)
    print("测试 stuff 装饰器")
    print("=" * 60)

    # 测试基本功能
    print("\n=== 测试基本功能 ===")

    @stuff
    def add(a, b, c):
        return a + b + c

    result = add(1)(2)(3)()
    print(f"add(1)(2)(3)() = {result}")
    assert result == 6

    result = add(1, 2, 3)()
    print(f"add(1, 2, 3)() = {result}")
    assert result == 6

    print("[OK] 基本功能测试通过")

    # 测试参数依赖注入
    print("\n=== 测试参数依赖注入 ===")

    @stuff
    def multiply(a, b, c):
        return a * b * c

    @multiply.register
    def get_a():
        return 2

    @multiply.register(param_name=['b', 'c'])
    def get_bc():
        return 3, 4

    result = multiply()
    print(f"multiply() = {result}")
    assert result == 24

    print("[OK] 参数依赖注入测试通过")

    print("\n" + "=" * 60)
    print("stuff [SUCCESS] 所有测试通过!")
    print("=" * 60)


if __name__ == '__main__':
    test_basic_functions()
    test_stuff()
    print("\n[SUCCESS] 所有通用工具测试通过!")
