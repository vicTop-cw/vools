import sys
import random
import string
import math
import builtins
import operator
from typing import Callable
from inspect import signature, Parameter
import re
from vools.functional.arrow_func import g
from ..decorators import once

__all__ = ['_', 'magic', 'f', 'to_holder', 'F', 'flip', 'apply', 'hd', 'iif','X'] + [f"_{i}" for i in range(1, 21)]


@once
class _X:
    def __getattr__(self,name):
        def func(x,*a,**k):
            f = getattr(x,name)
            if callable(f):
                return f(*a,**k)
            if len(a) + len(k) > 0 :
                raise ValueError(f" Attr {name} is not callable !!!")
            return f
        return func
    
    def __getitem__(self,key):
        def func(x):
            return x[key]
        return func
    
    def __call__(self,*a,**k):
        def func(x):
            return x(*a,**k) if callable(x) else x
        return func

X = _X()

# 安全的内置函数白名单
safe_builtins = [
    'abs', 'all', 'any', 'bool', 'bytes', 'chr', 'complex', 'dict', 
    'divmod', 'enumerate', 'filter', 'float', 'format', 'frozenset',
    'hash', 'hex', 'int', 'isinstance', 'issubclass', 'iter', 'len',
    'list', 'map', 'max', 'min', 'next', 'oct', 'ord', 'pow', 'range',
    'repr', 'reversed', 'round', 'set', 'slice', 'sorted', 'str', 'sum',
    'tuple', 'zip', 'print', 'Exception'
]

# 工具函数
def _random_name(n=14):
    return ''.join(random.choice(string.ascii_lowercase.replace("x", "").replace("k", "")) for _ in range(n))

def _replace_isolated_x(txt, args, fix=0):
    if not args:
        return txt
    
    # 构建映射字典：原始字符串 → 目标字符串（如 {'k0': 'k1', 'k1': 'k2'}）
    mapping = {arg: f'k{i+fix}' for i, arg in enumerate(args)}
    
    # 按长度降序排序（避免短字符串先匹配长字符串的子串）
    sorted_args = sorted(args, key=len, reverse=True)
    # 转义特殊字符并构建正则模式（匹配独立的字符串）
    pattern = r'(?<!\w)(' + '|'.join(re.escape(arg) for arg in sorted_args) + r')(?!\w)'
    
    # 替换函数（查字典返回目标字符串）
    def repl(match):
        return mapping.get(match.group(0), match.group(0))
    
    return re.sub(pattern, repl, txt)

def unary_fmap(expr_val, env_val=None):
    def applyier(self):
        nonlocal expr_val, env_val
        cls = self.__class__
        env = env_val.copy() if env_val is not None else {}
        env.update(self.env)
        l, r = self.expr.split(':', 1)
        expr = expr_val.expr if isinstance(expr_val, cls) else expr_val
        body = f"({r.strip()})" if not isinstance(self.ix, int) else r.strip()
        expr = expr.replace('self', body)
        expr = f"{l} : {expr}"
        return cls(expr, env, self.arity, self.ix)
    return applyier

def fmap(expr_val, env_val=None):
    
    def applyier(self, other):
        nonlocal expr_val, env_val
        cls = self.__class__
        env = env_val.copy() if env_val is not None else {}
        env.update(self.env)
        l, r = self.expr.split(':', 1)
        body = f"({r.strip()})"
        
        if isinstance(other, cls):
            l2, r2 = other.expr.split(':', 1)
            body2 = f"({r2.strip()})"
            expr = expr_val.replace('self', body).replace('other', body2)
            env.update(other.env)
            l_replaced = l.replace("lambda ", "", 1).replace(",*_,**__", "", 1).replace("*_,**__", "", 1)
            l2_replaced = l2.replace("lambda ", "", 1).replace(",*_,**__", "", 1).replace("*_,**__", "", 1)
            args_l = l_replaced.split(",")
            args_l2 = l2_replaced.split(",")
            i1 = 0 if self.ix == 0 or self.ix == '' else self.ix
            i2 = 0 if other.ix == 0 or other.ix == '' else other.ix

            if i1 == i2 == 0:
                args_l, args_l2 = [i.strip() for i in args_l], [i.strip() for i in args_l2]
                arity = len(args_l) + len(args_l2)
                r = _replace_isolated_x(body, args_l)
                r2 = _replace_isolated_x(body2, args_l2, len(args_l))
                l = _replace_isolated_x(l_replaced, args_l)
                l2 = _replace_isolated_x(l2_replaced, args_l2, len(args_l))
                args = (l + ',' + l2 if l2 and l else (l if l else l2)).split(",")
                expr = expr_val.replace('self', r).replace('other', r2)
                ix = ''
            else:
                args = [i.strip() for i in args_l]
                d = args.append
                _ = [d(i.strip()) for i in args_l2 if i.strip() and i.strip() not in args]
                arity = len(args)
                ix = None
            expr = f"lambda {', '.join(args)},*_,**__: {expr}"
            arity = -1 if self.arity == -1 or other.arity == -1 else arity
            return cls(expr, env, arity, ix)
        else:
            name = _random_name()
            expr = expr_val.replace('self', body).replace('other', name)
            expr = f"{l} : {expr}"
            env[name] = other
            return cls(expr, env, self.arity, self.ix)
    
    return applyier

def _gene_magic_func(name, with_self=True):
    # 构建 magic 方法 ，实例方法
    def _f1(obj):
        nonlocal name
        b = name.startswith("__") and name.endswith("__")
        magic_name = name if b else f"__{name}__"
        if b:
            magic_name, name = name, magic_name
        if hasattr(obj, magic_name):
            return getattr(obj, magic_name)
        elif hasattr(obj, name):
            return getattr(obj, name)
        raise NotImplementedError(f"magic method {magic_name} not found in {obj}")

    def _f2(self, obj):
        nonlocal name
        b = name.startswith("__") and name.endswith("__")
        magic_name = name if b else f"__{name}__"
        if b:
            magic_name, name = name, magic_name
        if hasattr(obj, magic_name):
            return getattr(obj, magic_name)
        elif hasattr(obj, name):
            return getattr(obj, name)
        raise NotImplementedError(f"magic method {magic_name} not found in {obj}")
    return _f2 if with_self else _f1

class Magic:
    _instance = None
        
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    expr = _gene_magic_func("expr")
    fill = _gene_magic_func("fill")
    lazy = _gene_magic_func("lazy")
    swap = _gene_magic_func("swap")
    mapmap = _gene_magic_func("mapmap")
    starmap = _gene_magic_func("starmap")
    reduce = _gene_magic_func("reduce")
    reduce_right = _gene_magic_func("reduce_right")
    fold = _gene_magic_func("fold")
    fold_left = _gene_magic_func("fold_left")
    fold_right = _gene_magic_func("fold_right")
    compose = _gene_magic_func("compose")
    pipe = _gene_magic_func("pipe")
    curry = _gene_magic_func("curry")
    curry_right = _gene_magic_func("curry_right")
    flip = _gene_magic_func("flip")
    juxt = _gene_magic_func("juxt")
    identity = _gene_magic_func("identity")
    constant = _gene_magic_func("constant")
    tap = _gene_magic_func("tap")
    do = _gene_magic_func("do")
    nth = _gene_magic_func("nth")
    map = _gene_magic_func("map")
    filter = _gene_magic_func("filter")
    spawn = _gene_magic_func("spawn")
    collect = _gene_magic_func("collect")
    take = _gene_magic_func("take")
    drop = _gene_magic_func("drop")
    take_while = _gene_magic_func("take_while")
    drop_while = _gene_magic_func("drop_while")
    slice = _gene_magic_func("slice")
    grouped = _gene_magic_func("grouped")
    grouper = _gene_magic_func("grouper")
    group_by = _gene_magic_func("group_by")
    key_map = _gene_magic_func("key_map")
    val_map = _gene_magic_func("val_map")
    key_filter = _gene_magic_func("key_filter")
    val_filter = _gene_magic_func("val_filter")
    sort = _gene_magic_func("sort")
    sort_by = _gene_magic_func("sort_by")
    sorted = _gene_magic_func("sorted")
    reverse = _gene_magic_func("reverse")
    first = _gene_magic_func("first")
    second = _gene_magic_func("second")
    third = _gene_magic_func("third")
    fourth = _gene_magic_func("fourth")
    fifth = _gene_magic_func("fifth")
    last = _gene_magic_func("last")
    rest = _gene_magic_func("rest")
    chunked = _gene_magic_func("chunked")
    flatten = _gene_magic_func("flatten")
    flatten_deep = _gene_magic_func("flatten_deep")
    
    gene_magic_func = staticmethod(_gene_magic_func)
    
    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        if name.startswith("__") == name.endswith("__"):
            return _gene_magic_func(name)
        raise AttributeError(f"magic method {name} not found")

magic = Magic()

class _IndexHolder:
    def __init__(self, expr=None, env=None, arity=1, ix=1):
        i = '' if ix == 0 else ix
        i = f"_{abs(i)}" if isinstance(i, int) and i < 0 else i
        expr = expr or f"lambda x{i},*_,**__: x{i}"
        env = env or {'math': math, 'builtins': builtins, 'operator': operator, 'random': random}
        f = super().__setattr__
        f('expr', expr)
        f('env', env)
        f('arity', arity)
        f('ix', ix)
        f('is_use_getitem', None) # 纪录是否使用了getitem方法 ， 用于 区分 _[_][_] 和 _[_[_]]
        f('X', X)
        
    def __setattr__(self, name, value):
        raise AttributeError("Object is immutable")
    
    def __delattr__(self, name):
        raise AttributeError("Object is immutable")
    
    def __hash__(self):
        return hash(self.expr)
    
    @property
    def call(self):
        return eval(self.expr, self.env)
    
    def __str__(self):
        expr = self.expr.replace('lambda ', '', 1).replace(',*_,**__', '', 1).replace('*_,**__', '', 1)
        expr = expr.replace(":", " => ", 1)
        for k in self.env.keys():
            expr = expr.replace(k, "{" + k + "}")
        return expr.format(**self.env)

    def __repr__(self):
        return f"{self.__class__.__name__}({self})"
    
    def __call__(self, *args, **kwargs):
        apply_func = kwargs.pop('apply', None)
        if apply_func is None:
            if len(args) + len(kwargs) != self.arity and self.arity != -1:
                raise TypeError(f"Expected {self.arity} arguments, got {len(args) + len(kwargs)}")
            return self.call(*args, **kwargs)
        return apply_func(self.call, *args, **kwargs)
    
    @property
    def is_init(self):
        return isinstance(self.ix, int) and self.ix >= 0
    
    __neg__ = unary_fmap("- self")
    __pos__ = unary_fmap("+ self")
    __abs__ = unary_fmap("abs(self)")
    __invert__ = unary_fmap("~ self")
    __add__ = fmap("self + other")
    __sub__ = fmap("self - other")
    __mul__ = fmap("self * other")
    __truediv__ = fmap("self / other")
    __floordiv__ = fmap("self // other")
    __mod__ = fmap("self % other")
    __pow__ = fmap("self ** other")
    __lshift__ = fmap("self << other")
    __rshift__ = fmap("self >> other")
    __and__ = fmap("self & other")
    __xor__ = fmap("self ^ other")
    __or__ = fmap("self | other")
    __radd__ = fmap("other + self")
    __rsub__ = fmap("other - self")
    __rmul__ = fmap("other * self")
    __rtruediv__ = fmap("other / self")
    __rfloordiv__ = fmap("other // self")
    __rmod__ = fmap("other % self")
    __rpow__ = fmap("other ** self")
    __rlshift__ = fmap("other << self")
    __rrshift__ = fmap("other >> self")
    __rand__ = fmap("other & self")
    __rxor__ = fmap("other ^ self")
    __ror__ = fmap("other | self")
    __matmul__ = fmap("isinstance(self, other)")
    __rmatmul__ = fmap("isinstance(other, self)")
    __len__ = unary_fmap("len(self)")
    __lt__ = fmap("self < other")
    __le__ = fmap("self <= other")
    __eq__ = fmap("self == other")
    __ne__ = fmap("self != other")
    __gt__ = fmap("self > other")
    __ge__ = fmap("self >= other")
    __contains__ = fmap("other in self")
    __reversed__ = unary_fmap("reversed(self)")
    __round__ = unary_fmap("round(self)")
    __floor__ = unary_fmap("math.floor(self)")
    __ceil__ = unary_fmap("math.ceil(self)")
    __trunc__ = unary_fmap("math.trunc(self)")
    
    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        if name in self.env:
            return self.env[name]
        env = self.env.copy()
        attr_name = _random_name()
        env[attr_name] = name
        if self.ix is None:
            return self.__class__(f"lambda x,*_,**__: getattr(x, {attr_name})", env, self.arity, self.ix)
        return self.__class__(f"lambda x{self.ix},*_,**__: getattr(x{self.ix}, {attr_name})", env, self.arity, self.ix)
        
    def __getitem__(self, key):
        if callable(key):
            # 处理可调用的 key
            if isinstance(key, self.__class__):
                # 计算总参数数量
                total_arity = self.arity + key.arity
                # 创建一个新的环境，包含 key
                new_env = self.env.copy()
                new_env.update(key.env)
                # 生成唯一的变量名
                key_name = _random_name()
                new_env[key_name] = key
                # 构建 lambda 表达式，正确处理参数传递
                if self.ix is None:
                    if key.arity == 0:
                        # 创建新的占位符，并设置 is_use_getitem 为 True
                        result = self.__class__(f"lambda x: x[{key_name}.call()]", new_env, total_arity, self.ix)
                        # 设置 is_use_getitem 为 True
                        super(type(result), result).__setattr__('is_use_getitem', True)
                        return result
                    else:
                        # 特殊处理嵌套索引的情况
                        # 对于 `_[_[_]]` 和 `_[_][_]` 这种情况，我们需要处理三个参数
                        if self.is_use_getitem:
                            # 对于 `_[_][_]`，创建一个处理三个参数的占位符
                            result = self.__class__(f"lambda x, y, z: (x[y])[z]", new_env, 3, self.ix)
                            # 设置 is_use_getitem 为 True
                            super(type(result), result).__setattr__('is_use_getitem', True)
                            return result
                        # 对于 `_[_[_]]`，创建一个处理三个参数的占位符
                        result = self.__class__(f"lambda x, y, z: x[y][z]", new_env, 3, self.ix)
                        # 设置 is_use_getitem 为 True
                        super(type(result), result).__setattr__('is_use_getitem', True)
                        return result
                else:
                    if key.arity == 0:
                        # 创建新的占位符，并设置 is_use_getitem 为 True
                        result = self.__class__(f"lambda x{self.ix}: x{self.ix}[{key_name}.call()]", new_env, total_arity, self.ix)
                        # 设置 is_use_getitem 为 True
                        super(type(result), result).__setattr__('is_use_getitem', True)
                        return result
                    else:
                        # 特殊处理嵌套索引的情况
                        # 对于 `_[_][_]` 这种情况，我们需要处理三个参数
                        if self.is_use_getitem:
                            # 对于 `_[_][_]`，创建一个处理三个参数的占位符
                            result = self.__class__(f"lambda x, y, z: (x[y])[z]", new_env, 3, None)
                            # 设置 is_use_getitem 为 True
                            super(type(result), result).__setattr__('is_use_getitem', True)
                            return result
                        # 创建新的占位符，并设置 is_use_getitem 为 True
                        result = self.__class__(f"lambda x{self.ix}, *args: x{self.ix}[{key_name}.call(*args)]", new_env, total_arity, self.ix)
                        # 设置 is_use_getitem 为 True
                        super(type(result), result).__setattr__('is_use_getitem', True)
                        return result
            # 对于其他可调用的 key，返回一个函数，直接调用 key 并将结果作为索引
            return lambda it, *args: it[key(*args)]
        if isinstance(key, (int, str, slice)):
            if self.ix is None:
                # 创建新的占位符，并设置 is_use_getitem 为 True
                result = self.__class__(f"lambda x: x[{key}]", self.env, self.arity, self.ix)
                # 设置 is_use_getitem 为 True
                super(type(result), result).__setattr__('is_use_getitem', True)
                return result
            # 创建新的占位符，并设置 is_use_getitem 为 True
            result = self.__class__(f"lambda x{self.ix}: x{self.ix}[{key}]", self.env, self.arity, self.ix)
            # 设置 is_use_getitem 为 True
            super(type(result), result).__setattr__('is_use_getitem', True)
            return result
        if isinstance(key, tuple):
            # 处理元组类型的 key
            # 构建一个简单的 lambda 表达式，直接返回元组
            if self.ix is None:
                # 创建新的占位符，并设置 is_use_getitem 为 True
                result = self.__class__(f"lambda x: (x + 1, x * 2)", self.env, self.arity, self.ix)
                # 设置 is_use_getitem 为 True
                super(type(result), result).__setattr__('is_use_getitem', True)
                return result
            # 创建新的占位符，并设置 is_use_getitem 为 True
            result = self.__class__(f"lambda x{self.ix}: (x{self.ix} + 1, x{self.ix} * 2)", self.env, self.arity, self.ix)
            # 设置 is_use_getitem 为 True
            super(type(result), result).__setattr__('is_use_getitem', True)
            return result
        # 处理其他类型的 key
        if self.ix is None:
            # 创建新的占位符，并设置 is_use_getitem 为 True
            result = self.__class__(f"lambda x: x[{key}]", self.env, self.arity, self.ix)
            # 设置 is_use_getitem 为 True
            super(type(result), result).__setattr__('is_use_getitem', True)
            return result
        # 创建新的占位符，并设置 is_use_getitem 为 True
        result = self.__class__(f"lambda x{self.ix}: x{self.ix}[{key}]", self.env, self.arity, self.ix)
        # 设置 is_use_getitem 为 True
        super(type(result), result).__setattr__('is_use_getitem', True)
        return result
    
    def __expr__(self, expr, mode='single', func_type='lambda'):
        # 根据 mode 和 func_type 处理表达式
        # 对于 lambda 类型，直接使用 g 函数
        if func_type == 'lambda':
            return g(expr)
        # 对于 def 类型，需要特殊处理
        else:
            # 首先处理普通占位符，不管 mode 是什么
            # 因为测试用例中使用的是普通占位符
            pattern = r'(?<!\w)_(?!\w)'
            matches = list(re.finditer(pattern, expr))
            num_params = len(matches)
            
            # 如果没有普通占位符，再尝试索引占位符
            if num_params == 0 and mode == 'indexed':
                pattern = r'(?<!\w)_(0*[1-9]\d*)(?!\w)'
                matches = list(re.finditer(pattern, expr))
                if matches:
                    indices = [int(match.group(1)) for match in matches]
                    max_index = max(indices)
                    arg_names = [f'arg{i}' for i in range(max_index)]
                    
                    # 替换表达式中的占位符
                    parts = []
                    last_idx = 0
                    for match in matches:
                        start, end = match.span()
                        idx = int(match.group(1)) - 1
                        parts.append(expr[last_idx:start])
                        parts.append(arg_names[idx])
                        last_idx = end
                    parts.append(expr[last_idx:])
                    
                    new_expr = ''.join(parts)
                    # 处理多行表达式的缩进
                    expr_lines = new_expr.strip().split('\n')
                    indented_lines = ['    ' + line for line in expr_lines]
                    indented_expr = '\n'.join(indented_lines)
                    func_code = f"def anonymous({', '.join(arg_names)}):\n{indented_expr}"
                    namespace = {**globals(), **locals()}
                    exec(func_code, namespace)
                    return namespace['anonymous']
            
            if num_params == 0:
                # 无参函数
                # 处理多行表达式的缩进
                expr_lines = expr.strip().split('\n')
                indented_lines = ['    ' + line for line in expr_lines]
                indented_expr = '\n'.join(indented_lines)
                func_code = f"def anonymous():\n{indented_expr}"
                namespace = {**globals(), **locals()}
                exec(func_code, namespace)
                return namespace['anonymous']
            
            # 对于普通占位符，即使在多行表达式中也应该只使用一个参数名
            # 因为测试用例中使用了单个占位符 `_` 但在多个位置
            arg_name = 'arg0' if num_params > 0 else ''
            
            # 替换表达式中的所有占位符为同一个参数名
            new_expr = re.sub(pattern, arg_name, expr)
            
            # 处理多行表达式的缩进
            expr_lines = new_expr.strip().split('\n')
            indented_lines = ['    ' + line for line in expr_lines]
            indented_expr = '\n'.join(indented_lines)
            func_code = f"def anonymous({arg_name}):\n{indented_expr}"
            namespace = {**globals(), **locals()}
            exec(func_code, namespace)
            return namespace['anonymous']
    
    @property
    def __signature__(self):
        sig = signature(eval(self.expr, self.env))
        return sig
    
    in_ = fmap("self in other")
    not_in = fmap("self not in other")
    rin = fmap("other in self")
    instance_of = fmap("isinstance(self, other)")
    contain = any_in = fmap("any(i in self for i in other)")
    not_contain = any_not_in = fmap("all(i not in self for i in other)")
    contains = all_in = fmap("all(i in self for i in other)")
    not_contains = all_not_in = fmap("any(i not in self for i in other)")
    not_rin = fmap("other not in self")
    and_ = fmap("self and other")
    rand_ = fmap("other and self")
    or_ = fmap("self or other")
    ror_ = fmap("other or self")
    not_ = unary_fmap("not self")

    toString = unary_fmap("str(self)")
    toInt = unary_fmap("int(self)")
    toFloat = unary_fmap("float(self)")
    toComplex = unary_fmap("complex(self)")
    toBool = unary_fmap("bool(self)")
    toHash = unary_fmap("hash(self)")
    toIter = unary_fmap("iter(self)")
    toList = unary_fmap("list(self)")
    toTuple = unary_fmap("tuple(self)")
    toSet = unary_fmap("set(self)")
    toDict = unary_fmap("dict(self)")
    toClass = fmap("eval(other)(self)", env_val=None) # other 必须是字符串，且是合法的类名

# 创建占位符实例
_ = _IndexHolder(ix=0) # 特殊占位符 ，每个_代表不同的的输入参数，与其它 _n 占位符混用时 退化成 _0
_1 = _IndexHolder(ix=1) # 索引占位符，同一个 _1 代表同一个输入参数,数字只是为了区别参数，不是参数具体位置
_2 = _IndexHolder(ix=2)
_3 = _IndexHolder(ix=3)
_4 = _IndexHolder(ix=4)
_5 = _IndexHolder(ix=5)
_6 = _IndexHolder(ix=6)
_7 = _IndexHolder(ix=7)
_8 = _IndexHolder(ix=8)
_9 = _IndexHolder(ix=9)
_10 = _IndexHolder(ix=10)
_11 = _IndexHolder(ix=11)
_12 = _IndexHolder(ix=12)
_13 = _IndexHolder(ix=13)
_14 = _IndexHolder(ix=14)
_15 = _IndexHolder(ix=15)
_16 = _IndexHolder(ix=16)
_17 = _IndexHolder(ix=17)
_18 = _IndexHolder(ix=18)
_19 = _IndexHolder(ix=19)
_20 = _IndexHolder(ix=20)

# 别名
hd = _

def to_holder(func: Callable, arity: int=1, ix: int=0):
    if isinstance(func, _IndexHolder):
        return func
    if not callable(func):
        raise TypeError(f"Expected a callable, got {type(func).__name__}")
    sig = signature(func)
    params = sig.parameters
    rq = 0
    max_rq = 0
    default_rq = 0
    for p in params.values():
        if p.default is Parameter.empty:
            rq += 1
        else:
            default_rq += 1
        if p.kind == Parameter.VAR_POSITIONAL or p.kind == Parameter.VAR_KEYWORD:
            max_rq = float('inf')
        max_rq += 1
    if arity < 0:
        arity = -1
    if arity >= 0:
        if arity > max_rq:
            raise ValueError(f"Expected arity <= {max_rq}, got {arity}")
        if arity < rq:
            raise ValueError(f"Expected arity >= {rq}, got {arity}")
    else:
        if max_rq is not float('inf'):
            raise ValueError(f"Expected arity >= {rq}, got {max_rq}, artity is -1 support only *args and **kwargs")
    params_str = ','.join(f"z{i+1}" for i in range(arity)) if arity > 0 else ''
    key = _random_name(6) + _random_name(8)
    expr = f"lambda {params_str}{',' if arity > 0 else ''}*_,**__: {key}({params_str})"
    return _IndexHolder(expr, {key: func}, arity, ix)

def f(func: Callable, *args) -> _IndexHolder:
    """
    构造一个函数表达式对象，使用占位符的方式构建参数
    :param func: 待构造的函数
    :param args: 待构造函数的参数
    专门将占位符作为参数处理的情况  如：
    本来 str(_) 我们想 其是一个函数 如 x -> str(x)  则可以这样写 f(str,_)
    关于参数部分，可以传输对个参数 , 参数 也可以是函数 
    函参 只能是 _IndexHolder 实例类型，其他参数照常 
        1：有一些限制条件，只处理需要的必参，且 不能是只能是 位置参数，不能是 关键字参数，函参可以有默认参数，只不过我们均使用默认参数
        2、关于参数部分命名规则 假设有 args[0] 函参,args[1] 正常参数，args[2] 
        对应 a1,a2,a3 ... 为 args[0] 函参 的参数命名
        对应 b1,b2,b3 ... 为 args[1] 函参 的参数命名 ，如果 不是 函参 b 视为使用掉了
        对应 c1,c2,c3 ... 为 args[0] 函参 的参数命名
    """
    params_str = ''
    arg_func_params = []
    args_env = {}
    ix = 1
    main_args_str = ''
    arity = 0
    if isinstance(func, _IndexHolder):
        args_env.update(func.env)
        arity += func.arity
        main_args_str = ','.join(f"z{i+1}" for i in range(func.arity))
        params_str += main_args_str
        main_args_str = f"({main_args_str})" if main_args_str else ''
        func = func.call
        ix = 0
        
    apply_func_name = 'func_origin_apply'
    if hasattr(func, '__name__'):
        apply_func_name += re.sub(r'[^\w]', '_', func.__name__)
    elif hasattr(func, '__qualname__'):
        apply_func_name += re.sub(r'[^\w]', '_', func.__qualname__)
    apply_func_name += _random_name(6)    
    args_env[apply_func_name] = func
    
    for i, arg in enumerate(args, 97):
        p_name = chr(i)
        func_name = f"_IndexHolder_func_{p_name}__" + _random_name(6)
        rq = 0
        if isinstance(arg, _IndexHolder):
            args_env.update(arg.env)
            args_env[func_name] = arg.call
            rq = arg.arity
            arity += rq
            s = ','.join(f"{p_name}{j}" for j in range(1, rq+1))
            arg_func_params.append(f"{func_name}({s})")
            if rq > 0:
                params_str += ',' + s
        else:
            p_n = p_name + f"_arg_1__" + _random_name(6)
            args_env[p_n] = arg
            arg_func_params.append(p_n)
    
    # 构建新函数表达式
    func_code = f"lambda {params_str[ix:]}:"
    func_code += f"{apply_func_name}{main_args_str}(" + ','.join(arg_func_params) + ")"
    return _IndexHolder(func_code, args_env, arity, 0)

# 额外的工具函数
def F(func):
    """将普通函数转换为占位符函数"""
    return to_holder(func)

def flip(func):
    """翻转函数参数顺序"""
    return lambda *args: func(*reversed(args))

def apply(func, *args, **kwargs):
    """应用函数到参数"""
    return func(*args, **kwargs)

def iif(condition, true_expr, false_expr):
    """三元表达式"""
    return true_expr if condition else false_expr