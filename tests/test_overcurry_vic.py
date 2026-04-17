"""
测试 overcurry 和 vic 类的功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from vools import (
    overcurry,
    vicText,
    vicList,
)


# 测试 overcurry 功能
def test_overcurry():
    """测试 overcurry 装饰器"""
    @overcurry
    def add(a, b):
        return a + b
    
    @add.register
    def add(a, b, c):
        return a + b + c
    
    @add.register
    def add(a, b, c, d):
        return a + b + c + d
    
    # 测试柯里化功能
    assert add(1)(2) == 3
    # 注意：add(1, 2) 返回的是一个整数，不能被再次调用
    # 所以我们直接测试 add(1, 2, 3) 来验证三参数版本的重载
    assert add(1, 2, 3) == 6
    # 测试四参数版本的重载
    assert add(1, 2, 3, 4) == 10
    
    # 测试类型重载
    @overcurry(is_strict=True)
    def process(a: int, b: int):
        return a + b
    
    @process.register
    def process(a: str, b: str):
        return a + b
    
    assert process(1)(2) == 3
    assert process("hello")(" world") == "hello world"


# 测试 vic 类功能
def test_vic_classes():
    """测试 vic 类"""
    # 测试 vicText
    text = vicText("Hello, World!")
    assert text.upper() == "HELLO, WORLD!"
    assert text.lower() == "hello, world!"
    
    # 测试 vicList
    lst = vicList([1, 2, 3, 4, 5])
    assert lst.map(lambda x: x * 2).collect() == [2, 4, 6, 8, 10]
    assert lst.filter(lambda x: x > 2).collect() == [3, 4, 5]
    assert lst.unique.collect() == [1, 2, 3, 4, 5]


# 测试 Mixer 功能
# 由于 Mixer 和 mixer 已被移除，暂时跳过测试
# def test_mixer():
#     """测试 Mixer 类"""
#     class A:
#         def method_a(self):
#             return "A.method_a"
#         
#         def common_method(self):
#             return "A.common_method"
#     
#     class B:
#         def method_b(self):
#             return "B.method_b"
#         
#         def common_method(self):
#             return "B.common_method"
#     
#     a = A()
#     b = B()
#     
#     # 创建混合器
#     m = mixer(a, b)
#     
#     # 测试属性访问
#     assert m.method_a() == "A.method_a"
#     assert m.method_b() == "B.method_b"
#     # 测试优先级（先添加的对象优先级高）
#     assert m.common_method() == "A.common_method"


if __name__ == "__main__":
    test_overcurry()
    test_vic_classes()
    # test_mixer()  # 由于 Mixer 和 mixer 已被移除，暂时跳过测试
    print("所有测试通过!")
