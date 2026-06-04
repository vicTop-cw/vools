"""
rself 类装饰器 - 最终版本

核心功能：
1. 限制继承方式为最多单继承或不继承
2. 方法返回值处理：
   - 返回 None → 返回自身实例
   - 返回父类实例 → 转换为子类实例
   - 其他情况保持原返回值

解决场景：
当创建如 class SuperText(str) 的子类时，调用 s.upper() 返回的是 str 类型，
使用 @rself 装饰后，会自动返回 SuperText 类型，支持继续链式调用扩展方法。
"""

import functools
import inspect
from typing import Any, Type

__all__ = ['rself']

def rself(cls: Type) -> Type:
    """
    类装饰器：实现链式调用支持

    功能：
    1. 限制继承方式为最多单继承或不继承
    2. 拦截非魔法方法、属性、类方法、静态方法
    3. 返回值处理：
       - None → 返回自身实例
       - 父类实例 → 转换为子类实例返回
       - 其他 → 保持原返回值

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
        raise TypeError(
            f"@rself 仅支持单继承或不继承，当前类 {cls.__name__} 继承了 {len(bases)} 个父类: {bases}"
        )
    parent_cls = bases[0] if bases else None

    # 保存原有的 __getattr__（如果有）
    original_getattr = cls.__dict__.get('__getattr__', None)

    def _wrap_return_value(self, value: Any):
        """
        应用返回值转换规则：
        - None → 返回 self
        - 父类实例 → 返回子类实例（用子类重新包装）
        """
        if value is None:
            return self
        if parent_cls is not None and isinstance(value, parent_cls):
            try:
                return cls(value)
            except Exception:
                return value
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
        if name.startswith('_'):
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

    # 注入新方法
    cls.__getattribute__ = __getattribute__
    return cls


# ========== 示例和测试 ==========
if __name__ == "__main__":
    @rself
    class SuperText(str):
        """扩展的字符串类，支持链式调用自定义方法"""
        def __init__(self, value: str = ""):
            # str 是不可变类型，初始化时需调用父类 __new__
            super().__init__()
            self._times = 1          # 自定义属性：重复次数
            self._prefix = ">> "     # 自定义属性：前缀

        @property
        def times(self):
            return self._times

        def set_times(self, n: int):
            self._times = n

        def set_prefix(self, prefix: str):
            self._prefix = prefix

        def decorated(self):
            """自定义方法：返回带前缀并重复的字符串"""
            return self._prefix + (self * self._times)

    @rself
    class SuperList(list):
        """增强版列表类，支持链式调用"""
        def add(self, item):
            new_list = SuperList(self)
            new_list.append(item)
            return new_list

    @rself
    class NoInheritance:
        """无继承的类"""
        def __init__(self):
            self.value = 0

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
    # 注意：upper() 返回新实例，所以 set_times() 返回的是新实例，不是原始的 s
    result2 = result.set_times(3)
    print(f"type(result.set_times(3)) = {type(result2).__name__}")
    assert result2 is result, "set_times() 应该返回新实例"

    # 使用同一个实例链式调用
    s2 = SuperText("hello")
    result3 = s2.set_times(3)
    print(f"s2.set_times(3) is s2 = {result3 is s2}")
    assert result3 is s2, "set_times() 应该返回自身"

    # 2. 自定义方法返回 str → 也会被包装
    d = s.decorated()
    print(f"type(s.decorated()) = {type(d).__name__}, value = '{d}'")
    assert isinstance(d, SuperText), "decorated() 应该返回 SuperText 类型"

    # 3. 链式调用
    chained = SuperText("hello").upper().set_prefix("## ").decorated()
    print(f"链式调用结果: '{chained}'")
    assert isinstance(chained, SuperText), "链式调用应该返回 SuperText 类型"

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