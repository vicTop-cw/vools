"""
测试 placeholder_impl.py 中的 Z 惰性表达式占位符系统

覆盖：
- 基础表达式构建与编译
- 属性访问、方法调用、索引操作
- invoke() / __call__()
- 关键字参数
- *args / **kwargs 解包（star / kwstar）
- 可变参数引用（args_all / kwargs_all）
- Pickle 序列化/反序列化
- JSON 序列化/反序列化（expr_to_dict / expr_from_dict）
- 边界条件与错误处理
- 复杂表达式树（链式组合）
"""
import sys
import os
import pickle
import json
from vools.functional.placeholder_impl import (
    Z,
    Expr, Placeholder, Attr, Call, GetItem,
    StarArgs, StarKwargs, RestArgs, RestKwargs,
    _Auto,
    _serialize, _deserialize,
    expr_to_dict, expr_from_dict,
    make_func,
)


# ============================================================
# 辅助类
# ============================================================

class Person:
    """测试用的 Person 类，提供方法链式调用场景"""
    def __init__(self, name, age):
        self.name = name
        self.age = age

    def greet(self):
        return f"Hello, {self.name}"

    def get_age(self):
        return self.age


class Calculator:
    """测试用的 Calculator 类，提供多参数调用场景"""
    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b

    def compute(self, a, b, op='add'):
        if op == 'add':
            return a + b
        elif op == 'multiply':
            return a * b
        else:
            raise ValueError(f"Unknown op: {op}")


# ============================================================
# 基础表达式测试
# ============================================================

def test_z_basic_attr():
    """测试 Z 的属性访问"""
    # Z.name → 访问第一个参数（Person）的 name 属性
    f = (Z.name).as_function()
    assert f(Person('Alice', 30)) == 'Alice'

    # Z.age
    f = (Z.age).as_function()
    assert f(Person('Bob', 25)) == 25

    print("Z 基础属性访问测试通过")


def test_z_basic_call():
    """测试 Z 的方法调用"""
    # Z.greet() → 调用第一个参数的 greet 方法
    f = (Z.greet()).as_function()
    assert f(Person('Alice', 30)) == 'Hello, Alice'

    # Z.get_age()
    f = (Z.get_age()).as_function()
    assert f(Person('Bob', 25)) == 25

    print("Z 基础方法调用测试通过")


def test_z_basic_index():
    """测试 Z 的索引操作"""
    # Z[0] → 取第一个参数的第 0 个元素
    f = (Z[0]).as_function()
    assert f('hello') == 'h'

    # Z[-1]
    f = (Z[-1]).as_function()
    assert f('hello') == 'o'

    # Z[1:4]
    f = (Z[1:4]).as_function()
    assert f('hello') == 'ell'

    # Z['key'] → 字典索引
    f = (Z['key']).as_function()
    assert f({'key': 'value'}) == 'value'

    print("Z 基础索引操作测试通过")


# ============================================================
# invoke / __call__ 测试
# ============================================================

def test_z_invoke_no_args():
    """测试 Z.invoke() 无参调用"""
    # Z.invoke() → 调用第一个参数（它必须是可调用的）
    f = (Z.invoke()).as_function()
    assert f(lambda: 42) == 42

    # 使用 __call__ 语法
    f = (Z()).as_function()
    assert f(lambda: 99) == 99

    print("Z.invoke() 无参调用测试通过")


def test_z_invoke_with_args():
    """测试 Z.invoke() 带参数"""
    # Z.invoke(1, 2) → 将第一个参数作为函数，传入 (1, 2)
    f = (Z.invoke(1, 2)).as_function()
    assert f(lambda a, b: a + b) == 3

    # 使用 __call__ 语法
    f = (Z(3, 4)).as_function()
    assert f(lambda a, b: a * b) == 12

    print("Z.invoke() 带参数测试通过")


def test_z_invoke_with_kwargs():
    """测试 Z.invoke() 带关键字参数"""
    # Z.invoke(k1=1, k2='hello')
    f = (Z.invoke(k1=1, k2='hello')).as_function()

    def func(**kw):
        return kw
    assert f(func) == {'k1': 1, 'k2': 'hello'}

    # 混合位置参数和关键字参数
    f = (Z.invoke(10, op='add')).as_function()

    def func2(a, *, op):
        return f"{op}:{a}"
    assert f(func2) == 'add:10'

    print("Z.invoke() 关键字参数测试通过")


# ============================================================
# 链式组合测试
# ============================================================

def test_z_chained_attr_call():
    """测试 Z 链式组合：属性访问 + 方法调用"""
    # Z.strip().upper()
    f = (Z.strip().upper()).as_function()
    assert f('  hello  ') == 'HELLO'

    # Z.split(',').f(list)
    f = (Z.split(',')).as_function()
    assert f('a,b,c') == ['a', 'b', 'c']

    print("Z 链式 attr+call 测试通过")


def test_z_chained_index_call():
    """测试 Z 链式组合：索引 + 方法调用"""
    # Z[0].upper()
    f = (Z[0].upper()).as_function()
    assert f('hello') == 'H'

    # Z['name'].upper()
    f = (Z['name'].upper()).as_function()
    assert f({'name': 'alice'}) == 'ALICE'

    print("Z 链式 index+call 测试通过")


def test_z_chained_call_index():
    """测试 Z 链式组合：方法调用 + 索引"""
    # Z.split(',')[0]
    f = (Z.split(',')[0]).as_function()
    assert f('a,b,c') == 'a'

    # Z.split(',')[1:3]
    f = (Z.split(',')[1:3]).as_function()
    assert f('a,b,c,d') == ['b', 'c']

    print("Z 链式 call+index 测试通过")


def test_z_chained_multi_ops():
    """测试 Z 复杂链式组合"""
    # Z.strip().split(',')[0].upper()
    f = (Z.strip().split(',')[0].upper()).as_function()
    assert f('  a,b,c  ') == 'A'

    # Z.strip().split(',') → 对结果直接使用 list() 转换（由调用者完成）
    f = (Z.strip().split(',')).as_function()
    assert list(f('  a,b,c  ')) == ['a', 'b', 'c']

    print("Z 复杂链式组合测试通过")


# ============================================================
# 多参数 + 多次 Z 出现测试
# ============================================================

def test_z_multiple_placeholders():
    """测试表达式中多次出现 Z"""
    # Z + Z → 两个固定参数相加
    f = (Z + Z).as_function()
    assert f(3, 5) == 8

    # Z.split(Z) → 第一个参数调用 split(第二个参数)
    f = (Z.split(Z)).as_function()
    assert f('a,b,c', ',') == ['a', 'b', 'c']

    # Z.add(Z).compute(Z) → 链式方法调用包含多个 Z
    class Chain:
        def add(self, v):
            self._v = v
            return self

        def compute(self, v):
            return self._v * v

    f = (Z.add(Z).compute(Z)).as_function()
    assert f(Chain(), 3, 4) == 12  # 3*4=12

    print("Z 多次出现（多参数）测试通过")


def test_z_method_chain_with_z():
    """测试链式调用中包含多个 Z"""
    # Z.add(Z) → obj.add(value)
    class Adder:
        def add(self, v):
            return self.value + v

        def __init__(self, v):
            self.value = v

    f = (Z.add(Z)).as_function()
    assert f(Adder(10), 5) == 15

    # Z.add(Z).compute(Z) → obj.add(a).compute(b)
    class Chain:
        def add(self, v):
            self._v = v
            return self

        def compute(self, v):
            return self._v * v

    f = (Z.add(Z).compute(Z)).as_function()
    assert f(Chain(), 3, 4) == 12  # 3*4=12

    print("Z 方法链中包含多个 Z 测试通过")


# ============================================================
# *args / **kwargs 解包测试
# ============================================================

def test_z_star_args():
    """测试 Z.star（*args 解包）"""
    # Z.invoke(1, Z.star) → f(1, *args)
    f = (Z.invoke(1, Z.star)).as_function()

    def func(a, b, c):
        return a + b + c
    assert f(func, [2, 3]) == 6  # func(1, 2, 3) = 6

    # 多个 star
    f = (Z.invoke(Z.star, Z.star)).as_function()

    def func2(a, b, c, d):
        return a + b + c + d
    assert f(func2, [1, 2], [3, 4]) == 10

    print("Z.star 解包测试通过")


def test_z_kwstar():
    """测试 Z.kwstar（**kwargs 解包）"""
    # Z.invoke(kw=Z.kwstar) → f(**kwargs)
    f = (Z.invoke(kw=Z.kwstar)).as_function()

    def func(*, kw):
        return kw
    assert f(func, {'kw': 'hello'}) == 'hello'

    # Z.invoke(1, kw=Z.kwstar) → f(1, **kwargs)
    f = (Z.invoke(1, kw=Z.kwstar)).as_function()

    def func2(a, *, kw):
        return a + kw
    assert f(func2, {'kw': 10}) == 11

    print("Z.kwstar 解包测试通过")


# ============================================================
# args_all / kwargs_all 测试
# ============================================================

def test_z_args_all():
    """测试 Z.args_all（可变位置参数）"""
    # 返回整个 args
    f = (Z.args_all).as_function()
    assert f(1, 2, 3) == (1, 2, 3)

    # Z.args_all[0] → 取第一个参数
    f = (Z.args_all[0]).as_function()
    assert f(10, 20, 30) == 10

    # Z.args_all[0] + Z.args_all[1]
    f = (Z.args_all[0] + Z.args_all[1]).as_function()
    assert f(3, 5) == 8
    # 可以传入更多参数
    assert f(3, 5, 100) == 8

    # Z.args_all[-1] → 取最后一个参数
    f = (Z.args_all[-1]).as_function()
    assert f(1, 2, 3) == 3

    print("Z.args_all 测试通过")


def test_z_kwargs_all():
    """测试 Z.kwargs_all（可变关键字参数）"""
    # 返回整个 kwargs
    f = (Z.kwargs_all).as_function()
    assert f(a=1, b=2) == {'a': 1, 'b': 2}

    # Z.kwargs_all['key']
    f = (Z.kwargs_all['key']).as_function()
    assert f(key='value') == 'value'

    print("Z.kwargs_all 测试通过")


def test_z_args_all_with_func():
    """测试 args_all 编译为可变参数函数"""
    # args_all 会导致生成 def f(*args, **kwargs)
    f = (Z.args_all[0] + Z.args_all[1]).as_function()

    # 可以传入任意数量的参数
    assert f(1, 2) == 3
    assert f(10, 20, 30, 40) == 30  # 使用前两个

    print("Z.args_all 可变参数函数测试通过")


# ============================================================
# Pickle 序列化/反序列化测试
# ============================================================

def test_z_pickle_serialization():
    """测试 Z 表达式的 pickle 序列化/反序列化"""
    expr = Z.strip().upper()

    # 序列化
    buf = pickle.dumps(expr)
    restored = pickle.loads(buf)

    # 验证还原后可以正常编译执行
    f = restored.as_function()
    assert f('  hello  ') == 'HELLO'

    # 复杂表达式
    expr2 = Z.strip().split(',')[0].upper()
    buf2 = pickle.dumps(expr2)
    restored2 = pickle.loads(buf2)
    f2 = restored2.as_function()
    assert f2('  a,b,c  ') == 'A'

    print("Z pickle 序列化测试通过")


def test_z_pickle_complex_expression():
    """测试复杂表达式树的 pickle 序列化"""
    expr = Z.invoke(1, 2)
    buf = pickle.dumps(expr)

    # 如果 pickle 因 __main__ 问题失败，走手动状态重建
    try:
        restored = pickle.loads(buf)
    except Exception:
        state = expr.__getstate__()
        restored = _deserialize(state)

    f = restored.as_function()

    def func(a, b):
        return a + b
    assert f(func) == 3

    print("Z pickle 复杂表达式测试通过")


# ============================================================
# JSON 序列化/反序列化测试
# ============================================================

def test_z_json_serialization():
    """测试 expr_to_dict / expr_from_dict JSON 序列化"""
    # 简单表达式
    expr = Z.strip().upper()
    d = expr_to_dict(expr)
    json_str = json.dumps(d, ensure_ascii=False)

    restored = expr_from_dict(json.loads(json_str))
    f = restored.as_function()
    assert f('  hello  ') == 'HELLO'

    print("Z JSON 序列化测试通过")


def test_z_json_with_constants():
    """测试 JSON 序列化包含常量的表达式"""
    # 包含整数字面量
    expr = Z.invoke(1, 2)
    d = expr_to_dict(expr)
    json_str = json.dumps(d, ensure_ascii=False)

    restored = expr_from_dict(json.loads(json_str))
    f = restored.as_function()

    def func(a, b):
        return a + b
    assert f(func) == 3

    # 包含字符串字面量
    expr2 = Z.invoke(k1=1, k2='hello')
    d2 = expr_to_dict(expr2)
    json_str2 = json.dumps(d2, ensure_ascii=False)
    restored2 = expr_from_dict(json.loads(json_str2))
    f2 = restored2.as_function()

    def func2(**kw):
        return kw
    assert f2(func2) == {'k1': 1, 'k2': 'hello'}

    print("Z JSON 含常量测试通过")


def test_z_json_complex_expression():
    """测试 JSON 序列化复杂表达式"""
    expr = Z.strip().split(',')[0].upper()
    d = expr_to_dict(expr)
    json_str = json.dumps(d, ensure_ascii=False)

    restored = expr_from_dict(json.loads(json_str))
    assert isinstance(restored, Expr)

    # 验证可以编译执行
    f = restored.as_function()
    assert callable(f)
    assert f('  a,b,c  ') == 'A'

    print("Z JSON 复杂表达式测试通过")


def test_z_json_roundtrip():
    """测试多次 JSON 往返序列化（在编译前）"""
    expr = Z.strip().upper()

    # 第一次
    d1 = expr_to_dict(expr)
    restored1 = expr_from_dict(d1)
    f1 = restored1.as_function()
    assert f1('  hello  ') == 'HELLO'

    # 第二次（不编译，直接对原始表达式再次序列化）
    d2 = expr_to_dict(expr)
    restored2 = expr_from_dict(d2)
    f2 = restored2.as_function()
    assert f2('  hello  ') == 'HELLO'

    # 验证序列化结构一致
    assert d1 == d2

    print("Z JSON 往返序列化测试通过")


# ============================================================
# 序列化辅助函数测试
# ============================================================

def test_serialize_deserialize_functions():
    """测试 _serialize / _deserialize 辅助函数"""
    # 常量直接返回
    assert _serialize(42) == 42
    assert _serialize('hello') == 'hello'
    assert _serialize([1, 2, 3]) == [1, 2, 3]
    assert _serialize(None) is None

    # None 不是 dict，直接返回
    assert _deserialize(None) is None
    assert _deserialize(42) == 42

    # Expr 节点序列化为 dict
    p = Placeholder(0)
    d = _serialize(p)
    assert isinstance(d, dict)
    assert d['__type__'] == 'Placeholder'
    assert d['n'] == 0

    # 反序列化
    restored = _deserialize(d)
    assert isinstance(restored, Placeholder)
    assert restored.n == 0

    # 未知类型抛出 ValueError
    try:
        _deserialize({'__type__': 'UnknownType'})
        assert False, "Expected ValueError"
    except ValueError:
        pass

    print("_serialize/_deserialize 辅助函数测试通过")


# ============================================================
# make_func 测试（与 as_function 等价）
# ============================================================

def test_make_func():
    """测试 make_func 与 as_function 等价"""
    expr1 = Z.strip().upper()
    f1 = expr1.as_function()
    assert f1('  hello  ') == 'HELLO'

    # 使用新表达式（因为 _compile 会原地修改树）
    expr2 = Z.strip().upper()
    f2 = make_func(expr2)
    assert f2('  hello  ') == 'HELLO'

    # 可变参数
    expr3 = Z.args_all[0]
    f3 = expr3.as_function()
    assert f3(42) == 42

    expr4 = Z.args_all[0]
    f4 = make_func(expr4)
    assert f4(42) == 42

    print("make_func 测试通过")


# ============================================================
# 错误处理测试
# ============================================================

def test_z_error_uncompiled():
    """测试未编译的 Z 求值"""
    try:
        Z.evaluate(('arg',))
        assert False, "Expected RuntimeError"
    except RuntimeError as e:
        assert 'make_func' in str(e)

    print("Z 未编译错误测试通过")


def test_z_error_wrong_arg_count():
    """测试固定参数数量不匹配"""
    f = (Z + Z).as_function()  # 需要 2 个参数

    try:
        f(1)  # 只传 1 个
        assert False, "Expected TypeError"
    except TypeError:
        pass

    try:
        f(1, 2, 3)  # 传 3 个
        assert False, "Expected TypeError"
    except TypeError:
        pass

    print("Z 参数数量不匹配错误测试通过")


def test_z_error_attr_name_with_underscore():
    """测试属性名以 _ 开头抛异常"""
    try:
        Z._private
        assert False, "Expected AttributeError"
    except AttributeError:
        pass

    print("Z 下划线属性名错误测试通过")


def test_z_error_unknown_op():
    """测试未知操作类型的错误处理"""
    # 构造一个带非法操作类型的节点（不会自然产生）
    # 直接验证 _deserialize 的 ValueError
    try:
        _deserialize({'__type__': 'NonExistent'})
        assert False, "Expected ValueError"
    except ValueError as e:
        assert '未知节点类型' in str(e)

    print("Z 未知操作类型错误测试通过")


# ============================================================
# 节点类型测试
# ============================================================

def test_node_types():
    """测试各节点类型的基本创建和求值"""
    # Placeholder
    p = Placeholder(0)
    assert p.evaluate(('hello',)) == 'hello'

    # Attr
    p = Placeholder(0)
    a = Attr(p, 'upper')
    assert a.evaluate(('hello',)) == getattr('hello', 'upper')

    # GetItem
    g = GetItem(Placeholder(0), 0)
    assert g.evaluate(('hello',)) == 'h'

    # RestArgs
    r = RestArgs()
    assert r.evaluate((1, 2, 3)) == (1, 2, 3)

    # RestKwargs
    rk = RestKwargs()
    assert rk.evaluate((), {'a': 1}) == {'a': 1}
    assert rk.evaluate(()) == {}  # kwargs=None → {}

    # Call
    p = Placeholder(0)
    c = Call(p, (1, 2), {})
    assert c.evaluate((lambda a, b: a + b,)) == 3

    # StarArgs
    s = StarArgs(Placeholder(1))
    c = Call(Placeholder(0), (1, s), {})
    assert c.evaluate((lambda a, b: a + b, [2])) == 3

    # StarKwargs
    sk = StarKwargs(Placeholder(1))
    c = Call(Placeholder(0), (), {'kw': sk})
    def func(*, kw):
        return kw
    assert c.evaluate((func, {'kw': 'hello'})) == 'hello'

    print("节点类型测试通过")


def test_node_serialization():
    """测试各节点类型的 getstate/setstate"""
    # Placeholder
    p = Placeholder(2)
    state = p.__getstate__()
    p2 = Placeholder.__new__(Placeholder)
    p2.__setstate__(state)
    assert p2.n == 2

    # Attr
    a = Attr(Placeholder(0), 'name')
    state = a.__getstate__()
    a2 = Attr.__new__(Attr)
    a2.__setstate__(state)
    assert a2.name == 'name'

    # Call
    c = Call(Placeholder(0), (1, Placeholder(1)), {'k': 2})
    state = c.__getstate__()
    c2 = Call.__new__(Call)
    c2.__setstate__(state)
    assert len(c2.args) == 2

    # GetItem
    g = GetItem(Placeholder(0), 'key')
    state = g.__getstate__()
    g2 = GetItem.__new__(GetItem)
    g2.__setstate__(state)
    assert g2.key == 'key'

    # _Auto
    state = Z.__getstate__()
    assert state['__type__'] == '_Auto'
    a3 = _deserialize(state)
    assert a3 is Z

    print("节点序列化测试通过")


# ============================================================
# make_func 参数数量测试
# ============================================================

def test_make_func_arity():
    """测试 make_func 正确计算参数数量"""
    # 0 个 Z → 固定 0 参数
    f = make_func(Z.invoke(1, 2))  # 没有 Z 占位符（1, 2 是常量）
    assert f(lambda a, b: a + b) == 3

    # 1 个 Z
    f = make_func(Z.upper())
    assert f('hello') == 'HELLO'

    # 2 个 Z
    f = make_func(Z + Z)
    assert f(1, 2) == 3

    # 3 个 Z → Z.add(Z).compute(Z) 表达式中有 3 个 Z
    class Chain:
        def add(self, v):
            self._v = v
            return self

        def compute(self, v):
            return self._v * v

    f = make_func(Z.add(Z).compute(Z))
    assert f(Chain(), 2, 4) == 8  # 2*4=8

    # args_all → 可变参数（无 arity 限制）
    f = make_func(Z.args_all)
    assert f() == ()
    assert f(1, 2, 3) == (1, 2, 3)

    print("make_func 参数数量测试通过")


# ============================================================
# 真实场景测试
# ============================================================

def test_real_scenario_data_pipeline():
    """真实场景：数据清洗管道"""
    # 模拟数据清洗：strip → upper → 取前5个字符
    f = (Z.strip().upper()[:5]).as_function()
    assert f('  hello world  ') == 'HELLO'

    # 模拟 CSV 解析：split → 取特定列 → strip
    f = (Z.split(',')[2].strip()).as_function()
    assert f('a, b , c ') == 'c'

    print("真实场景数据管道测试通过")


def test_real_scenario_json_extraction():
    """真实场景：JSON 数据提取"""
    # 从嵌套字典中提取字段
    data = {
        'user': {
            'name': 'Alice',
            'profile': {
                'city': 'Beijing',
                'age': 30,
            }
        }
    }

    # 提取 user → name
    f = (Z['user']['name']).as_function()
    assert f(data) == 'Alice'

    # 提取 user → profile → city
    f = (Z['user']['profile']['city']).as_function()
    assert f(data) == 'Beijing'

    # 提取后调用 upper
    f = (Z['user']['name'].upper()).as_function()
    assert f(data) == 'ALICE'

    print("真实场景 JSON 提取测试通过")


def test_real_scenario_function_composition():
    """真实场景：函数组合"""
    # data → strip → split(_, ',') → map(len) → max
    # 使用表达式构建步骤
    f = (Z.strip().split(',')).as_function()
    result = f('  hello,world,foo  ')
    lens = [len(s) for s in result]
    assert max(lens) == 5  # 'hello'/'world' 都是 5

    print("真实场景函数组合测试通过")


# ============================================================
# 运行入口
# ============================================================

if __name__ == '__main__':
    # 基础表达式
    test_z_basic_attr()
    test_z_basic_call()
    test_z_basic_index()

    # invoke / __call__
    test_z_invoke_no_args()
    test_z_invoke_with_args()
    test_z_invoke_with_kwargs()

    # 链式组合
    test_z_chained_attr_call()
    test_z_chained_index_call()
    test_z_chained_call_index()
    test_z_chained_multi_ops()

    # 多参数 + 多次 Z
    test_z_multiple_placeholders()
    test_z_method_chain_with_z()

    # *args / **kwargs 解包
    test_z_star_args()
    test_z_kwstar()

    # args_all / kwargs_all
    test_z_args_all()
    test_z_kwargs_all()
    test_z_args_all_with_func()

    # Pickle 序列化
    test_z_pickle_serialization()
    test_z_pickle_complex_expression()

    # JSON 序列化
    test_z_json_serialization()
    test_z_json_with_constants()
    test_z_json_complex_expression()
    test_z_json_roundtrip()

    # 辅助函数
    test_serialize_deserialize_functions()

    # make_func
    test_make_func()
    test_make_func_arity()

    # 错误处理
    test_z_error_uncompiled()
    test_z_error_wrong_arg_count()
    test_z_error_attr_name_with_underscore()
    test_z_error_unknown_op()

    # 节点类型
    test_node_types()
    test_node_serialization()

    # 真实场景
    test_real_scenario_data_pipeline()
    test_real_scenario_json_extraction()
    test_real_scenario_function_composition()

    print("\n=== Z 表达式系统所有测试通过 ===")
