"""
rself 类装饰器 - 支持自定义初始化的增强版本

核心功能：
1. 限制继承方式为最多单继承或不继承
2. 方法返回值处理：
   - 返回 None → 返回自身实例
   - 返回父类实例 → 转换为子类实例
3. 自定义初始化支持：
   - 定义 __from_parent__ 类方法来自定义转换逻辑
   - 支持传递额外参数（kwargs）
   - 自动保存和恢复实例属性

解决场景：
当创建如 class SuperText(str) 的子类时，调用 s.upper() 返回的是 str 类型，
使用 @rself 装饰后，会自动返回 SuperText 类型，支持继续链式调用扩展方法。
"""

import functools
import inspect
from typing import Any, Type, Optional, Dict

__all__ = ['rself']


def rself(cls: Type) -> Type:
    """
    类装饰器：实现链式调用支持

    功能：
    1. 限制继承方式为最多单继承或不继承
    2. 拦截非魔法方法、属性、类方法、静态方法
    3. 返回值处理：
       - None → 返回自身实例
       - 父类实例 → 转换为子类实例
    4. 自定义初始化支持：
       - 若类定义了 __from_parent__ 类方法，使用该方法进行转换
       - 否则使用默认的 cls(value) 方式
       - 自动保存和恢复实例属性

    不影响：
    - 魔法方法（如 __init__、__getattr__ 等）
    - 下划线开头的成员
    """
    # 类型检查
    if not inspect.isclass(cls):
        raise TypeError(f"@rself 装饰器仅允许应用于类，当前类型为: {type(cls).__name__}")

    # 1. 检查继承关系，只允许单继承（排除 object）
    bases = [b for b in cls.__bases__ if b is not object]
    if len(bases) > 1:
        # 检查是否有自定义元类（使用 metaclass=xxx）
        if cls.__class__ is not type:
            # 如果有自定义元类，允许继承自一个类（其他可能是元类相关）
            # 检查是否只有一个非 object 的实际父类
            actual_bases = [b for b in bases if not isinstance(b, type)]
            if len(actual_bases) <= 1:
                bases = actual_bases
            else:
                raise TypeError(
                    f"@rself 仅支持单继承或不继承，当前类 {cls.__name__} 继承了 {len(bases)} 个父类: {bases}"
                )
        else:
            raise TypeError(
                f"@rself 仅支持单继承或不继承，当前类 {cls.__name__} 继承了 {len(bases)} 个父类: {bases}"
            )
    parent_cls = bases[0] if bases else None

    # 检查是否定义了 __from_parent__ 方法
    has_from_parent = callable(getattr(cls, '__from_parent__', None))

    # 保存原有的 __getattr__（如果有）
    original_getattr = cls.__dict__.get('__getattr__', None)

    def _wrap_return_value(self, value: Any):
        """
        应用返回值转换规则：
        - None → 返回 self
        - 已经是当前类或其子类的实例 → 直接返回原值
        - 父类实例 → 使用 __from_parent__ 或 cls(value) 转换

        支持自定义初始化，通过 __from_parent__ 方法或实例属性传递参数
        """
        if value is None:
            return self

        if isinstance(value, cls):
            return value

        # 检查是否是当前类或其任何祖先类的实例
        # 用于处理继承链的情况
        if parent_cls is not None:
            for base in cls.__mro__:
                if base is object:
                    break
                if isinstance(value, base):
                    # 找到匹配的基类，使用该基类的转换逻辑
                    # 尝试从实例属性获取初始化参数
                    kwargs = {}
                    try:
                        kwargs_attr = object.__getattribute__(self, '_rself_kwargs')
                        kwargs = dict(kwargs_attr) if kwargs_attr else {}
                    except AttributeError:
                        pass

                    # 优先使用 __from_parent__ 类方法
                    if has_from_parent:
                        try:
                            # 调用类的 __from_parent__ 方法
                            result = cls.__from_parent__(value, **kwargs)
                            return result
                        except TypeError:
                            # 如果 __from_parent__ 不接受 kwargs，尝试无参数调用
                            try:
                                result = cls.__from_parent__(value)
                                return result
                            except Exception:
                                pass

                    # 使用默认的 cls(value) 方式
                    try:
                        return cls(value)
                    except TypeError:
                        # 如果构造函数需要额外参数但没有 __from_parent__，抛出错误
                        if kwargs:
                            raise TypeError(
                                f"类 {cls.__name__} 的构造函数不支持直接用父类实例初始化，"
                                f"请定义 __from_parent__(cls, parent_val, **kwargs) 类方法来处理"
                            )
                        raise

        return value

    def __getattribute__(self, name: str):
        # 先通过标准途径获取属性值
        try:
            attr = object.__getattribute__(self, name)
        except AttributeError:
            if original_getattr is not None:
                attr = original_getattr(self, name)
            else:
                raise

        # 过滤：魔法方法(__xx__) 或下划线开头(_) 的成员直接返回原值
        if name.startswith('_') and not (name.startswith('__') and name.endswith('__')):
            return attr
        if name.startswith('__') and name.endswith('__'):
            return attr

        # 获取属性在类中的原始定义（用于区分 property / classmethod / staticmethod）
        attr_def = None
        for base in type(self).__mro__:
            if name in base.__dict__:
                attr_def = base.__dict__[name]
                break

        # 如果是 property，已经通过 getter 获得值，直接处理返回值
        if isinstance(attr_def, property):
            return _wrap_return_value(self, attr)

        # 如果是可调用对象（方法、类方法、静态方法、动态生成的函数）
        if callable(attr) and not isinstance(attr_def, property):
            @functools.wraps(attr)
            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                return _wrap_return_value(self, result)
            return wrapper

        # 其他普通属性直接返回
        return attr

    # 保存原始 __init__ 和 __new__ 方法
    original_init = cls.__dict__.get('__init__')
    original_new = cls.__dict__.get('__new__')

    # 不可变类型列表，这些类型需要特殊的 __new__ 处理
    _IMMUTABLE_TYPES = (str, int, float, bool, tuple, bytes, frozenset)

    def _wrap_new(cls, *args, **kwargs):
        """包装后的 __new__，保存初始化参数"""
        # 从 kwargs 中提取父类构造所需的参数
        # 对于 str 子类，第一个参数是 value
        if args:
            parent_value = args[0]
        else:
            parent_value = kwargs.pop('value', '')

        # 存储 kwargs 用于后续的 __from_parent__ 调用
        # 注意：保留原始 kwargs 因为子类可能需要这些参数
        stored_kwargs = kwargs.copy() if kwargs else {}

        # 创建实例 - 对于不可变类型，必须使用父类的 __new__
        if original_new is not None:
            # 调用原始 __new__，保留所有参数
            instance = original_new(cls, *args, **kwargs)
        elif parent_cls is not None and isinstance(parent_cls, _IMMUTABLE_TYPES):
            # 对于不可变类型的子类，使用父类的 __new__
            instance = parent_cls.__new__(cls, parent_value)
        else:
            # 对于可变类型或没有父类的情况，使用 object.__new__
            instance = object.__new__(cls)

        # 存储 kwargs 作为实例属性，用于 __from_parent__ 调用
        instance._rself_kwargs = stored_kwargs

        return instance

    def _wrap_init(self, *args, **kwargs):
        """包装后的 __init__，保存初始化参数"""
        # 将初始化参数存储为实例属性
        # 注意：对于不可变类型，__new__ 已经处理了 kwargs
        if not hasattr(self, '_rself_kwargs'):
            self._rself_kwargs = kwargs.copy() if kwargs else {}

        # 调用原始 __init__
        if original_init is not None:
            original_init(self, *args, **kwargs)

    # 如果类有自定义 __new__，替换为包装版本
    if original_new is not None and original_new is not _wrap_new:
        cls.__new__ = staticmethod(lambda cls, *args, **kwargs: _wrap_new(cls, *args, **kwargs))
    elif original_new is None and parent_cls is not None and isinstance(parent_cls, _IMMUTABLE_TYPES):
        # 仅对不可变类型的子类添加 __new__ 包装
        cls.__new__ = staticmethod(lambda cls, *args, **kwargs: _wrap_new(cls, *args, **kwargs))

    # 如果类有自定义 __init__，替换为包装版本
    if original_init is not None and '__init__' not in cls.__dict__:
        cls.__init__ = _wrap_init
    elif original_init is not None and original_init is not _wrap_init:
        cls.__init__ = _wrap_init

    # 注入新方法
    cls.__getattribute__ = __getattribute__
    return cls


# ========== 示例和测试 ==========
if __name__ == "__main__":
    @rself
    class SuperText(str):
        """扩展的字符串类，支持链式调用自定义方法"""
        def __init__(self, value: str = "", extra: str = None):
            # str 是不可变类型，初始化时需调用父类 __new__
            super().__init__()
            self._value = value
            self._extra = extra

        @property
        def extra(self):
            return self._extra

        def set_extra(self, extra: str):
            """设置额外参数"""
            self._extra = extra


        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function
                sub_f: Post-processing function (no return value expected)

            Returns:
                self, for chaining
            """
            rs = self
            if pre_f:
                rs = pre_f(rs)
            rs = f(rs)
            if sub_f:
                sub_f(rs)
            return self

        def decorated(self):
            """自定义方法：返回带前缀并重复的字符串"""
            prefix = self._extra or ""
            return prefix + self._value

    @rself
    class SuperTextWithFactory(str):
        """使用 __from_parent__ 的字符串类"""
        def __new__(cls, value: str = "", prefix: str = "", suffix: str = ""):
            instance = super().__new__(cls, value)
            instance._prefix = prefix
            instance._suffix = suffix
            return instance

        @classmethod
        def __from_parent__(cls, parent_val, **kwargs):
            """自定义工厂方法，支持传递额外参数"""
            prefix = kwargs.get('prefix', '>> ')
            suffix = kwargs.get('suffix', '')
            return cls(str(parent_val), prefix=prefix, suffix=suffix)


        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function
                sub_f: Post-processing function (no return value expected)

            Returns:
                self, for chaining
            """
            rs = self
            if pre_f:
                rs = pre_f(rs)
            rs = f(rs)
            if sub_f:
                sub_f(rs)
            return self

        def with_affix(self):
            """返回带前后缀的字符串"""
            return self._prefix + str(self) + self._suffix

    @rself
    class SuperList(list):
        """增强版列表类，支持链式调用"""

        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function
                sub_f: Post-processing function (no return value expected)

            Returns:
                self, for chaining
            """
            rs = self
            if pre_f:
                rs = pre_f(rs)
            rs = f(rs)
            if sub_f:
                sub_f(rs)
            return self

        def add(self, item):
            new_list = SuperList(self)
            new_list.append(item)
            return new_list

    @rself
    class NoInheritance:
        """无继承的类"""
        def __init__(self):
            self.value = 0


        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function
                sub_f: Post-processing function (no return value expected)

            Returns:
                self, for chaining
            """
            rs = self
            if pre_f:
                rs = pre_f(rs)
            rs = f(rs)
            if sub_f:
                sub_f(rs)
            return self

        def increment(self):
            self.value += 1

    # ----- 测试 SuperText -----
    print("=== 测试 SuperText ===")
    s = SuperText("hello")

    # 1. 父类方法返回 str 实例 → 自动转为 SuperText 实例
    result = s.upper()
    print(f"type(s.upper()) = {type(result).__name__}, value = '{result}'")
    assert isinstance(result, SuperText), "s.upper() 应该返回 SuperText 类型"

    # set_times() 返回 None → 返回自身
    result2 = result.set_extra("prefix:")
    print(f"type(result.set_extra()) = {type(result2).__name__}")
    assert result2 is result, "set_extra() 应该返回自身"

    # 2. 自定义方法返回 str → 也会被包装
    d = s.decorated()
    print(f"type(s.decorated()) = {type(d).__name__}, value = '{d}'")
    assert isinstance(d, SuperText), "decorated() 应该返回 SuperText 类型"

    # ----- 测试 SuperTextWithFactory -----
    print("\n=== 测试 SuperTextWithFactory ===")
    s2 = SuperTextWithFactory("hello", prefix=">> ", suffix=" <<")

    # 链式调用继承方法
    result = s2.upper()
    print(f"type(s2.upper()) = {type(result).__name__}, value = '{result}'")
    assert isinstance(result, SuperTextWithFactory), "upper() 应该返回 SuperTextWithFactory 类型"

    # 链式调用自定义方法
    result2 = result.with_affix()
    print(f"type(s2.with_affix()) = {type(result2).__name__}, value = '{result2}'")
    assert isinstance(result2, SuperTextWithFactory), "with_affix() 应该返回 SuperTextWithFactory 类型"

    # ----- 测试 SuperList -----
    print("\n=== 测试 SuperList ===")
    lst = SuperList([1, 2, 3])
    result = lst.add(4)
    print(f"type(lst.add(4)) = {type(result).__name__}, value = {result}")
    assert isinstance(result, SuperList), "add() 应该返回 SuperList 类型"

    # 链式调用
    chained_list = SuperList([1, 2]).add(3).add(4)
    print(f"链式调用结果: {chained_list}")
    assert isinstance(chained_list, SuperList)

    # ----- 测试 NoInheritance -----
    print("\n=== 测试 NoInheritance ===")
    obj = NoInheritance()
    result = obj.increment()
    print(f"type(obj.increment()) = {type(result).__name__}")
    assert result is obj, "increment() 应该返回自身"
    assert obj.value == 1

    # ----- 测试多继承错误 -----
    print("\n=== 测试多继承限制 ===")
    try:
        @rself
        class MultiInherit(str, list):
            pass
        print("[FAIL] 应该抛出错误")
    except TypeError as e:
        print(f"[OK] 正确抛出错误: {e}")

    print("\n所有测试通过!")