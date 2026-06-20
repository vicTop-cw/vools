"""
测试装饰器两种调用方式

验证所有装饰器都支持：
1. @decorator 直接调用
2. @decorator(params) 带参数调用
"""

import sys
import os
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.decorators.cache import memorize, once, persist
from vools.decorators.control import retry, rerun, excepts, suppress, ignore
from vools.decorators.overload import strict
from vools.decorators.curry_core import curry


def test_memorize():
    """测试 memorize 两种调用方式"""
    print("\n=== 测试 memorize ===")
    
    # 直接调用
    @memorize
    def func1():
        return time.time()
    
    result1 = func1()
    result2 = func1()
    assert result1 == result2, "memorize 直接调用失败"
    print("✓ @memorize 直接调用成功")
    
    # 带参数调用
    @memorize(duration=1)
    def func2():
        return time.time()
    
    result1 = func2()
    time.sleep(0.5)
    result2 = func2()
    assert result1 == result2, "memorize 带参数调用失败"
    print("✓ @memorize(duration=1) 带参数调用成功")


def test_once():
    """测试 once 两种调用方式"""
    print("\n=== 测试 once ===")
    
    # 直接调用
    counter = [0]
    
    @once
    def func1():
        counter[0] += 1
        return counter[0]
    
    result1 = func1()
    result2 = func1()
    assert result1 == result2 == 1, "once 直接调用失败"
    print("✓ @once 直接调用成功")
    
    # 带参数调用
    counter2 = [0]
    
    @once(force_default=True)
    def func2():
        counter2[0] += 1
        return counter2[0]
    
    result1 = func2()
    result2 = func2()
    assert result1 != result2, "once 带参数调用失败"
    print("✓ @once(force_default=True) 带参数调用成功")


def test_persist():
    """测试 persist 两种调用方式"""
    print("\n=== 测试 persist ===")
    
    # 直接调用
    @persist
    def func1():
        return {"data": "value1"}
    
    result1 = func1()
    result2 = func1()
    assert result1 == result2, "persist 直接调用失败"
    print("✓ @persist 直接调用成功")
    
    # 带参数调用
    @persist(file_key="test_cache", force=True)
    def func2():
        return {"data": "value2"}
    
    result = func2()
    assert result["data"] == "value2", "persist 带参数调用失败"
    print("✓ @persist(file_key='test_cache', force=True) 带参数调用成功")


def test_retry():
    """测试 retry 两种调用方式"""
    print("\n=== 测试 retry ===")
    
    # 直接调用
    counter = [0]
    
    @retry
    def func1():
        counter[0] += 1
        if counter[0] < 2:
            raise ValueError("测试错误")
        return "成功"
    
    result = func1()
    assert result == "成功", "retry 直接调用失败"
    print("✓ @retry 直接调用成功")
    
    # 带参数调用
    counter2 = [0]
    
    @retry(tries=2, delay=0.1)
    def func2():
        counter2[0] += 1
        if counter2[0] < 2:
            raise ValueError("测试错误")
        return "成功"
    
    result = func2()
    assert result == "成功", "retry 带参数调用失败"
    print("✓ @retry(tries=2, delay=0.1) 带参数调用成功")


def test_rerun():
    """测试 rerun 两种调用方式"""
    print("\n=== 测试 rerun ===")
    
    # 直接调用
    @rerun
    def func1():
        return "成功"
    
    result = func1()
    assert result == "成功", "rerun 直接调用失败"
    print("✓ @rerun 直接调用成功")
    
    # 带参数调用
    counter = [0]
    
    @rerun(until=lambda x: x == "成功", interval=0.1, time_out=2)
    def func2():
        counter[0] += 1
        if counter[0] < 3:
            return "pending"
        return "成功"
    
    result = func2()
    assert result == "成功", "rerun 带参数调用失败"
    print("✓ @rerun(until=lambda x: x == '成功') 带参数调用成功")


def test_excepts():
    """测试 excepts 两种调用方式"""
    print("\n=== 测试 excepts ===")
    
    # 直接调用
    @excepts
    def func1():
        raise ValueError("测试错误")
    
    result = func1()
    assert result is None, "excepts 直接调用失败"
    print("✓ @excepts 直接调用成功")
    
    # 带参数调用
    @excepts(exc_type=ValueError, handler=lambda e: f"错误: {e}")
    def func2():
        raise ValueError("测试错误")
    
    result = func2()
    assert result == "错误: 测试错误", "excepts 带参数调用失败"
    print("✓ @excepts(exc_type=ValueError, handler=...) 带参数调用成功")


def test_suppress():
    """测试 suppress 两种调用方式"""
    print("\n=== 测试 suppress ===")
    
    # 直接调用
    @suppress
    def func1():
        raise ValueError("测试错误")
    
    result = func1()
    assert result is None, "suppress 直接调用失败"
    print("✓ @suppress 直接调用成功")
    
    # 哑参数调用（无异常类型）
    @suppress()
    def func2():
        raise ValueError("测试错误")
    
    result = func2()
    assert result is None, "suppress() 带参数调用失败"
    print("✓ @suppress() 带参数调用成功")


def test_ignore():
    """测试 ignore 两种调用方式"""
    print("\n=== 测试 ignore ===")
    
    # 直接调用
    @ignore
    def func1():
        return 42
    
    result = func1()
    assert result is None, "ignore 直接调用失败"
    print("✓ @ignore 直接调用成功")
    
    # 带参数调用
    @ignore(return_value="已执行")
    def func2():
        return 42
    
    result = func2()
    assert result == "已执行", "ignore 带参数调用失败"
    print("✓ @ignore(return_value='已执行') 带参数调用成功")


def test_strict():
    """测试 strict 两种调用方式"""
    print("\n=== 测试 strict ===")
    
    # 直接调用
    @strict
    def func1(a: int, b: int) -> int:
        return a + b
    
    result = func1(1, 2)
    assert result == 3, "strict 直接调用失败"
    
    try:
        func1(1, "2")
        assert False, "应该抛出 TypeError"
    except TypeError:
        pass
    
    print("✓ @strict 直接调用成功")
    
    # 带参数调用
    @strict(enabled=False)
    def func2(a: int, b: int) -> int:
        return a + b
    
    # enabled=False 时不会检查类型，但函数本身仍然会执行
    # 注意：这里测试的是装饰器不检查类型，而不是函数能处理错误类型
    # 所以我们测试一个不会抛出错误的场景
    result = func2(1, 2)
    assert result == 3, "strict 带参数调用失败"
    print("✓ @strict(enabled=False) 带参数调用成功")


def test_curry():
    """测试 curry 两种调用方式"""
    print("\n=== 测试 curry ===")
    
    # 直接调用
    @curry
    def func1(a, b, c):
        return a + b + c
    
    result = func1(1)(2)(3)
    assert result == 6, "curry 直接调用失败"
    print("✓ @curry 直接调用成功")
    
    # 带参数调用
    @curry(is_strict=True)
    def func2(a: int, b: int) -> int:
        return a + b
    
    result = func2(1)(2)
    assert result == 3, "curry 带参数调用失败"
    print("✓ @curry(is_strict=True) 带参数调用成功")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*70)
    print("开始测试装饰器两种调用方式")
    print("="*70)
    
    try:
        test_memorize()
        test_once()
        test_persist()
        test_retry()
        test_rerun()
        test_excepts()
        test_suppress()
        test_ignore()
        test_strict()
        test_curry()
        
        print("\n" + "="*70)
        print("✓ 所有测试通过！所有装饰器都支持两种调用方式")
        print("="*70)
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)