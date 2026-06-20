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

__all__ = ['dataclass', 'field', 'asdict', 'is_dataclass', 'MISSING']

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

    def dataclass(cls: Optional[_T] = None, **kwargs) -> _T:
        """dataclass 装饰器（标准库模式）"""
        if cls is not None:
            return _std_dataclass(cls, **kwargs)
        return lambda c: _std_dataclass(c, **kwargs)  # type: ignore

    field = _std_field
    asdict = _std_asdict
    is_dataclass = _std_is_dataclass
    MISSING = _std_MISSING

else:
    # ── attrs 降级模式 ──
    try:
        from attr import attrs, attrib, asdict as _attr_asdict
        from attr import has as _attr_has
    except ImportError:
        msg = (
            "Python < 3.7 detected but 'attrs' package is not installed. "
            "Run: pip install attrs"
        )
        raise ImportError(msg)

    class _MISSING_TYPE:
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
        # attrs 的 frozen 默认是 False，等价
        if cls is not None:
            return attrs(cls, frozen=frozen, auto_attribs=True)
        # 带参装饰器模式: @dataclass(frozen=True)
        return lambda c: attrs(c, frozen=frozen, auto_attribs=True)

    def field(*, default=MISSING, default_factory=MISSING, **kwargs) -> Any:
        """
        field 兼容函数（底层使用 attr.attrib）

        Args:
            default: 默认值
            default_factory: 默认值工厂
            **kwargs: 其他参数（如 compare=False, repr=True）
        """
        if default_factory is not MISSING:
            return attrib(factory=default_factory, **kwargs)
        if default is not MISSING:
            return attrib(default=default, **kwargs)
        return attrib(**kwargs)

    def asdict(obj) -> Dict[str, Any]:
        """asdict 兼容函数"""
        return _attr_asdict(obj)

    def is_dataclass(obj) -> bool:
        """判断是否为 dataclass/attrs 实例"""
        return _attr_has(obj)
