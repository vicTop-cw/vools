"""
Type registry for vools.serialize

为 json/msgpack 等文本/二进制后端扩展对 Python 标准类型的支持。

支持类型：
- datetime.datetime / date / time / timedelta
- set / frozenset
- complex
- decimal.Decimal
- fractions.Fraction
- enum.Enum
- pathlib.Path
- bytearray

通过 register_type() 可以自定义更多类型的序列化/反序列化方式，
新类型自动被所有非 pickle 后端复用。
"""

import datetime
import decimal
import enum
import fractions
import pathlib
from typing import Any, Callable, Dict, Optional, Tuple

from ..core.datetime_compat import datetime_fromisoformat, date_fromisoformat, time_fromisoformat
__all__ = ['register_type', 'get_type_handler', 'get_type_deserializer']


# 类型处理器注册表
# type -> (type_name, serialize_fn, deserialize_fn)
_TYPE_HANDLERS: Dict[type, Tuple[str, Callable[[Any], Any], Callable[[Any], Any]]] = {}


def register_type(
    type_: type,
    name: Optional[str] = None,
    serialize: Optional[Callable[[Any], Any]] = None,
    deserialize: Optional[Callable[[Any], Any]] = None,
) -> None:
    """
    注册一个类型的序列化/反序列化处理器

    Args:
        type_: 要注册的类型
        name: 类型标识名称，默认使用 type_.__module__ + '.' + type_.__qualname__
        serialize: 序列化函数，接收实例，返回可 JSON/msgpack 编码的字典
        deserialize: 反序列化函数，接收字典，返回实例

    Example:
        register_type(
            MyClass,
            serialize=lambda obj: {'value': obj.value},
            deserialize=lambda state: MyClass(state['value']),
        )
    """
    if name is None:
        name = f'{type_.__module__}.{type_.__qualname__}'
    if serialize is None:
        raise ValueError(f'serialize function is required for type {name}')
    if deserialize is None:
        raise ValueError(f'deserialize function is required for type {name}')
    _TYPE_HANDLERS[type_] = (name, serialize, deserialize)


def get_type_handler(obj: Any) -> Optional[Tuple[str, Callable[[Any], Any]]]:
    """
    获取对象对应的类型处理器（序列化部分）

    按 MRO 长度降序匹配，保证子类优先于父类（如 datetime.datetime 优先于 datetime.date）。
    """
    handlers = sorted(_TYPE_HANDLERS.items(), key=lambda item: len(item[0].__mro__), reverse=True)
    for type_, (name, serialize, _) in handlers:
        if isinstance(obj, type_):
            return name, serialize
    return None


def get_type_deserializer(name: str) -> Optional[Callable[[Any], Any]]:
    """根据类型名称获取反序列化函数"""
    for registered_name, _, deserialize in _TYPE_HANDLERS.values():
        if registered_name == name:
            return deserialize
    return None


def _serialize_datetime(obj: datetime.datetime) -> Dict[str, Any]:
    return {
        'iso': obj.isoformat(),
        'tz': str(obj.tzinfo) if obj.tzinfo else None,
    }


def _deserialize_datetime(state: Dict[str, Any]) -> datetime.datetime:
    dt = datetime_fromisoformat(state['iso'])
    # 时区信息简单还原：如果 tz 是 UTC 则设置 UTC，否则保持原样
    tz_str = state.get('tz')
    if tz_str and tz_str != 'None':
        import datetime as _dt
        if tz_str in ('UTC', 'datetime.timezone.utc'):
            dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt


def _serialize_date(obj: datetime.date) -> Dict[str, Any]:
    return {'iso': obj.isoformat()}


def _deserialize_date(state: Dict[str, Any]) -> datetime.date:
    return date_fromisoformat(state['iso'])


def _serialize_time(obj: datetime.time) -> Dict[str, Any]:
    return {
        'iso': obj.isoformat(),
        'tz': str(obj.tzinfo) if obj.tzinfo else None,
    }


def _deserialize_time(state: Dict[str, Any]) -> datetime.time:
    t = time_fromisoformat(state['iso'])
    tz_str = state.get('tz')
    if tz_str and tz_str != 'None':
        import datetime as _dt
        if tz_str in ('UTC', 'datetime.timezone.utc'):
            t = t.replace(tzinfo=_dt.timezone.utc)
    return t


def _serialize_timedelta(obj: datetime.timedelta) -> Dict[str, Any]:
    return {'days': obj.days, 'seconds': obj.seconds, 'microseconds': obj.microseconds}


def _deserialize_timedelta(state: Dict[str, Any]) -> datetime.timedelta:
    return datetime.timedelta(
        days=state.get('days', 0),
        seconds=state.get('seconds', 0),
        microseconds=state.get('microseconds', 0),
    )


def _serialize_complex(obj: complex) -> Dict[str, Any]:
    return {'real': obj.real, 'imag': obj.imag}


def _deserialize_complex(state: Dict[str, Any]) -> complex:
    return complex(state['real'], state['imag'])


def _serialize_decimal(obj: decimal.Decimal) -> Dict[str, Any]:
    return {'value': str(obj)}


def _deserialize_decimal(state: Dict[str, Any]) -> decimal.Decimal:
    return decimal.Decimal(state['value'])


def _serialize_fraction(obj: fractions.Fraction) -> Dict[str, Any]:
    return {'numerator': obj.numerator, 'denominator': obj.denominator}


def _deserialize_fraction(state: Dict[str, Any]) -> fractions.Fraction:
    return fractions.Fraction(state['numerator'], state['denominator'])


def _serialize_enum(obj: enum.Enum) -> Dict[str, Any]:
    # BUG-204：模块路径与嵌套 __qualname__ 都含 '.'，不能拼成一个 'type' 串再用
    # rsplit 切开（嵌套 enum 会被误切）。module / qualname 分开存储，避免歧义。
    # BUG-255：函数内 enum 的 qualname 含 '<locals>'（如 'make.<locals>.Color'），
    # 反序列化时无法通过 getattr 链找到该类（函数局部作用域不可见）。
    # 检测到此标记时退化保存 name+value 并标记 local_enum，反序列化端据此退化
    # 返回值，保证不崩溃、数据不丢失。
    qualname = type(obj).__qualname__
    if '<locals>' in qualname:
        return {
            'type': f'{type(obj).__module__}.{qualname}',
            'module': type(obj).__module__,
            'qualname': qualname,
            'name': obj.name,
            'value': obj.value,
            'local_enum': True,
        }
    return {
        'type': f'{type(obj).__module__}.{qualname}',
        'module': type(obj).__module__,
        'qualname': qualname,
        'name': obj.name,
        'value': obj.value,
    }


# BUG-96/BUG-100/BUG-253: 反序列化 enum 前必须校验模块路径，
# 仅允许 enum 所在的标准模块，禁止导入 os/subprocess 等危险模块（导入即副作用）。
# BUG-253: __main__ 也必须放行——用户脚本/notebook/CLI 里定义的 enum 是可信代码，
# 否则 `python script.py` 里任何含 enum 的 JSON 往返都 ValueError。
_ALLOWED_ENUM_MODULES = frozenset({
    'enum',
    '__main__',
})
# 允许 vools/tests 前缀模块内的 enum 定义
# (tests 前缀仅覆盖仓库内测试代码，属可信代码)
_ALLOWED_ENUM_MODULE_PREFIXES = ('vools', 'tests')


def _is_allowed_enum_module(module_path: str) -> bool:
    """判断枚举模块路径是否在白名单内（BUG-100）。"""
    if module_path in _ALLOWED_ENUM_MODULES:
        return True
    for prefix in _ALLOWED_ENUM_MODULE_PREFIXES:
        if module_path.startswith(prefix):
            return True
    return False


def _deserialize_enum(state: Dict[str, Any]) -> Any:
    type_name = state['type']
    # BUG-255: 序列化端标记 local_enum=True 表示函数内 enum（qualname 含
    # '<locals>'），函数局部作用域不可见于 getattr 链。直接退化返回 name+value，
    # 保证不崩溃、数据不丢失。
    if state.get('local_enum'):
        return state['value']
    # BUG-204: 优先使用序列化时单独存储的 module / qualname（module 与嵌套
    # __qualname__ 都含 '.'，用 rsplit 切 'type' 串会误切嵌套 enum）。
    module_path = state.get('module')
    qualname = state.get('qualname')
    if not module_path or not qualname:
        parts = type_name.rsplit('.', 1)
        if len(parts) != 2:
            raise ValueError(f'Invalid enum type reference: {type_name}')
        module_path, qualname = parts
    # BUG-100: 导入前白名单校验，禁止任意模块导入（导入即副作用）
    if not _is_allowed_enum_module(module_path):
        raise ValueError(f'Invalid enum module: {module_path}')
    mod = __import__(module_path, fromlist=[qualname])
    # 沿 qualname 逐级解析嵌套类（如 'Outer.E' 先取 Outer 再取 E）
    cls = mod
    for part in qualname.split('.'):
        cls = getattr(cls, part)
    # BUG-96: 仅允许 enum.Enum 子类，禁止任意类或函数被呼叫
    if not isinstance(cls, type) or not issubclass(cls, enum.Enum):
        raise ValueError(f'Invalid enum type: {type_name}')
    return cls(state['value'])


def _serialize_path(obj: pathlib.PurePath) -> Dict[str, Any]:
    return {'path': str(obj)}


def _deserialize_path(state: Dict[str, Any]) -> pathlib.PurePath:
    return pathlib.PurePath(state['path'])


def _serialize_bytearray(obj: bytearray) -> Dict[str, Any]:
    return {'hex': obj.hex()}


def _deserialize_bytearray(state: Dict[str, Any]) -> bytearray:
    return bytearray.fromhex(state['hex'])


def _serialize_set(obj: set) -> Dict[str, Any]:
    return {'items': list(obj)}


def _deserialize_set(state: Dict[str, Any]) -> set:
    return set(state['items'])


def _serialize_frozenset(obj: frozenset) -> Dict[str, Any]:
    return {'items': list(obj)}


def _deserialize_frozenset(state: Dict[str, Any]) -> frozenset:
    return frozenset(state['items'])


# 注册内置类型处理器
# 注意：子类应优先注册，因此 datetime 在 date 之前
register_type(datetime.datetime, 'datetime.datetime', _serialize_datetime, _deserialize_datetime)
register_type(datetime.time, 'datetime.time', _serialize_time, _deserialize_time)
register_type(datetime.date, 'datetime.date', _serialize_date, _deserialize_date)
register_type(datetime.timedelta, 'datetime.timedelta', _serialize_timedelta, _deserialize_timedelta)
register_type(complex, 'complex', _serialize_complex, _deserialize_complex)
register_type(decimal.Decimal, 'decimal.Decimal', _serialize_decimal, _deserialize_decimal)
register_type(fractions.Fraction, 'fractions.Fraction', _serialize_fraction, _deserialize_fraction)
register_type(enum.Enum, 'enum.Enum', _serialize_enum, _deserialize_enum)
register_type(pathlib.PurePath, 'pathlib.PurePath', _serialize_path, _deserialize_path)
register_type(bytearray, 'bytearray', _serialize_bytearray, _deserialize_bytearray)
register_type(frozenset, 'frozenset', _serialize_frozenset, _deserialize_frozenset)
register_type(set, 'set', _serialize_set, _deserialize_set)