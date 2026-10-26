"""
核心基础类
"""

__all__ = ['VoolsBase', '_validate_type', '_ensure_callable']

from functools import wraps as _wraps


import copy as _copy_mod
import collections.abc as _abc
from typing import Any


def _is_opaque(value: Any) -> bool:
    """判断值是否"无有意义相等语义"（函数/生成器/迭代器等）——BUG-415。"""
    return callable(value) or isinstance(value, (_abc.Generator, _abc.Iterator))


def _state_of(obj: Any) -> dict:
    """收集实例状态：``__dict__`` + 沿 MRO 的 ``__slots__``——BUG-415。

    原实现只看 ``self.__dict__``：`Seq`/`VList`/`Table` 的数据存放在
    ``__slots__``（`_collection` 等）里，导致 ``Seq([1,2]) == Seq([1,3])``
    返回 **True**（两者 ``__dict__`` 都只含操作管道）。
    """
    state = {}
    for cls in type(obj).__mro__:
        slots = cls.__dict__.get('__slots__', ())
        if isinstance(slots, str):
            slots = (slots,)
        for name in slots:
            try:
                state[name] = getattr(obj, name)
            except AttributeError:
                pass
    state.update(getattr(obj, '__dict__', {}))
    return state


class VoolsBase:
    """vools 基础类，提供通用方法和属性"""

    def __repr__(self):
        return f"<{self.__class__.__name__}>"

    def __str__(self):
        return self.__repr__()

    def __eq__(self, other):
        # BUG-415: 原实现只比较 __dict__，忽略 __slots__ 中的数据——Seq 等
        # 数据容器因此"不同内容判相等"；且状态里的 lambda/生成器按身份比较
        # 又会让"相同内容判不等"。现：类型必须一致 + 合并 slots/__dict__ 状态，
        # 逐项比较，跳过无相等语义的 opaque 值。
        # BUG-416: 递归比较需带循环检测（见 _vools_eq）。
        if self is other:
            return True
        if type(self) is not type(other):
            return False
        return self._vools_eq(other, {})
    def _vools_eq(self, other: Any, seen: dict) -> bool:
        """带循环检测的相等比较（BUG-416）。

        状态中的对象互相引用时，递归比较会无限展开；原实现靠
        RecursionError 被 except 吞掉返回 NotImplemented，导致结构相同的
        循环对象被判为 **False**。这里对 (self, other) 配对记账：
        重复出现同一对即视为已比较（相等），既保证终止又不至于误判。
        """
        key = (id(self), id(other))
        if key in seen:
            return seen[key]
        seen[key] = True
        mine, theirs = _state_of(self), _state_of(other)
        if mine.keys() != theirs.keys():
            seen[key] = False
            return False
        for key_name in mine:
            va, vb = mine[key_name], theirs[key_name]
            if va is vb:
                continue
            if _is_opaque(va) or _is_opaque(vb):
                continue
            if isinstance(va, VoolsBase) and isinstance(vb, VoolsBase):
                if not va._vools_eq(vb, seen):
                    seen[key] = False
                    return False
                continue
            try:
                if va != vb:
                    seen[key] = False
                    return False
            except Exception:
                seen[key] = False
                return False
        return True

    def __hash__(self):
        # BUG-415: 原实现 hash(tuple(sorted(self.__dict__.items()))) 对含
        # list/dict 的状态直接抛 "TypeError: unhashable type: 'list'"（信息
        # 完全指不到对象本身）。内容可变的对象本就不应可哈希，这里给出明确
        # 错误；需要哈希请按业务定义不可变键。
        raise TypeError(
            f"{type(self).__name__} 的内容可变，不支持 hash（如需字典键请"
            f"使用不可变字段组合或 id()）")

    def to_dict(self):
        """转换为字典"""
        result = {}
        for key, value in self.__dict__.items():
            if not key.startswith('_'):
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data):
        """从字典创建对象（BUG-417）。

        原实现 ``cls(**data)`` 对两类常见情况都不友好：

        * ``Seq.from_dict({})`` → 静默得到**空 Seq**（数据被丢弃却毫无提示）；
        * ``Seq.from_dict({'x': 1})`` → TypeError: unexpected keyword argument 'x'
          （看不出是"类不接受该键"）；
        * ``Encryptor.from_dict({})`` → missing 1 required positional argument
          'data'（看不出与 from_dict 的关联）。

        现：data 必须是 dict；优先 ``cls(**data)``；失败后退化为
        "默认构造 + 逐键赋值"（仅限类已有/已有 slot 的属性）；两者都不可行时
        抛带类名的 TypeError。
        """
        if not isinstance(data, dict):
            raise TypeError(
                f"{cls.__name__}.from_dict 需要 dict，收到 "
                f"{type(data).__name__}: {data!r}")
        try:
            return cls(**data)
        except TypeError:
            pass
        try:
            obj = cls()
        except Exception:
            raise TypeError(
                f"{cls.__name__}.from_dict 无法从 {data!r} 重建："
                f"既不能 cls(**data)，也无法用默认构造 + 属性赋值。")
        for key, value in data.items():
            has_slot = any(
                key in (getattr(c, '__slots__', ()) if not isinstance(
                    getattr(c, '__slots__', ()), str) else (getattr(c, '__slots__', ''),))
                for c in cls.__mro__)
            if hasattr(cls, key) or has_slot:
                try:
                    setattr(obj, key, value)
                except AttributeError:
                    raise TypeError(
                        f"{cls.__name__} 的属性 {key!r} 不可写，无法 from_dict")
            else:
                raise TypeError(
                    f"{cls.__name__} 没有属性 {key!r}，无法 from_dict 重建")
        return obj

    def copy(self):
        """返回对象的浅拷贝（BUG-415）。

        原实现 ``self.__class__(self.__dict__.copy())``：把状态字典当作**构造
        参数**传入，对绝大多数类都是错的——实测
        ``Seq([1, 2]).copy()`` 得到 ``Seq(['_ops', '_active_op'])``（元素变成了
        属性名），``VList``/``Table`` 同样。改用标准库 ``copy.copy``。
        """
        try:
            return _copy_mod.copy(self)
        except Exception:
            # 少数对象不可 copy（含锁/文件句柄等），退化为构造式复制
            return self.__class__(self)


    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

        Returns:
            self, for chaining
        """
        # BUG-509: do() 零校验——do(123) 抛裸 "'int' object is not callable"，
        # 且 pre_f/sub_f 传不可调用对象时也是同类裸错。
        for _name, _fn, _allow_none in (
                ("f", f, False), ("pre_f", pre_f, True), ("sub_f", sub_f, True)):
            if _fn is None and _allow_none:
                continue
            if not callable(_fn):
                raise TypeError(
                    f"{type(self).__name__}.do() 的 {_name} 必须可调用"
                    + ("或 None" if _allow_none else "")
                    + f"，收到 {type(_fn).__name__}: {_fn!r}")
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self
    
    def update(self, **kwargs):
        """更新对象属性"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self


def _validate_type(value, expected_type, param_name=''):
    """类型验证辅助函数"""
    if not isinstance(value, expected_type):
        raise TypeError(f"{param_name} expected {expected_type.__name__}, got {type(value).__name__}")


def _ensure_callable(func):
    """确保值是可调用的"""
    if not callable(func):
        raise TypeError(f"Expected callable, got {type(func).__name__}")
    return func