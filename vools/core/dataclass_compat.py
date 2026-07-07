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
        from attr.exceptions import FrozenInstanceError as _attr_FrozenInstanceError
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
            'auto_attribs': True,
            'frozen': True,
        }
        try:
            sig = inspect.signature(attrib)
            caps['factory'] = 'factory' in sig.parameters
        except (ValueError, TypeError):
            pass
        try:
            sig = inspect.signature(attrs)
            if 'auto_attribs' not in sig.parameters:
                caps['auto_attribs'] = False
            if 'frozen' not in sig.parameters:
                caps['frozen'] = False
        except (ValueError, TypeError):
            pass
        return caps

    _ATTR_CAPS = _detect_attr_capabilities()

    class _MISSING_TYPE:
        """模拟 dataclasses.MISSING"""
        def __repr__(self):
            return 'MISSING'
        def __bool__(self):
            return False
        def do(self, f=print, pre_f=None, sub_f=None):
            """Apply a function for side effects, return self for chaining.

            Args:
                f: Function to apply (default print)
                pre_f: Pre-processing function applied before f
                sub_f: Post-processing function (no return expected)

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
            wrapped = attrs(c, **_attrs_kwargs)
            if not _ATTR_CAPS['auto_attribs']:
                pass
            # 兼容 __post_init__: attrs 用 __attrs_post_init__
            if hasattr(wrapped, '__post_init__') and not hasattr(wrapped, '__attrs_post_init__'):
                wrapped.__attrs_post_init__ = wrapped.__post_init__
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
