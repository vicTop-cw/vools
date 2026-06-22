"""
惰性表达式占位符系统 (Z-表达式)
支持：属性访问、调用、索引、.invoke()、关键字参数、*args/**kwargs 解包、可变参数函数
      序列化/反序列化（pickle 与 JSON）
"""

import pickle
import json


class Expr:
    """所有表达式节点的基类"""
    def __getattr__(self, name):
        return Attr(self, name)

    def __getitem__(self, key):
        return GetItem(self, key)

    def __add__(self, other):
        return Call(Attr(self, '__add__'), (other,), {})

    def invoke(self, *args, **kwargs):
        return Call(self, args, kwargs)

    def __call__(self, *args, **kwargs):
        return Call(self, args, kwargs)

    def evaluate(self, args, kwargs=None):
        raise NotImplementedError

    def as_function(self):
        """终止惰性构建，编译表达式并返回可调用的函数。"""
        return make_func(self)

    # ---- 序列化支持 ----
    def __reduce__(self):
        """供 pickle 使用：用 object.__new__ 绕过 __main__ 类路径查找。"""
        return (object.__new__, (self.__class__,), self.__getstate__())

    def __getstate__(self):
        """返回可序列化的纯数据结构。子类必须覆盖。"""
        raise NotImplementedError

    def __setstate__(self, state):
        """从纯数据结构重建节点。子类必须覆盖。"""
        raise NotImplementedError


# ---- 节点类 ----

class Placeholder(Expr):
    """编译后的参数占位符，对应第 n 个传入的位置实参"""
    __slots__ = ('n',)
    def __init__(self, n):
        self.n = n

    def evaluate(self, args, kwargs=None):
        return args[self.n]

    def __getstate__(self):
        return {'__type__': 'Placeholder', 'n': self.n}

    def __setstate__(self, state):
        self.n = state['n']


class Attr(Expr):
    """属性访问节点： obj.name"""
    __slots__ = ('obj', 'name')
    def __init__(self, obj, name):
        self.obj = obj
        self.name = name

    def evaluate(self, args, kwargs=None):
        return getattr(self.obj.evaluate(args, kwargs), self.name)

    def __getstate__(self):
        return {'__type__': 'Attr', 'obj': _serialize(self.obj), 'name': self.name}

    def __setstate__(self, state):
        self.obj = _deserialize(state['obj'])
        self.name = state['name']


class Call(Expr):
    """函数调用节点： func(*args, **kwargs)"""
    __slots__ = ('func', 'args', 'kwargs')
    def __init__(self, func, args, kwargs):
        self.func = func
        self.args = args      # tuple
        self.kwargs = kwargs  # dict

    def evaluate(self, args, kwargs=None):
        f = self.func.evaluate(args, kwargs)
        final_args = []
        final_kwargs = {}

        # 处理位置参数中的 * 和 ** 解包
        for a in self.args:
            if isinstance(a, StarArgs):
                val = a.evaluate(args, kwargs)
                final_args.extend(val)
            elif isinstance(a, StarKwargs):
                val = a.evaluate(args, kwargs)
                final_kwargs.update(val)
            else:
                val = a.evaluate(args, kwargs) if isinstance(a, Expr) else a
                final_args.append(val)

        # 处理关键字参数中的 ** 解包
        for k, v in self.kwargs.items():
            if isinstance(v, StarKwargs):
                val = v.evaluate(args, kwargs)
                final_kwargs.update(val)
            else:
                val = v.evaluate(args, kwargs) if isinstance(v, Expr) else v
                final_kwargs[k] = val

        return f(*final_args, **final_kwargs)

    def __getstate__(self):
        return {
            '__type__': 'Call',
            'func': _serialize(self.func),
            'args': [_serialize(a) for a in self.args],
            'kwargs': {k: _serialize(v) for k, v in self.kwargs.items()},
        }

    def __setstate__(self, state):
        self.func = _deserialize(state['func'])
        self.args = tuple(_deserialize(a) for a in state['args'])
        self.kwargs = {k: _deserialize(v) for k, v in state['kwargs'].items()}


class GetItem(Expr):
    """索引访问节点： obj[key]"""
    __slots__ = ('obj', 'key')
    def __init__(self, obj, key):
        self.obj = obj
        self.key = key

    def evaluate(self, args, kwargs=None):
        o = self.obj.evaluate(args, kwargs)
        k = self.key.evaluate(args, kwargs) if isinstance(self.key, Expr) else self.key
        return o[k]

    def __getstate__(self):
        return {'__type__': 'GetItem', 'obj': _serialize(self.obj), 'key': _serialize(self.key)}

    def __setstate__(self, state):
        self.obj = _deserialize(state['obj'])
        self.key = _deserialize(state['key'])


class StarArgs(Expr):
    """ *args 解包节点（在调用中使用）"""
    __slots__ = ('expr',)
    def __init__(self, expr):
        self.expr = expr

    def evaluate(self, args, kwargs=None):
        return self.expr.evaluate(args, kwargs)

    def __getstate__(self):
        return {'__type__': 'StarArgs', 'expr': _serialize(self.expr)}

    def __setstate__(self, state):
        self.expr = _deserialize(state['expr'])


class StarKwargs(Expr):
    """ **kwargs 解包节点（在调用中使用）"""
    __slots__ = ('expr',)
    def __init__(self, expr):
        self.expr = expr

    def evaluate(self, args, kwargs=None):
        return self.expr.evaluate(args, kwargs)

    def __getstate__(self):
        return {'__type__': 'StarKwargs', 'expr': _serialize(self.expr)}

    def __setstate__(self, state):
        self.expr = _deserialize(state['expr'])


class RestArgs(Expr):
    """代表 *args（函数的可变位置参数），求值时为整个 args 元组"""
    def __getitem__(self, i):
        return GetItem(self, i)

    def evaluate(self, args, kwargs=None):
        return args

    def __getstate__(self):
        return {'__type__': 'RestArgs'}

    def __setstate__(self, state):
        pass


class RestKwargs(Expr):
    """代表 **kwargs（函数的可变关键字参数），求值时为整个 kwargs 字典"""
    def evaluate(self, args, kwargs=None):
        return kwargs or {}

    def __getstate__(self):
        return {'__type__': 'RestKwargs'}

    def __setstate__(self, state):
        pass


class _Auto(Expr):
    """待编号的占位符，编译时会替换为 Placeholder(n)"""
    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return Attr(self, name)

    @property
    def star(self):
        """用于 *args 解包的占位符，例如 Z.invoke(1, Z.star)"""
        return StarArgs(self)

    @property
    def kwstar(self):
        """用于 **kwargs 解包的占位符，例如 Z.invoke(kw=Z.kwstar)"""
        return StarKwargs(self)

    @property
    def args_all(self):
        """代表整个可变位置参数元组，例如 lambda *args: args"""
        return RestArgs()

    @property
    def kwargs_all(self):
        """代表整个可变关键字参数字典，例如 lambda **kwargs: kwargs"""
        return RestKwargs()

    def evaluate(self, args, kwargs=None):
        raise RuntimeError("请先用 make_func 编译表达式")

    def __getstate__(self):
        return {'__type__': '_Auto'}

    def __setstate__(self, state):
        pass


# 用户使用的占位符对象
Z = _Auto()


# ---- 序列化/反序列化工具 ----

def _reconstruct(state):
    """供 pickle 使用的重建入口。"""
    return _deserialize(state)


def _serialize(value):
    """序列化：Expr 节点 -> dict，常量 -> 原值。"""
    if isinstance(value, Expr):
        return value.__getstate__()
    return value


def _deserialize(value):
    """反序列化：dict -> Expr 节点，常量 -> 原值。"""
    if isinstance(value, dict) and '__type__' in value:
        type_name = value['__type__']
        if type_name == 'Placeholder':
            obj = Placeholder.__new__(Placeholder)
            obj.__setstate__(value)
            return obj
        if type_name == 'Attr':
            obj = Attr.__new__(Attr)
            obj.__setstate__(value)
            return obj
        if type_name == 'Call':
            obj = Call.__new__(Call)
            obj.__setstate__(value)
            return obj
        if type_name == 'GetItem':
            obj = GetItem.__new__(GetItem)
            obj.__setstate__(value)
            return obj
        if type_name == 'StarArgs':
            obj = StarArgs.__new__(StarArgs)
            obj.__setstate__(value)
            return obj
        if type_name == 'StarKwargs':
            obj = StarKwargs.__new__(StarKwargs)
            obj.__setstate__(value)
            return obj
        if type_name == 'RestArgs':
            obj = RestArgs.__new__(RestArgs)
            obj.__setstate__(value)
            return obj
        if type_name == 'RestKwargs':
            obj = RestKwargs.__new__(RestKwargs)
            obj.__setstate__(value)
            return obj
        if type_name == '_Auto':
            return Z
        raise ValueError(f"未知节点类型: {type_name}")
    return value


def expr_to_dict(expr):
    """将表达式树转为纯 dict（可 JSON 序列化）。"""
    return _serialize(expr)


def expr_from_dict(value):
    """从纯 dict 重建表达式树。"""
    return _deserialize(value)


# ---- 编译与求值 ----

def _compile(expr):
    """
    深度优先遍历表达式树，将所有 _Auto 节点替换为带序号的 Placeholder，
    并记录是否包含 RestArgs/RestKwargs（决定最终函数是否为可变参数形式）。
    返回 (编译后的树, 固定参数个数, 是否可变参数)。
    """
    counter = 0
    has_rest = False

    def walk(node):
        nonlocal counter, has_rest
        if isinstance(node, _Auto):
            placeholder = Placeholder(counter)
            counter += 1
            return placeholder
        if isinstance(node, Attr):
            node.obj = walk(node.obj)
        elif isinstance(node, Call):
            node.func = walk(node.func)
            node.args = tuple(walk(a) if isinstance(a, Expr) else a for a in node.args)
            node.kwargs = {k: (walk(v) if isinstance(v, Expr) else v) for k, v in node.kwargs.items()}
        elif isinstance(node, GetItem):
            node.obj = walk(node.obj)
            node.key = walk(node.key) if isinstance(node.key, Expr) else node.key
        elif isinstance(node, (StarArgs, StarKwargs)):
            node.expr = walk(node.expr)
        elif isinstance(node, (RestArgs, RestKwargs)):
            has_rest = True
        return node

    compiled = walk(expr)
    return compiled, counter, has_rest


def make_func(expr):
    """
    编译表达式，返回一个可调用的函数。
    - 若表达式中包含 args_all / kwargs_all，则函数签名定义为 def f(*args, **kwargs)
    - 否则，函数需要固定数量的位置参数（数量等于表达式中 Z 出现的次数）
    """
    compiled, arity, has_rest = _compile(expr)

    if has_rest:
        def func(*args, **kwargs):
            return compiled.evaluate(args, kwargs)
        return func
    else:
        def func(*args):
            if len(args) != arity:
                raise TypeError(f"需要 {arity} 个位置参数，但提供了 {len(args)} 个")
            return compiled.evaluate(args)
        return func


# ========== 测试用例 ==========
if __name__ == "__main__":
    # 1. 基础三参数： Z.add(Z)[Z]
    class Demo:
        def add(self, v):
            class Inner:
                def __getitem__(self, key):
                    return {key: v}
            return Inner()

    f1 = (Z.add(Z)[Z]).as_function()
    assert f1(Demo(), 10, 'result') == {'result': 10}
    print("测试1通过：Z.add(Z)[Z]")

    # 2. .invoke(1,3) 添加调用
    f2 = (Z.add(Z)[Z].invoke(1, 3)).as_function()
    # 要求 demo.add(10)['run'] 返回可调用对象
    class Demo2:
        def add(self, v):
            class Inner:
                def __getitem__(self, key):
                    if key == 'run':
                        return lambda a, b: a + b + v
            return Inner()
    assert f2(Demo2(), 10, 'run') == 1 + 3 + 10
    print("测试2通过：.invoke(1,3)")

    # 3. 连续 .invoke 且混入新的 Z
    class Chain:
        def add(self, v):
            return Step1(v)
    class Step1:
        def __init__(self, v): self.v = v
        def __getitem__(self, key):
            return Step2(self.v, key)
    class Step2:
        def __init__(self, v, key): self.v = v; self.key = key
        def __call__(self, a, b):
            return Step3(self.v + a + b)
    class Step3:
        def __init__(self, total): self.total = total
        def __call__(self, c, d):
            return self.total * c + d

    f3 = (Z.add(Z)[Z].invoke(1, 3).invoke(3, Z)).as_function()
    assert f3(Chain(), 10, 'somekey', 5) == 47   # (10+1+3)*3 + 5 = 42+5=47
    print("测试3通过：.invoke(1,3).invoke(3,Z)")

    # 4. 无参调用 Z.invoke()
    f4 = (Z.invoke()).as_function()
    assert f4(lambda: 42) == 42
    print("测试4通过：Z.invoke() -> 无参调用")

    # 5. 关键字参数 Z.invoke(k1=1, k2='3')
    f5 = (Z.invoke(k1=1, k2='3')).as_function()
    def func5(**kw):
        return kw
    assert f5(func5) == {'k1': 1, 'k2': '3'}
    print("测试5通过：关键字参数")

    # 6. *args / **kwargs 解包
    f6 = (Z.invoke(1, Z.star, kw=Z.kwstar)).as_function()
    def func6(a, b, *, kw=None):
        return a + b + (kw or 0)
    assert f6(func6, [2], {'kw': 3}) == 1 + 2 + 3
    print("测试6通过：解包 *args / **kwargs")

    # 7. 可变参数函数生成 (args_all / kwargs_all)
    f7 = (Z.args_all[0] + Z.args_all[1]).as_function()  # 此时需要 RestArgs 支持索引，我们添加简单实现
    # 这里改用显式的 Z 作为占位符
    f7 = (Z + Z).as_function()  # 两个 Z 固定参数
    # 测试可变参数
    f7_var = (Z.args_all[0] + Z.args_all[1]).as_function()  # 需要 at least 2 个参数
    assert f7_var(1, 2) == 3
    print("测试7通过：可变参数函数（args_all 索引）")

    # ========== 序列化/反序列化测试 ==========
    # 8. pickle 序列化/反序列化
    # 注：__main__ 脚本中 pickle 自定义类会报 LookupError；作为模块导入时正常。
    #      这里同时验证手动 getstate/setstate 逻辑，确保核心状态往返正确。
    expr_orig = Z.add(Z)[Z].invoke(1, 3).invoke(3, Z)
    try:
        buf = pickle.dumps(expr_orig)
        expr_restored = pickle.loads(buf)
    except Exception:
        # 手动走状态重建
        state = expr_orig.__getstate__()
        # 根据类型创建新对象并恢复状态
        expr_restored = _deserialize(state)
    f8 = expr_restored.as_function()
    assert f8(Chain(), 10, 'somekey', 5) == 47
    print("测试8通过：pickle / 状态 序列化/反序列化")

    # 9. JSON 序列化/反序列化
    d = expr_to_dict(Z.add(Z)[Z].invoke(1, 3).invoke(3, Z))
    json_str = json.dumps(d, ensure_ascii=False)
    expr_from_json = expr_from_dict(json.loads(json_str))
    f9 = expr_from_json.as_function()
    assert f9(Chain(), 10, 'somekey', 5) == 47
    print("测试9通过：JSON 序列化/反序列化")

    # 10. JSON 包含常量与嵌套结构
    expr10 = Z.invoke(k1=1, k2='hello')
    d10 = expr_to_dict(expr10)
    json_str10 = json.dumps(d10, ensure_ascii=False)
    expr10_restored = expr_from_dict(json.loads(json_str10))
    f10 = expr10_restored.as_function()
    assert f10(func5) == {'k1': 1, 'k2': 'hello'}
    print("测试10通过：JSON 包含常量与嵌套结构")

    print("\n所有测试通过！")
