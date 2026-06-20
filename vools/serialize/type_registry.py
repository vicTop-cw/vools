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
    dt = datetime.datetime.fromisoformat(state['iso'])
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
    return datetime.date.fromisoformat(state['iso'])


def _serialize_time(obj: datetime.time) -> Dict[str, Any]:
    return {
        'iso': obj.isoformat(),
        'tz': str(obj.tzinfo) if obj.tzinfo else None,
    }


def _deserialize_time(state: Dict[str, Any]) -> datetime.time:
    t = datetime.time.fromisoformat(state['iso'])
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
    return {
        'type': f'{type(obj).__module__}.{type(obj).__qualname__}',
        'name': obj.name,
        'value': obj.value,
    }


def _deserialize_enum(state: Dict[str, Any]) -> Any:
    type_name = state['type']
    parts = type_name.rsplit('.', 1)
    if len(parts) != 2:
        raise ValueError(f'Invalid enum type reference: {type_name}')
    module_path, cls_name = parts
    mod = __import__(module_path, fromlist=[cls_name])
    cls = getattr(mod, cls_name)
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