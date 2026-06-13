"""
测试 placeholder_impl.py 中的 X 和 Y 工具
"""
import sys
import os
# 确保导入项目中的 vools 包
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
from vools.functional.placeholder_impl import X, Y


class vicList(list):
    def map(self, f):
        return self.__class__(f(i) for i in self)


def test_x_basic():
    """测试 X 的基本功能"""
    # X.strip()['  hello  '] - 需要调用，[] 终止并传入目标对象
    result = X.strip()['  hello  ']
    assert result == 'hello', f"Expected 'hello', got {result}"
    
    # X.strip().split(',')['a,b,c']
    result = X.strip().split(',')['a,b,c']
    assert result == ['a', 'b', 'c'], f"Expected ['a', 'b', 'c'], got {result}"
    
    # X.split(',')[None, 1]['a,b,c'] - 使用 [None, idx] 追加索引操作
    result = X.split(',')[None, 1]['a,b,c']
    assert result == 'b', f"Expected 'b', got {result}"
    
    print("X 基本功能测试通过")


def test_x_direct_index():
    """测试 X[idx] 直接构建索引操作"""
    # X[0]['hello'] - 直接索引
    result = X[0]['hello']
    assert result == 'h', f"Expected 'h', got {result}"
    
    # X[-1]['hello'] - 负索引
    result = X[-1]['hello']
    assert result == 'o', f"Expected 'o', got {result}"
    
    # X[1:4]['hello'] - 切片
    result = X[1:4]['hello']
    assert result == 'ell', f"Expected 'ell', got {result}"
    
    # X[0].upper()['hello'] - 索引后继续链式调用
    result = X[0].upper()['hello']
    assert result == 'H', f"Expected 'H', got {result}"
    
    # X[0].upper()['hello world', 0] - 索引后链式调用 + 额外索引
    result = X[0].upper()['hello world', 0]
    assert result == 'H', f"Expected 'H', got {result}"
    
    # X['name'][{'name': 'Alice'}] - 字典索引（使用 [] 终止执行）
    result = X['name'][{'name': 'Alice'}]
    assert result == 'Alice', f"Expected 'Alice', got {result}"
    
    # X['name'].upper()[{'name': 'alice'}] - 字典索引后调用方法
    result = X['name'].upper()[{'name': 'alice'}]
    assert result == 'ALICE', f"Expected 'ALICE', got {result}"
    
    # X[0][None, 1][[[1, 2], [3, 4]]] - 多维索引（使用 [None, idx] 追加索引）
    result = X[0][None, 1][[[1, 2], [3, 4]]]
    assert result == 2, f"Expected 2, got {result}"
    
    print("X 直接索引操作测试通过")


def test_x_index_pipeline():
    """测试 X 的索引管道功能 [None, idx...]"""
    # X.split(',')[None, 0]('a,b,c') - 追加索引操作
    result = X.split(',')[None, 0]['a,b,c']
    assert result == 'a', f"Expected 'a', got {result}"
    
    # X.split(',')[None, 1:3]('a,b,c,d') - 追加切片操作
    result = X.split(',')[None, 1:3]['a,b,c,d']
    assert result == ['b', 'c'], f"Expected ['b', 'c'], got {result}"
    
    # X.strip()[None, 0].upper()('  hello  ') - 索引后继续链式调用
    result = X.strip()[None, 0].upper()['  hello  ']
    assert result == 'H', f"Expected 'H', got {result}"
    
    # X.split(',')[None, 0].upper()('a,b,c') - 索引后调用方法
    result = X.split(',')[None, 0].upper()['a,b,c']
    assert result == 'A', f"Expected 'A', got {result}"
    
    print("X 索引管道功能测试通过")


def test_x_with_extra_index():
    """测试 X 的执行时额外索引 [target, idx...]"""
    # X.split(',')['a,b,c,d', 1] - 执行时携带额外索引
    result = X.split(',')['a,b,c,d', 1]
    assert result == 'b', f"Expected 'b', got {result}"
    
    # X.split(',')['a,b,c,d', 1:3] - 执行时携带切片
    result = X.split(',')['a,b,c,d', 1:3]
    assert result == ['b', 'c'], f"Expected ['b', 'c'], got {result}"
    
    # X.strip().split(',')['  a,b,c,d  ', 1] - 链式后携带额外索引
    result = X.strip().split(',')['  a,b,c,d  ', 1]
    assert result == 'b', f"Expected 'b', got {result}"
    
    print("X 执行时额外索引测试通过")


def test_x_with_f():
    """测试 X 的 f() 工厂方法"""
    # X.split(',').f(vicList)['a,b,c']
    result = X.split(',').f(vicList)['a,b,c']
    assert isinstance(result, vicList), f"Expected vicList, got {type(result)}"
    assert result == vicList(['a', 'b', 'c']), f"Expected vicList(['a', 'b', 'c']), got {result}"
    
    # X.strip().split(',').f(vicList)['  a,b,c  ']
    result = X.strip().split(',').f(vicList)['  a,b,c  ']
    assert isinstance(result, vicList), f"Expected vicList, got {type(result)}"
    assert result == vicList(['a', 'b', 'c']), f"Expected vicList(['a', 'b', 'c']), got {result}"
    
    # X.split(',')[None, 0].upper().f(str.lower)['a,b,c'] - 链式后使用 f
    result = X.split(',')[None, 0].upper().f(str.lower)['a,b,c']
    assert result == 'a', f"Expected 'a', got {result}"
    
    print("X f() 工厂方法测试通过")


def test_x_as_function():
    """测试 X 的 as_function() 方法"""
    # X.strip().as_function() - 返回可调用函数
    f = X.strip().as_function()
    assert callable(f), f"Expected callable, got {type(f)}"
    
    # 使用返回的函数
    result = f('  hello  ')
    assert result == 'hello', f"Expected 'hello', got {result}"
    
    # X.strip().split(',').as_function() - 链式后返回函数
    f = X.strip().split(',').as_function()
    result = f('  a,b,c  ')
    assert result == ['a', 'b', 'c'], f"Expected ['a', 'b', 'c'], got {result}"
    
    # 使用 f 参数
    f = X.split(',').as_function()
    result = f('a,b,c', f=vicList)
    assert isinstance(result, vicList), f"Expected vicList, got {type(result)}"
    assert result == vicList(['a', 'b', 'c']), f"Expected vicList(['a', 'b', 'c']), got {result}"
    
    # X['name'].as_function() - 索引后返回函数
    f = X['name'].as_function()
    result = f({'name': 'Alice'})
    assert result == 'Alice', f"Expected 'Alice', got {result}"
    
    # X['name'].upper().as_function() - 索引后链式调用
    f = X['name'].upper().as_function()
    result = f({'name': 'alice'})
    assert result == 'ALICE', f"Expected 'ALICE', got {result}"
    
    # X[0][None, 1].as_function() - 多维索引（使用 [None, idx] 追加索引）
    f = X[0][None, 1].as_function()
    result = f([[1, 2], [3, 4]])
    assert result == 2, f"Expected 2, got {result}"
    
    # X.split(',').f(vicList).as_function() - f() 后使用 as_function()
    f = X.split(',').f(vicList).as_function()
    result = f('a,b,c')
    assert isinstance(result, vicList), f"Expected vicList, got {type(result)}"
    assert result == vicList(['a', 'b', 'c']), f"Expected vicList(['a', 'b', 'c']), got {result}"
    
    print("X as_function() 方法测试通过")


def test_y_basic():
    """测试 Y 的基本功能"""
    # Y.strip()('  hello  ', exe=True) - 需要调用，exe=True 触发执行
    result = Y.strip()('  hello  ', exe=True)
    assert result == 'hello', f"Expected 'hello', got {result}"
    
    # Y.strip().split(',')('a,b,c', exe=True) - 链式调用
    result = Y.strip().split(',')('a,b,c', exe=True)
    assert result == ['a', 'b', 'c'], f"Expected ['a', 'b', 'c'], got {result}"
    
    # Y.split(',')[1]('a,b,c', exe=True) - 索引操作
    result = Y.split(',')[1]('a,b,c', exe=True)
    assert result == 'b', f"Expected 'b', got {result}"
    
    print("Y 基本功能测试通过")


def test_y_as_function():
    """测试 Y 的 as_function() 新方法"""
    # Y.strip().as_function() - 返回可调用函数
    f = Y.strip().as_function()
    assert callable(f), f"Expected callable, got {type(f)}"
    
    # 使用返回的函数
    result = f('  hello  ')
    assert result == 'hello', f"Expected 'hello', got {result}"
    
    # Y.strip().split(',').as_function() - 链式后返回函数
    f = Y.strip().split(',').as_function()
    result = f('  a,b,c  ')
    assert result == ['a', 'b', 'c'], f"Expected ['a', 'b', 'c'], got {result}"
    
    # 使用 f 参数
    f = Y.split(',').as_function()
    result = f('a,b,c', f=vicList)
    assert isinstance(result, vicList), f"Expected vicList, got {type(result)}"
    assert result == vicList(['a', 'b', 'c']), f"Expected vicList(['a', 'b', 'c']), got {result}"
    
    # Y['name'].as_function() - 索引后返回函数
    f = Y['name'].as_function()
    result = f({'name': 'Alice'})
    assert result == 'Alice', f"Expected 'Alice', got {result}"
    
    # Y['name'].upper().as_function() - 索引后链式调用
    f = Y['name'].upper().as_function()
    result = f({'name': 'alice'})
    assert result == 'ALICE', f"Expected 'ALICE', got {result}"
    
    # Y[0][1].as_function() - 多维索引
    f = Y[0][1].as_function()
    result = f([[1, 2], [3, 4]])
    assert result == 2, f"Expected 2, got {result}"
    
    # Y.strip().f(vicList).as_function() - f() 后使用 as_function()
    f = Y.strip().f(vicList).as_function()
    result = f('  hello  ')
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert result == ['h', 'e', 'l', 'l', 'o'], f"Expected ['h', 'e', 'l', 'l', 'o'], got {result}"
    
    print("Y as_function() 方法测试通过")


def test_y_f_method():
    """测试 Y 的 f() 工厂方法"""
    # Y.split(',').f(vicList)('a,b,c', exe=True)
    result = Y.split(',').f(vicList)('a,b,c', exe=True)
    assert isinstance(result, vicList), f"Expected vicList, got {type(result)}"
    assert result == vicList(['a', 'b', 'c']), f"Expected vicList(['a', 'b', 'c']), got {result}"
    
    # Y.strip().split(',').f(vicList)('  a,b,c  ', exe=True)
    result = Y.strip().split(',').f(vicList)('  a,b,c  ', exe=True)
    assert isinstance(result, vicList), f"Expected vicList, got {type(result)}"
    assert result == vicList(['a', 'b', 'c']), f"Expected vicList(['a', 'b', 'c']), got {result}"
    
    # Y.split(',')[0].upper().f(str.lower)('a,b,c', exe=True)
    result = Y.split(',')[0].upper().f(str.lower)('a,b,c', exe=True)
    assert result == 'a', f"Expected 'a', got {result}"
    
    print("Y f() 方法测试通过")


def test_y_as_subscript():
    """测试 Y 的 as_subscript() 方法"""
    # Y.strip().as_subscript()['  hello  '] - 返回下标执行器
    sub = Y.strip().as_subscript()
    result = sub['  hello  ']
    assert result == 'hello', f"Expected 'hello', got {result}"
    
    # Y.strip().split(',').as_subscript()['  a,b,c  '] - 链式后返回下标执行器
    sub = Y.strip().split(',').as_subscript()
    result = sub['  a,b,c  ']
    assert result == ['a', 'b', 'c'], f"Expected ['a', 'b', 'c'], got {result}"
    
    # Y.split(',').as_subscript()['a,b,c', 1] - 带额外索引
    sub = Y.split(',').as_subscript()
    result = sub['a,b,c', 1]
    assert result == 'b', f"Expected 'b', got {result}"
    
    # Y.split(',').as_subscript()['a,b,c,d', 1:3] - 带切片索引
    sub = Y.split(',').as_subscript()
    result = sub['a,b,c,d', 1:3]
    assert result == ['b', 'c'], f"Expected ['b', 'c'], got {result}"
    
    # Y['name'].as_subscript()[{'name': 'Alice'}] - 索引后返回下标执行器
    sub = Y['name'].as_subscript()
    result = sub[{'name': 'Alice'}]
    assert result == 'Alice', f"Expected 'Alice', got {result}"
    
    # Y['name'].upper().as_subscript()[{'name': 'alice'}] - 索引后链式调用
    sub = Y['name'].upper().as_subscript()
    result = sub[{'name': 'alice'}]
    assert result == 'ALICE', f"Expected 'ALICE', got {result}"
    
    # Y[0][1].as_subscript()[[[1, 2], [3, 4]]] - 多维索引
    sub = Y[0][1].as_subscript()
    result = sub[[[1, 2], [3, 4]]]
    assert result == 2, f"Expected 2, got {result}"
    
    # Y.split(',').f(vicList).as_subscript()['a,b,c'] - f() 后使用 as_subscript()
    sub = Y.split(',').f(vicList).as_subscript()
    result = sub['a,b,c']
    assert isinstance(result, vicList), f"Expected vicList, got {type(result)}"
    assert result == vicList(['a', 'b', 'c']), f"Expected vicList(['a', 'b', 'c']), got {result}"
    
    print("Y as_subscript() 方法测试通过")


def test_y_with_f():
    """测试 Y 的 f 工厂参数"""
    # Y.split(',')('a,b,c', exe=True, f=vicList)
    result = Y.split(',')('a,b,c', exe=True, f=vicList)
    assert isinstance(result, vicList), f"Expected vicList, got {type(result)}"
    assert result == vicList(['a', 'b', 'c']), f"Expected vicList(['a', 'b', 'c']), got {result}"
    
    # Y.strip().split(',')('  a,b,c  ', exe=True, f=vicList)
    result = Y.strip().split(',')('  a,b,c  ', exe=True, f=vicList)
    assert isinstance(result, vicList), f"Expected vicList, got {type(result)}"
    assert result == vicList(['a', 'b', 'c']), f"Expected vicList(['a', 'b', 'c']), got {result}"
    
    print("Y f 工厂参数测试通过")


def test_y_index():
    """测试 Y 的索引操作"""
    # Y['name']({'name': 'Alice'}, exe=True)
    result = Y['name']({'name': 'Alice'}, exe=True)
    assert result == 'Alice', f"Expected 'Alice', got {result}"
    
    # Y[0][1]([[1, 2], [3, 4]], exe=True)
    result = Y[0][1]([[1, 2], [3, 4]], exe=True)
    assert result == 2, f"Expected 2, got {result}"
    
    print("Y 索引操作测试通过")


def test_error_handling():
    """测试错误处理"""
    # X 传入错误类型
    try:
        X.strip()[1]
        assert False, "Expected AttributeError"
    except AttributeError:
        pass
    
    # Y 传入错误类型
    try:
        Y.strip()(1, exe=True)
        assert False, "Expected AttributeError"
    except AttributeError:
        pass
    
    # X f() 传入非可调用对象
    try:
        X.split(',').f(None)['a,b,c']
        assert False, "Expected TypeError"
    except TypeError:
        pass
    
    # Y f 参数传入非可调用对象（None 除外）
    try:
        Y.split(',')('a,b,c', exe=True, f=123)
        assert False, "Expected TypeError"
    except TypeError:
        pass
    
    # Y 执行时缺少参数
    try:
        Y.strip()(exe=True)
        assert False, "Expected TypeError"
    except TypeError:
        pass
    
    # X 单独传入 None
    try:
        X.strip()[None]
        assert False, "Expected ValueError"
    except ValueError:
        pass
    
    # X 空 tuple
    try:
        X.strip[()]
        assert False, "Expected ValueError"
    except ValueError:
        pass
    
    # Y as_function() f 参数传入非可调用对象
    f = Y.split(',').as_function()
    try:
        f('a,b,c', f=123)
        assert False, "Expected TypeError"
    except TypeError:
        pass
    
    print("错误处理测试通过")


def test_chained_combinations():
    """测试各种链式组合"""
    # X: attr -> call -> attr -> call
    result = X.strip().upper()['  hello  ']
    assert result == 'HELLO', f"Expected 'HELLO', got {result}"
    
    # X: call -> index（使用 [None, idx] 管道内索引）
    result = X.split(',')[None, 0]['a,b,c']
    assert result == 'a', f"Expected 'a', got {result}"
    
    # X: call -> index -> attr -> call（管道内索引后继续链式）
    result = X.split(',')[None, 0].upper()['a,b,c']
    assert result == 'A', f"Expected 'A', got {result}"
    
    # X: index -> attr -> call（直接索引后链式）
    result = X[0].upper()['hello']
    assert result == 'H', f"Expected 'H', got {result}"
    
    # X: index -> index（多维索引，使用 [None, idx] 追加索引）
    result = X[0][None, 1][[[1, 2], [3, 4]]]
    assert result == 2, f"Expected 2, got {result}"
    
    # Y: attr -> call -> attr -> call
    result = Y.strip().upper()('  hello  ', exe=True)
    assert result == 'HELLO', f"Expected 'HELLO', got {result}"
    
    # Y: call -> index -> call
    result = Y.split(',')[0]('a,b,c', exe=True)
    assert result == 'a', f"Expected 'a', got {result}"
    
    # Y: 使用 as_function() 的链式组合
    f = Y.strip().upper().as_function()
    result = f('  hello  ')
    assert result == 'HELLO', f"Expected 'HELLO', got {result}"
    
    print("链式组合测试通过")


if __name__ == '__main__':
    test_x_basic()
    test_x_direct_index()
    test_x_index_pipeline()
    test_x_with_extra_index()
    test_x_with_f()
    test_x_as_function()
    test_y_basic()
    test_y_as_function()
    test_y_f_method()
    test_y_as_subscript()
    test_y_with_f()
    test_y_index()
    test_error_handling()
    test_chained_combinations()
    print("\n=== 所有测试通过 ===")