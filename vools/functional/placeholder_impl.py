"""
函数式编程占位符工具集 —— X、Y 和 Z

提供三层渐进式的函数式编程能力：

---

**一、X — 方括号终止模式**

使用 ``[]`` 终止链式调用并执行。

- ``X.attr`` → ``PipeX`` 管道对象
- ``X(*args, **kwargs)`` → ``PipeX`` 管道对象
- ``X[key]`` → ``PipeX`` 管道对象（索引操作）
- ``[target]`` → 执行管道并返回结果
- ``[target, idx...]`` → 执行管道并应用额外索引
- ``[None, idx...]`` → 追加索引操作到管道（不执行）
- ``.f(func)`` → 添加结果映射函数
- ``.as_function()`` → 返回普通可调用函数 ``fn(x, f=None)``

二 — Y — 关键字参数终止模式

使用 ``(target, exe=True)`` 终止链式调用并执行。

- ``Y.attr`` → ``PipeY`` 管道对象
- ``Y[key]`` → ``PipeY`` 管道对象（索引操作）
- ``Y(*args, **kwargs)`` → ``PipeY`` 管道对象
- ``(target, exe=True)`` → 执行管道并返回结果
- ``(target, exe=True, f=factory)`` → 执行管道并应用工厂函数
- ``.f(func)`` → 添加结果映射函数
- ``.as_function()`` → 返回普通可调用函数 ``fn(x, f=None)``
- ``.as_subscript()`` → 返回下标执行器，支持 ``[target]`` 或 ``[target, idx...]``

三 — Z — 惰性表达式占位符系统

编译时延迟绑定，将表达式树编译为可调用函数。

- ``Z.attr`` → ``Attr`` 属性访问节点
- ``Z[key]`` → ``GetItem`` 索引访问节点
- ``Z(*args, **kwargs)`` / ``Z.invoke(...)`` → ``Call`` 调用节点
- ``Z.star`` / ``Z.kwstar`` → ``*args`` / ``**kwargs`` 解包节点
- ``Z.args_all`` / ``Z.kwargs_all`` → 可变参数引用节点
- ``.as_function()`` → 编译表达式树并返回可调用函数
- ``make_func(expr)`` → 同 ``.as_function()``
- ``expr_to_dict(expr)`` / ``expr_from_dict(d)`` → JSON 序列化/反序列化

通用特性
^^^^^^^^

- 属性访问: ``.attr``
- 方法调用: ``(*args, **kwargs)``
- 索引操作: ``[key]``
- 函数映射: ``.f(func)``
- 链式调用: 任意顺序组合
- 副作用调试: ``.do(f=print)``

设计理念
^^^^^^^^

- **延迟执行**：构建时不报错，执行时才检查类型
- **管道组合**：任意顺序组合操作序列，一次执行
- **可序列化**：Z 表达式树支持 pickle 和 JSON 双向序列化

导出
^^^^

    X, Y, Z — 单例占位符实例

示例
^^^^

X 的基本用法::

    X.strip()['  hello  ']                    # → 'hello'
    X.strip().split(',')['a,b,c']             # → ['a', 'b', 'c']
    X.split(',')[None, 1]['a,b,c']            # → 'b'
    X.split(',')['a,b,c', 1]                  # → 'b'
    X.split(',').f(list)['a,b,c']             # → ['a', 'b', 'c']

Y 的基本用法::

    Y.strip()('  hello  ', exe=True)          # → 'hello'
    Y.strip().split(',')('a,b,c', exe=True)   # → ['a', 'b', 'c']
    Y.split(',')('a,b,c', exe=True, f=list)  # → ['a', 'b', 'c']
    Y.strip().as_function()('  hello  ')      # → 'hello'
    Y.strip().as_subscript()['  hello  ']     # → 'hello'

Z 的基本用法::

    f = (Z.strip().upper()).as_function()
    f('  hello  ')                            # → 'HELLO'

    g = (Z['name'].upper()).as_function()
    g({'name': 'alice'})                      # → 'ALICE'

    h = (Z.split(',').f(list)).as_function()
    h('a,b,c')                                # → ['a', 'b', 'c']

索引操作::

    X[0]['hello']                             # → 'h'
    X['name'][{'name': 'Alice'}]              # → 'Alice'
    Y[0]['hello', exe=True]                   # → 'h'

链式组合::

    X.strip().upper()['  hello  ']            # → 'HELLO'
    X.split(',')[None, 0].upper()['a,b,c']    # → 'A'
"""

from typing import Any, Callable, Optional

__all__ = ['X', 'Y','Z']


class _X:
    """
    X 单例类 —— 使用方括号 ``[]`` 终止链式调用。

    X 本身不执行任何操作，而是作为一个入口点：通过属性访问、方法调用或索引操作
    创建一个 ``PipeX`` 管道对象，记录一连串待执行的操作序列。

    核心用法
    --------
    - ``X.attr`` → 返回 ``PipeX`` 管道对象
    - ``X(*args, **kwargs)`` → 返回 ``PipeX`` 管道对象
    - ``X[key]`` → 返回 ``PipeX`` 管道对象（索引操作）
    - ``pipe[target]`` → 执行管道，返回结果

    管道操作
    --------
    - ``.attr`` — 属性访问
    - ``(*args, **kwargs)`` — 方法调用
    - ``[key]`` — 索引操作
    - ``[target]`` — 执行管道（终止操作）
    - ``[target, idx...]`` — 执行管道并应用额外索引
    - ``[None, idx...]`` — 追加索引操作（不执行，继续构建）
    - ``.f(func)`` — 添加结果映射函数
    - ``.as_function()`` — 终止管道，返回普通函数 ``fn(x, f=None)``
    - ``.do(f=print, pre_f=None, sub_f=None)`` — 副作用调试

    示例
    ----
    ::

        # 基础用法
        X.strip()['  hello  ']                     # → 'hello'

        # 链式调用
        X.strip().split(',')['a,b,c']              # → ['a', 'b', 'c']

        # 追加索引（构建模式）
        X.split(',')[None, 1]['a,b,c']             # → 'b'

        # 执行时索引
        X.split(',')['a,b,c', 1]                   # → 'b'

        # 函数映射
        X.split(',').f(list)['a,b,c']              # → ['a', 'b', 'c']

        # 转换为普通函数
        f = X.strip().as_function()
        f('  hello  ')                              # → 'hello'

    执行流程
    --------
    1. ``X.attr`` / ``X(...)`` / ``X[key]`` 创建一个 ``PipeX``，记录第一个操作
    2. 继续 ``.attr`` / ``(...)`` / ``.f(func)`` / ``[None, idx]`` 追加操作
    3. ``pipe[target]`` 终止：从 target 开始，依次应用所有记录的操作
    4. 返回最终结果
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __getstate__(self):
        """Singleton: return module path reference"""
        return {'__singleton__': 'vools.functional.placeholder_impl:X'}

    def __setstate__(self, state):
        """Singleton: nothing to restore"""
        pass

    def __getattr__(self, name):
        """拦截属性访问，开始构建管道"""
        return PipeX(('attr', name))

    def __call__(self, *args, **kwargs):
        """拦截方法调用，开始构建管道"""
        return PipeX(('call', args, kwargs))

    def __getitem__(self, key):
        """拦截索引操作，开始构建管道"""
        if isinstance(key, tuple):
            return PipeX(('index', key))
        return PipeX(('index', (key,)))

    def do(self, f=print, pre_f=None, sub_f=None):
        """对自身应用副作用函数，返回 self 以支持链式调用。

        用于调试或日志输出，不改变管道本身。

        参数
        ----
        f: callable
            副作用函数，默认为 ``print``。
        pre_f: callable, optional
            预处理函数，在 ``f`` 之前作用于 self。
        sub_f: callable, optional
            后处理函数，在 ``f`` 之后作用于返回值（不期望返回）。

        返回
        ----
        _X
            返回自身，支持链式调用。

        示例
        ----
        ::

            X.strip().do(print).upper()['  hello  ']
            # 打印 _X 单例信息（调试目的）
            # 返回 'HELLO'
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self


class PipeX:
    """
    X 的管道执行器。

    记录操作序列，支持链式构建和延迟执行。管道中的每个操作以元组形式存储：
    ``(typ, *data)``。

    操作类型
    --------
    - ``('attr', name)`` — 属性访问
    - ``('call', args, kwargs)`` — 方法调用
    - ``('index', keys)`` — 索引操作
    - ``('map', func)`` — 结果映射

    终止方式
    --------
    - ``pipe[target]`` — 执行管道
    - ``pipe[target, idx...]`` — 执行管道并应用额外索引
    - ``pipe[None, idx...]`` — 追加索引操作（不终止，继续构建）
    - ``pipe.as_function()`` — 返回普通可调用函数
    """
    __slots__ = ('ops',)

    def __init__(self, op, prev=None):
        """
        初始化管道
        
        Args:
            op: 当前操作 (typ, *data)
            prev: 前一个 PipeX 实例（用于链式构建）
        """
        self.ops = (prev.ops + [op]) if prev else [op]

    def __getstate__(self):
        """Return serialization state"""
        return {'ops': self.ops}

    def __setstate__(self, state):
        """Restore from serialization state"""
        self.ops = state['ops']

    def __getattr__(self, name):
        """继续构建管道：属性访问"""
        return PipeX(('attr', name), self)

    def __call__(self, *args, **kwargs):
        """继续构建管道：方法调用"""
        return PipeX(('call', args, kwargs), self)

    def f(self, func):
        """
        添加结果映射函数
        
        在管道执行完成后，对结果应用此函数。
        
        Args:
            func: 映射函数，接收管道结果并返回转换后的值
        
        Returns:
            PipeX: 新的管道对象
        
        Example:
            X.split(',').f(list)['a,b,c']  # → ['a', 'b', 'c']
            X.split(',').f(lambda x: len(x))['a,b,c']  # → 3
        """
        if not callable(func):
            raise TypeError("f() argument must be callable")
        return PipeX(('map', func), self)

    def __getitem__(self, arg):
        """
        管道终止与执行
        
        **三种模式:**
        
        1. **构建模式**: [None, idx...]
           追加索引操作到管道，不执行
           Example: X.split(',')[None, 1]['a,b,c'] → 'b'
        
        2. **禁止**: [None]
           单独传入 None 会抛出 ValueError
        
        3. **执行模式**: [target] 或 [target, idx...]
           执行管道并返回结果
           Example: X.strip()['  hello  '] → 'hello'
           Example: X.split(',')['a,b,c', 1] → 'b'
        
        Args:
            arg: 目标对象，或 (target, idx1, idx2, ...) 元组
        
        Returns:
            管道执行结果
        
        Raises:
            ValueError: 空元组或单独 None
            RuntimeError: 未知操作类型
        """
        # 构建模式：[None, idx...] - 追加索引操作
        if isinstance(arg, tuple) and len(arg) > 1 and arg[0] is None:
            extra = arg[1:]
            return PipeX(('index', extra), self)

        # 禁止单独传入 None
        if arg is None:
            raise ValueError(
                "Cannot execute with target None. "
                "Use [None, idx] to add index operation to pipeline."
            )

        # 执行模式：[target] 或 [target, idx...]
        if isinstance(arg, tuple):
            if not arg:
                raise ValueError("Empty tuple not allowed")
            x, *extra = arg
        else:
            x, extra = arg, []

        # 执行管道所有操作
        result = x
        for typ, *data in self.ops:
            if typ == 'attr':
                result = getattr(result, data[0])
            elif typ == 'call':
                a, kw = data
                result = result(*a, **kw)
            elif typ == 'index':
                indices = data[0]
                result = result[indices[0]] if len(indices) == 1 else result[tuple(indices)]
            elif typ == 'map':
                result = data[0](result)
            else:
                raise RuntimeError(f"Unknown operation: {typ}")

        # 应用执行时携带的额外索引
        if extra:
            result = result[extra[0]] if len(extra) == 1 else result[tuple(extra)]
        return result
    
    def as_function(self):
        """
        终止管道，返回一个可直接调用的函数
        
        Returns:
            Callable: fn(x, f=None) - 接收目标对象和可选的映射函数
        
        Example:
            f = X.strip().as_function()
            f('  hello  ')  # → 'hello'
            
            f = X.split(',').as_function()
            f('a,b,c', f=list)  # → ['a', 'b', 'c']
        """
        ops = self.ops

        def execute(x, f=None):
            result = x
            for typ, *data in ops:
                if typ == 'attr':
                    result = getattr(result, data[0])
                elif typ == 'index':
                    indices = data[0]
                    result = result[indices[0]] if len(indices) == 1 else result[tuple(indices)]
                elif typ == 'call':
                    a, kw = data
                    result = result(*a, **kw)
                elif typ == 'map':
                    result = data[0](result)
                else:
                    raise RuntimeError(f"Unknown operation: {typ}")
            if f is not None:
                if not callable(f):
                    raise TypeError("'f' must be callable")
                result = f(result)
            return result

        return execute


# X 单例实例
X = _X()


class _Y:
    """
    Y 单例类 —— 使用关键字参数 ``exe=True`` 终止链式调用。

    Y 本身不执行任何操作，而是作为一个入口点：通过属性访问、方法调用或索引操作
    创建一个 ``PipeY`` 管道对象，记录一连串待执行的操作序列。

    核心用法
    --------
    - ``Y.attr`` → 返回 ``PipeY`` 管道对象
    - ``Y[key]`` → 返回 ``PipeY`` 管道对象（索引操作）
    - ``Y(*args, **kwargs)`` → 返回 ``PipeY`` 管道对象
    - ``pipe(target, exe=True)`` → 执行管道，返回结果

    管道操作
    --------
    - ``.attr`` — 属性访问
    - ``[key]`` — 索引操作
    - ``(*args, **kwargs)`` — 方法调用（非执行模式，即不含 ``exe=True``）
    - ``(target, exe=True)`` — 执行管道（终止操作）
    - ``(target, exe=True, f=factory)`` — 执行管道并应用工厂函数
    - ``.f(func)`` — 添加结果映射函数
    - ``.as_function()`` — 终止管道，返回普通函数 ``fn(x, f=None)``
    - ``.as_subscript()`` — 终止管道，返回下标执行器 ``[target]`` 或 ``[target, idx...]``
    - ``.do(f=print, pre_f=None, sub_f=None)`` — 副作用调试

    示例
    ----
    ::

        # 基础用法
        Y.strip()('  hello  ', exe=True)                # → 'hello'

        # 链式调用
        Y.strip().split(',')('a,b,c', exe=True)          # → ['a', 'b', 'c']

        # 带工厂函数
        Y.split(',')('a,b,c', exe=True, f=list)          # → ['a', 'b', 'c']

        # 转换为普通函数
        f = Y.strip().as_function()
        f('  hello  ')                                    # → 'hello'

        # 转换为下标执行器
        sub = Y.strip().as_subscript()
        sub['  hello  ']                                  # → 'hello'

    执行流程
    --------
    1. ``Y.attr`` / ``Y[...]`` / ``Y(...)`` 创建一个 ``PipeY``，记录第一个操作
    2. 继续 ``.attr`` / ``[...]`` / ``(...)`` / ``.f(func)`` 追加操作
    3. ``pipe(target, exe=True)`` 终止：从 target 开始，依次应用所有记录的操作
    4. 返回最终结果
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __getstate__(self):
        """Singleton: return module path reference"""
        return {'__singleton__': 'vools.functional.placeholder_impl:Y'}

    def __setstate__(self, state):
        """Singleton: nothing to restore"""
        pass

    def __getattr__(self, name):
        """拦截属性访问，开始构建管道"""
        return PipeY(('attr', name))

    def __getitem__(self, key):
        """拦截索引操作，开始构建管道"""
        return PipeY(('index', key))

    def __call__(self, *args, **kwargs):
        """拦截方法调用，开始构建管道"""
        return PipeY(('call', args, kwargs))

    def do(self, f=print, pre_f=None, sub_f=None):
        """对自身应用副作用函数，返回 self 以支持链式调用。

        用于调试或日志输出，不改变管道本身。

        参数
        ----
        f: callable
            副作用函数，默认为 ``print``。
        pre_f: callable, optional
            预处理函数，在 ``f`` 之前作用于 self。
        sub_f: callable, optional
            后处理函数，在 ``f`` 之后作用于返回值（不期望返回）。

        返回
        ----
        _Y
            返回自身，支持链式调用。
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self



class PipeY:
    """
    Y 的管道执行器。

    记录操作序列，支持链式构建和多种终止方式。

    操作类型
    --------
    - ``('attr', name)`` — 属性访问
    - ``('index', key)`` — 索引操作
    - ``('call', args, kwargs)`` — 方法调用
    - ``('map', func)`` — 结果映射

    终止方式
    --------
    - ``(target, exe=True)`` — 执行管道
    - ``(target, exe=True, f=factory)`` — 执行管道并转换结果
    - ``.as_function()`` — 返回普通函数 ``fn(x, f=None)``
    - ``.as_subscript()`` — 返回下标执行器 ``[target]`` 或 ``[target, idx...]``
    """
    __slots__ = ('ops',)

    def __init__(self, op, prev=None):
        """
        初始化管道
        
        Args:
            op: 当前操作 (typ, *data)
            prev: 前一个 PipeY 实例（用于链式构建）
        """
        self.ops = (prev.ops + [op]) if prev else [op]

    def __getstate__(self):
        """Return serialization state"""
        return {'ops': self.ops}

    def __setstate__(self, state):
        """Restore from serialization state"""
        self.ops = state['ops']

    def __getattr__(self, name):
        """继续构建管道：属性访问"""
        return PipeY(('attr', name), self)

    def __getitem__(self, key):
        """继续构建管道：索引操作"""
        return PipeY(('index', key), self)

    def __call__(self, *args, **kwargs):
        """
        管道构建或执行
        
        **构建模式**（默认）:
            添加调用操作到管道
            Example: Y.strip().split(',')
        
        **执行模式**（exe=True）:
            执行管道并返回结果
            Example: Y.strip()('  hello  ', exe=True)
            Example: Y.strip()('  hello  ', exe=True, f=list)
        
        Args:
            *args: 目标对象（执行模式）或方法参数（构建模式）
            **kwargs: 
                exe: True 表示执行模式
                f: 可选的工厂函数（执行模式）
        
        Returns:
            PipeY（构建模式）或执行结果（执行模式）
        
        Raises:
            TypeError: 参数数量错误或关键字参数错误
            RuntimeError: 未知操作类型
        """
        if kwargs.pop('exe', False):
            # 执行模式
            factory = kwargs.pop('f', None)
            if len(args) != 1:
                raise TypeError("Execution requires exactly one positional argument (the target)")
            if kwargs:
                raise TypeError(f"Unexpected keyword arguments: {kwargs}")

            result = args[0]
            for typ, *data in self.ops:
                if typ == 'attr':
                    result = getattr(result, data[0])
                elif typ == 'index':
                    result = result[data[0]]
                elif typ == 'call':
                    a, kw = data
                    result = result(*a, **kw)
                elif typ == 'map':
                    result = data[0](result)
                else:
                    raise RuntimeError(f"Unknown operation: {typ}")

            if factory is not None:
                if not callable(factory):
                    raise TypeError("'f' must be callable")
                result = factory(result)
            return result
        else:
            # 构建模式：添加调用操作
            return PipeY(('call', args, kwargs), self)

    def f(self, func):
        """
        添加结果映射函数
        
        在管道执行完成后，对结果应用此函数。
        
        Args:
            func: 映射函数
        
        Returns:
            PipeY: 新的管道对象
        
        Example:
            Y.split(',').f(list)('a,b,c', exe=True)  # → ['a', 'b', 'c']
        """
        if not callable(func):
            raise TypeError("f() argument must be callable")
        return PipeY(('map', func), self)

    def as_function(self):
        """
        冻结为普通函数
        
        Returns:
            Callable: fn(x, f=None) - 接收目标对象和可选的映射函数
        
        Example:
            f = Y.strip().as_function()
            f('  hello  ')  # → 'hello'
            
            f = Y.split(',').as_function()
            f('a,b,c', f=list)  # → ['a', 'b', 'c']
        """
        ops = self.ops

        def execute(x, f=None):
            result = x
            for typ, *data in ops:
                if typ == 'attr':
                    result = getattr(result, data[0])
                elif typ == 'index':
                    result = result[data[0]]
                elif typ == 'call':
                    a, kw = data
                    result = result(*a, **kw)
                elif typ == 'map':
                    result = data[0](result)
                else:
                    raise RuntimeError(f"Unknown operation: {typ}")
            if f is not None:
                if not callable(f):
                    raise TypeError("'f' must be callable")
                result = f(result)
            return result
        return execute

    def as_subscript(self):
        """
        返回下标执行器
        
        返回一个可通过 [target] 或 [target, idx...] 执行的对象。
        不支持关键字参数，工厂修正需提前通过 .f() 构建在管道内。
        
        Returns:
            SubscriptExecutor: 支持 [] 操作的执行器
        
        Example:
            sub = Y.strip().as_subscript()
            sub['  hello  ']  # → 'hello'
            
            sub = Y.split(',').as_subscript()
            sub['a,b,c', 1]  # → 'b'
        """
        ops = self.ops

        class SubscriptExecutor:
            def __getitem__(self_, arg):
                if isinstance(arg, tuple):
                    if not arg:
                        raise ValueError("Empty tuple not allowed")
                    x, *extra = arg
                else:
                    x, extra = arg, []

                result = x
                for typ, *data in ops:
                    if typ == 'attr':
                        result = getattr(result, data[0])
                    elif typ == 'index':
                        result = result[data[0]]
                    elif typ == 'call':
                        a, kw = data
                        result = result(*a, **kw)
                    elif typ == 'map':
                        result = data[0](result)
                    else:
                        raise RuntimeError(f"Unknown operation: {typ}")

                if extra:
                    result = result[extra[0]] if len(extra) == 1 else result[tuple(extra)]
                return result
            def do(self, f=print, pre_f=None, sub_f=None):
                """对自身应用副作用函数，返回 self 以支持链式调用。

                用于调试或日志输出，不改变执行器本身。

                参数
                ----
                f: callable
                    副作用函数，默认为 ``print``。
                pre_f: callable, optional
                    预处理函数，在 ``f`` 之前作用于 self。
                sub_f: callable, optional
                    后处理函数，在 ``f`` 之后作用于返回值（不期望返回）。

                返回
                ----
                SubscriptExecutor
                    返回自身，支持链式调用。
                """
                rs = self
                if pre_f:
                    rs = pre_f(rs)
                rs = f(rs)
                if sub_f:
                    sub_f(rs)
                return self


        return SubscriptExecutor()


# Y 单例实例
Y = _Y()

# ============================================================
# Z — 惰性表达式占位符系统
# ============================================================
#
# Z 提供编译时延迟绑定，将表达式树编译为可调用函数。
# 与 X/Y 的即时管道执行不同，Z 构建一棵表达式 AST 树，
# 再通过 as_function() 编译为普通 Python 函数。
#
# 核心特性：
#   - 属性访问：Z.attr
#   - 方法调用：Z(...) / Z.invoke(...)
#   - 索引操作：Z[key]
#   - *args/**kwargs 解包：Z.star / Z.kwstar
#   - 可变参数引用：Z.args_all / Z.kwargs_all
#   - pickle 序列化：pickle.dumps/loads
#   - JSON 序列化：expr_to_dict / expr_from_dict
# ============================================================

import pickle
import json


class Expr:
    """所有表达式节点的抽象基类。

    为所有节点提供统一的构建接口（``.attr`` / ``[key]`` / ``.invoke()`` / ``()``）
    和序列化框架（``__reduce__`` + ``__getstate__`` + ``__setstate__``）。

    子类必须实现
    ------------
    - ``evaluate(args, kwargs=None)`` — 求值，返回表达式结果
    - ``__getstate__()`` — 返回可序列化的纯数据结构（dict）
    - ``__setstate__(state)`` — 从纯数据结构重建节点

    内置方法
    --------
    - ``.attr`` → ``Attr(self, name)`` — 属性访问节点
    - ``[key]`` → ``GetItem(self, key)`` — 索引访问节点
    - ``(...)`` / ``.invoke(...)`` → ``Call(self, args, kwargs)`` — 调用节点
    - ``.as_function()`` → ``Callable`` — 编译表达式树为可调用函数
    """
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
    """编译后的参数占位符，对应第 ``n`` 个传入的位置实参。

    由 ``_compile()`` 自动生成，用户通常不直接创建。
    求值时直接返回 ``args[self.n]``。

    参数
    ----
    n: int
        位置参数索引（从 0 开始）。

    序列化
    ------
    状态格式：``{'__type__': 'Placeholder', 'n': int}``
    """
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
    """属性访问节点：``obj.name``。

    求值时先对 ``obj`` 求值，再调用 ``getattr(result, name)``。

    参数
    ----
    obj: Expr
        被访问属性的对象表达式节点。
    name: str
        属性名称。

    序列化
    ------
    状态格式：``{'__type__': 'Attr', 'obj': <递归序列化>, 'name': str}``
    """
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
    """函数调用节点：``func(*args, **kwargs)``。

    支持 ``*args`` / ``**kwargs`` 解包：
    - 若 ``args`` 中包含 ``StarArgs`` 节点，求值时将解包为位置参数
    - 若 ``args`` / ``kwargs`` 中包含 ``StarKwargs`` 节点，求值时将解包为关键字参数

    参数
    ----
    func: Expr
        被调用的函数表达式节点。
    args: tuple
        位置参数元组，可包含 ``Expr`` 节点和常量。
    kwargs: dict
        关键字参数字典，值可为 ``Expr`` 节点或常量。

    序列化
    ------
    状态格式：``{'__type__': 'Call', 'func': ..., 'args': [...], 'kwargs': {...}}``
    """
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
    """索引访问节点：``obj[key]``。

    求值时先对 ``obj`` 求值，再对 ``key``（若是 ``Expr``）求值，
    最后执行 ``result[key]``。

    参数
    ----
    obj: Expr
        被索引的对象表达式节点。
    key: Expr 或常量
        索引键，可以是表达式节点或字面量。

    序列化
    ------
    状态格式：``{'__type__': 'GetItem', 'obj': ..., 'key': ...}``
    """
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
    """``*args`` 解包节点，用于在 ``Call`` 节点中解包位置参数。

    通过 ``Z.star`` 创建：``Z.invoke(1, 2, Z.star)`` 会将第三个位置参数解包为多个实参。

    参数
    ----
    expr: Expr
        求值后应返回可迭代对象的表达式。

    序列化
    ------
    状态格式：``{'__type__': 'StarArgs', 'expr': ...}``
    """
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
    """``**kwargs`` 解包节点，用于在 ``Call`` 节点中解包关键字参数。

    通过 ``Z.kwstar`` 创建：``Z.invoke(kw=Z.kwstar)`` 会将关键字参数解包为多个具名实参。

    参数
    ----
    expr: Expr
        求值后应返回字典的表达式。

    序列化
    ------
    状态格式：``{'__type__': 'StarKwargs', 'expr': ...}``
    """
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
    """代表函数的可变位置参数元组 ``*args``。

    通过 ``Z.args_all`` 获取。求值时返回编译后函数的整个 ``args`` 元组。
    支持索引访问 ``Z.args_all[i]`` 来获取特定位置的参数。

    序列化
    ------
    状态格式：``{'__type__': 'RestArgs'}``
    """
    def __getitem__(self, i):
        return GetItem(self, i)

    def evaluate(self, args, kwargs=None):
        return args

    def __getstate__(self):
        return {'__type__': 'RestArgs'}

    def __setstate__(self, state):
        pass


class RestKwargs(Expr):
    """代表函数的可变关键字参数字典 ``**kwargs``。

    通过 ``Z.kwargs_all`` 获取。求值时返回编译后函数的整个 ``kwargs`` 字典。

    序列化
    ------
    状态格式：``{'__type__': 'RestKwargs'}``
    """
    def evaluate(self, args, kwargs=None):
        return kwargs or {}

    def __getstate__(self):
        return {'__type__': 'RestKwargs'}

    def __setstate__(self, state):
        pass


class _Auto(Expr):
    """待编号的占位符 —— 用户入口 ``Z`` 的类。

    在编译（``make_func`` / ``as_function``）时，所有 ``_Auto`` 节点被深度优先遍历替换为
    带编号的 ``Placeholder(n)`` 节点。每个 ``Z`` 出现对应一个唯一的参数位置。

    属性
    ----
    star: StarArgs
        ``*args`` 解包占位符，用于 ``Z.invoke(1, Z.star)``。
    kwstar: StarKwargs
        ``**kwargs`` 解包占位符，用于 ``Z.invoke(kw=Z.kwstar)``。
    args_all: RestArgs
        代表整个 ``*args`` 元组，编译后函数签名变为 ``def f(*args, **kwargs)``。
    kwargs_all: RestKwargs
        代表整个 ``**kwargs`` 字典。

    注意
    ----
    属性名以 ``_`` 开头会正常抛 ``AttributeError``，避免与内部属性冲突。
    直接对未编译的 ``_Auto`` 调用 ``evaluate()`` 会抛出 ``RuntimeError``。

    序列化
    ------
    状态格式：``{'__type__': '_Auto'}``，反序列化时返回 ``Z`` 单例。
    """
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
    """将表达式节点或常量序列化为可存储的纯数据结构。

    - ``Expr`` 节点 → 调用其 ``__getstate__()`` 返回的 dict（含 ``__type__`` 标识）
    - 常量（非 ``Expr``） → 原值返回

    参数
    ----
    value: Expr 或 任意常量
        待序列化的值。

    返回
    ----
    dict 或 原值
        可 JSON 序列化的纯数据结构，或原常量。
    """
    if isinstance(value, Expr):
        return value.__getstate__()
    return value


def _deserialize(value):
    """从纯数据结构重建表达式节点或返回常量。

    根据 ``__type__`` 字段分派到对应的节点类，使用 ``object.__new__`` + ``__setstate__`` 重建。
    若值不含 ``__type__``，则原样返回（作为常量）。

    支持的节点类型
    --------------
    Placeholder, Attr, Call, GetItem, StarArgs, StarKwargs, RestArgs, RestKwargs, _Auto

    参数
    ----
    value: dict 或 任意常量
        待反序列化的数据结构。

    返回
    ----
    Expr 或 原值
        重建的表达式节点，或原常量。

    异常
    ----
    ValueError
        当 ``__type__`` 为未知节点类型时抛出。
    """
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
    """将表达式树序列化为纯 ``dict`` 结构（可 JSON 序列化）。

    递归序列化整棵表达式树，所有 ``Expr`` 节点转为含 ``__type__`` 的 dict，
    常量保持原值。结果可直接传给 ``json.dumps()``。

    参数
    ----
    expr: Expr
        待序列化的表达式节点（通常是 ``Z.xxx`` 构建的树）。

    返回
    ----
    dict
        可 JSON 序列化的纯数据字典。

    示例
    ----
    ::

        d = expr_to_dict(Z.strip().upper())
        json_str = json.dumps(d)
        restored = expr_from_dict(json.loads(json_str))
        f = restored.as_function()
        f('  hello  ')  # → 'HELLO'
    """
    return _serialize(expr)


def expr_from_dict(value):
    """从纯 ``dict`` 结构重建表达式树。

    ``expr_to_dict()`` 的逆操作，将 JSON 反序列化后的 dict 重建为可编译执行的表达式树。

    参数
    ----
    value: dict
        由 ``expr_to_dict()`` 产生的（或 JSON 反序列化后的）纯数据字典。

    返回
    ----
    Expr
        重建的表达式节点，可调用 ``.as_function()`` 编译执行。

    异常
    ----
    ValueError
        当 ``__type__`` 为未知节点类型时抛出。
    """
    return _deserialize(value)


# ---- 编译与求值 ----

def _compile(expr):
    """编译表达式树：深度优先遍历，将所有 ``_Auto`` 节点替换为带序号的 ``Placeholder``。

    同时记录是否包含 ``RestArgs`` / ``RestKwargs``（决定最终函数是否为可变参数形式）。

    参数
    ----
    expr: Expr
        未编译的表达式树根节点。

    返回
    ----
    tuple
        ``(编译后的树, 固定参数个数, 是否可变参数)``
        - ``compiled`` — 编译后的 ``Expr`` 树（不含 ``_Auto`` 节点）
        - ``arity`` — ``Z`` 出现次数（固定位置参数个数）
        - ``has_rest`` — 是否包含 ``RestArgs`` / ``RestKwargs``
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
    """编译表达式树，返回一个可直接调用的 Python 函数。

    函数签名由表达式内容决定：

    - **含 ``args_all`` / ``kwargs_all``**：``def f(*args, **kwargs)``
    - **否则**：``def f(*args)``，需要固定数量的位置参数（等于 ``Z`` 出现次数）

    参数
    ----
    expr: Expr
        未编译的表达式树根节点。

    返回
    ----
    Callable
        编译后的函数。

    异常
    ----
    TypeError
        固定参数模式下，传入参数数量不匹配时抛出。

    示例
    ----
    ::

        # 固定参数
        f = make_func(Z.strip().upper())
        f('  hello  ')  # → 'HELLO'

        # 可变参数
        g = make_func(Z.args_all[0] + Z.args_all[1])
        g(1, 2)        # → 3
        g(1, 2, 3)     # → 3（忽略多余参数）
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


