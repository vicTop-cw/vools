"""
dataclass 兼容层 — 统一处理 Python 不同版本的 dataclass 导入

在高版本 Python 使用标准库 dataclasses，
在低版本（<3.7）自动降级为 attrs 替代。

提供与标准库一致的接口：
- dataclass(cls, ...)       → 装饰器
- field(default=..., ...)    → 字段定义
- asdict(obj)               → 转字典
- is_dataclass(obj)         → 判断
"""

__all__ = ['dataclass', 'field', 'asdict', 'is_dataclass', 'MISSING', 'FrozenInstanceError']

from typing import Any, Dict, Callable, TypeVar, Optional
import sys

from .base import VoolsBase

_T = TypeVar('_T')

# ================================================================
# 检测运行环境，选择后端
# ================================================================

_HAS_DATACLASSES = sys.version_info >= (3, 7)

if _HAS_DATACLASSES:
    # ── 标准库 dataclasses ──
    from dataclasses import dataclass as _std_dataclass
    from dataclasses import field as _std_field
    from dataclasses import asdict as _std_asdict
    from dataclasses import is_dataclass as _std_is_dataclass
    from dataclasses import MISSING as _std_MISSING
    from dataclasses import FrozenInstanceError as _std_FrozenInstanceError

    def dataclass(cls: Optional[_T] = None, **kwargs) -> _T:
        """dataclass 装饰器（标准库模式）"""
        if cls is not None:
            return _std_dataclass(cls, **kwargs)
        return lambda c: _std_dataclass(c, **kwargs)  # type: ignore

    field = _std_field
    asdict = _std_asdict
    is_dataclass = _std_is_dataclass
    MISSING = _std_MISSING
    FrozenInstanceError = _std_FrozenInstanceError

else:
    # ── attrs 降级模式 ──
    try:
        import attr
        from attr import attrs, attrib, asdict as _attr_asdict
        from attr import has as _attr_has
        try:
            from attr.exceptions import FrozenInstanceError as _attr_FrozenInstanceError
        except ImportError:
            # attrs < 18.1.0 没有 frozen 特性，也就没有 FrozenInstanceError
            class _attr_FrozenInstanceError(AttributeError):
                """占位异常，兼容低版本 attrs"""
                pass
    except ImportError:
        msg = (
            "Python < 3.7 detected but 'attrs' package is not installed. "
            "Run: pip install attrs"
        )
        raise ImportError(msg)

    def _detect_attr_capabilities():
        """检测 attrs 版本支持的特性，确保最大兼容性"""
        import inspect
        caps = {
            'factory': False,
            'auto_attribs': False,
            'frozen': False,
        }
        try:
            sig = inspect.signature(attrib)
            caps['factory'] = 'factory' in sig.parameters
        except (ValueError, TypeError):
            pass
        try:
            sig = inspect.signature(attrs)
            # 注意：这里必须双向赋值——旧代码只在参数"缺失"时设 False，
            # "存在"时却从不设 True（初始值都是 False），导致 attrs 明明支持
            # auto_attribs / frozen 也被误判为不支持，py3.6 下 frozen=True 失效。
            caps['auto_attribs'] = 'auto_attribs' in sig.parameters
            caps['frozen'] = 'frozen' in sig.parameters
        except (ValueError, TypeError):
            pass
        return caps

    _ATTR_CAPS = _detect_attr_capabilities()

    class _MISSING_TYPE(VoolsBase):
        """模拟 dataclasses.MISSING"""
        def __repr__(self):
            return 'MISSING'
        def __bool__(self):
            return False
    MISSING = _MISSING_TYPE()

    def dataclass(cls: Optional[_T] = None, **kwargs) -> _T:
        """
        dataclass 兼容装饰器（底层使用 attrs）

        支持标准库 dataclass 的常用参数:
        - frozen: bool     → frozen=True（attrs 的 frozen）
        - order: bool      → 忽略（attrs 不支持自动排序）
        """
        frozen = kwargs.pop('frozen', False)

        _attrs_kwargs = {}
        if _ATTR_CAPS['auto_attribs']:
            _attrs_kwargs['auto_attribs'] = True
        if _ATTR_CAPS['frozen'] and frozen:
            _attrs_kwargs['frozen'] = True

        def _wrap(c):
            if not _ATTR_CAPS['auto_attribs']:
                # attrs < 18.2.0 不支持 auto_attribs，需手动将类型注解转为 attr.ib()
                # 由于 attrs 按 _CountingAttr.counter 排序，必须统一重新创建以确保顺序
                annotations = getattr(c, '__annotations__', {})
                _SENTINEL = object()
                _fields = {}
                for attr_name in annotations:
                    if attr_name.startswith('_'):
                        continue
                    val = getattr(c, attr_name, _SENTINEL)
                    if type(val).__name__ == '_CountingAttr':
                        _fields[attr_name] = ('ib', val._default)
                    elif val is not _SENTINEL:
                        _fields[attr_name] = ('default', val)
                    else:
                        _fields[attr_name] = ('required', None)
                    if attr_name in c.__dict__:
                        delattr(c, attr_name)
                for attr_name in annotations:
                    if attr_name not in _fields:
                        continue
                    kind, val = _fields[attr_name]
                    if kind == 'ib' and val is not attr.NOTHING:
                        setattr(c, attr_name, attr.ib(default=val))
                    elif kind == 'default':
                        setattr(c, attr_name, attr.ib(default=val))
                    else:
                        setattr(c, attr_name, attr.ib())
            # 必须在 attrs(c) **之前**把 __post_init__ 映射为 __attrs_post_init__：
            # attrs 在生成 __init__ 时检查 __attrs_post_init__ 是否存在；若在
            # attrs() 之后才赋值，生成的 __init__ 已定型、永远不会调用它，
            # 导致 Python < 3.7 下 __post_init__ 形同虚设（这正是 py3.6 上
            # KeyData.key_name 恒为空串的根因）。
            if hasattr(c, '__post_init__') and not hasattr(c, '__attrs_post_init__'):
                c.__attrs_post_init__ = c.__post_init__
            # 类已自定义 __repr__ 时不生成 attrs 的 repr，与标准库 dataclass
            # 行为一致（标准库 dataclass 只在未显式定义 __repr__ 时才生成）。
            # attrs 默认 repr=True 会覆盖自定义 __repr__（如 md/parser.py 的
            # InlineText，其 repr 输出 [B]'text' 风格的标记）。
            if 'repr' not in _attrs_kwargs and '__repr__' in c.__dict__:
                _attrs_kwargs['repr'] = False
            wrapped = attrs(c, **_attrs_kwargs)
            return wrapped

        if cls is not None:
            return _wrap(cls)
        return _wrap

    def field(*, default=MISSING, default_factory=MISSING, **kwargs) -> Any:
        """
        field 兼容函数（底层使用 attr.attrib）

        Args:
            default: 默认值
            default_factory: 默认值工厂
            **kwargs: 其他参数（如 compare=False, repr=True）
        """
        if 'compare' in kwargs:
            kwargs['eq'] = kwargs.pop('compare')
        if default_factory is not MISSING:
            if _ATTR_CAPS['factory']:
                return attrib(factory=default_factory, **kwargs)
            else:
                return attrib(default=attr.Factory(default_factory), **kwargs)
        if default is not MISSING:
            return attrib(default=default, **kwargs)
        return attrib(**kwargs)

    def asdict(obj) -> Dict[str, Any]:
        """asdict 兼容函数"""
        return _attr_asdict(obj)

    def is_dataclass(obj) -> bool:
        """判断是否为 dataclass/attrs 实例"""
        return _attr_has(obj)

    FrozenInstanceError = _attr_FrozenInstanceError
