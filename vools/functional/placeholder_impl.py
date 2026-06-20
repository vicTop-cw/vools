"""
函数式编程占位符工具 - X 和 Y

提供强大的函数式编程能力，支持多种操作模式：

**核心特性:**

1. **X - 方括号终止模式**
   - 使用 `[]` 终止链式调用并执行
   - 支持 `[target]` 或 `[target, idx...]` 格式
   - 支持 `[None, idx...]` 追加索引操作

2. **Y - 关键字参数终止模式**
   - 使用 `(target, exe=True)` 终止链式调用并执行
   - 支持 `(target, exe=True, f=factory)` 工厂函数转换
   - 支持 `as_function()` 和 `as_subscript()` 方法

3. **通用特性**
   - 属性访问: `.attr`
   - 方法调用: `(*args, **kwargs)`
   - 索引操作: `[key]`
   - 函数反转: `.f(func)`
   - 链式调用: 任意顺序组合

**设计理念:**
- 构建时不报错，执行时才检查类型
- 延迟执行，支持复杂管道构建
- 简洁的操作序列记录模式

**导出:**
    X, Y - 单例占位符实例

**示例:**

# X 的基本用法
X.strip()['  hello  ']                    # → 'hello'
X.strip().split(',')['a,b,c']             # → ['a', 'b', 'c']
X.split(',')[None, 1]['a,b,c']            # → 'b'
X.split(',')['a,b,c', 1]                  # → 'b'
X.split(',').f(list)['a,b,c']             # → ['a', 'b', 'c']

# Y 的基本用法
Y.strip()('  hello  ', exe=True)          # → 'hello'
Y.strip().split(',')('a,b,c', exe=True)   # → ['a', 'b', 'c']
Y.split(',')('a,b,c', exe=True, f=list)  # → ['a', 'b', 'c']
Y.strip().as_function()('  hello  ')      # → 'hello'
Y.strip().as_subscript()['  hello  ']     # → 'hello'

# 索引操作
X[0]['hello']                             # → 'h'
X['name'][{'name': 'Alice'}]              # → 'Alice'
Y[0]['hello', exe=True]                   # → 'h'

# 链式组合
X.strip().upper()['  hello  ']            # → 'HELLO'
X.split(',')[None, 0].upper()['a,b,c']    # → 'A'
"""

from typing import Any, Callable, Optional

__all__ = ['X', 'Y']


class _X:
    """
    X 单例类 - 使用方括号 [] 终止链式调用
    
    **核心用法:**
        X.attr → 返回 PipeX 管道对象
        X(*args, **kwargs) → 返回 PipeX 管道对象
        X[key] → 返回 PipeX 管道对象（索引操作）
        X.attr[...] → 执行管道，返回结果
    
    **管道操作:**
        .attr - 属性访问
        (*args, **kwargs) - 方法调用
        [None, idx...] - 追加索引操作（不执行）
        [target] - 执行管道
        [target, idx...] - 执行管道并应用额外索引
        .f(func) - 添加结果映射函数
        .as_function() - 返回普通函数
    
    **示例:**
        # 基础用法
        X.strip()['  hello  ']  # → 'hello'
        
        # 链式调用
        X.strip().split(',')['a,b,c']  # → ['a', 'b', 'c']
        
        # 追加索引（构建模式）
        X.split(',')[None, 1]['a,b,c']  # → 'b'
        
        # 执行时索引
        X.split(',')['a,b,c', 1]  # → 'b'
        
        # 函数映射
        X.split(',').f(list)['a,b,c']  # → ['a', 'b', 'c']
        
        # 转换为普通函数
        f = X.strip().as_function()
        f('  hello  ')  # → 'hello'
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


class PipeX:
    """
    X 的管道执行器
    
    记录操作序列，支持链式构建和延迟执行。
    
    **操作类型:**
        - ('attr', name) - 属性访问
        - ('call', args, kwargs) - 方法调用
        - ('index', keys) - 索引操作
        - ('map', func) - 结果映射
    
    **执行方式:**
        - 通过 __getitem__ 触发执行
        - 通过 as_function() 转换为普通函数
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
    Y 单例类 - 使用关键字参数终止链式调用
    
    **核心用法:**
        Y.attr → 返回 PipeY 管道对象
        Y[key] → 返回 PipeY 管道对象（索引操作）
        Y(*args, **kwargs) → 返回 PipeY 管道对象
        Y.attr(target, exe=True) → 执行管道，返回结果
    
    **管道操作:**
        .attr - 属性访问
        [key] - 索引操作
        (*args, **kwargs) - 方法调用（非执行模式）
        (*target, exe=True) - 执行管道
        (*target, exe=True, f=factory) - 执行管道并应用工厂函数
        .f(func) - 添加结果映射函数
        .as_function() - 返回普通函数 fn(x, f=None)
        .as_subscript() - 返回下标执行器 [target]
    
    **示例:**
        # 基础用法
        Y.strip()('  hello  ', exe=True)  # → 'hello'
        
        # 链式调用
        Y.strip().split(',')('a,b,c', exe=True)  # → ['a', 'b', 'c']
        
        # 带工厂函数
        Y.split(',')('a,b,c', exe=True, f=list)  # → ['a', 'b', 'c']
        
        # 转换为普通函数
        f = Y.strip().as_function()
        f('  hello  ')  # → 'hello'
        
        # 转换为下标执行器
        sub = Y.strip().as_subscript()
        sub['  hello  ']  # → 'hello'
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


class PipeY:
    """
    Y 的管道执行器
    
    记录操作序列，支持链式构建和多种终止方式。
    
    **操作类型:**
        - ('attr', name) - 属性访问
        - ('index', key) - 索引操作
        - ('call', args, kwargs) - 方法调用
        - ('map', func) - 结果映射
    
    **终止方式:**
        - (target, exe=True) - 执行管道
        - (target, exe=True, f=factory) - 执行管道并转换结果
        - as_function() - 返回普通函数
        - as_subscript() - 返回下标执行器
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

        return SubscriptExecutor()


# Y 单例实例
Y = _Y()
