"""
json/msgpack 序列化编解码器

提供 default 函数（编码时处理 __getstate__ 对象）和
object_hook 函数（解码时重建对象），以及 orjson 后处理。
"""

import pickle
import importlib
from typing import Any, Dict

from .context import get_protocol, get_current_serializer
from ..core.datetime_compat import datetime_fromisoformat, date_fromisoformat
from ..decorators.bridge_decorator import bridge
__all__ = [
    'vools_preprocess', 'vools_default', 'vools_object_hook',
    'post_process_orjson', 'post_process_msgpack',
    'pickle_encode', 'pickle_decode',
]


# ─── 编码（序列化） ───

# json/msgpack 原生支持的基础类型
_NATIVE_BASE_TYPES = (str, int, float, bool, type(None), bytes, list, dict, tuple)


def vools_preprocess(obj: Any) -> Any:
    """
    递归预处理对象树，将非原生类型（注册表类型、内置子类等）转换为包装字典。

    json/msgpack 的 default 回调不会为内置子类调用（它们被当作原生类型处理），
    因此需要预先遍历对象树，在编码前替换。
    """
    obj_type = type(obj)

    # 1. 检查类型注册表（处理 orjson 等不经过 default 回调的原生类型，如 enum）
    from .type_registry import get_type_handler
    handler = get_type_handler(obj)
    if handler is not None:
        type_name, serialize_fn = handler
        return {
            '__vools_type__': True,
            'type': type_name,
            'state': serialize_fn(obj),
        }

    # 2. 检查是否是内置子类且有自定义 __getstate__（排除 object 默认实现）
    _object_has_getstate = hasattr(object, '__getstate__')
    if (isinstance(obj, _NATIVE_BASE_TYPES)
            and obj_type not in _NATIVE_BASE_TYPES
            and hasattr(obj_type, '__getstate__')
            and (not _object_has_getstate or obj_type.__getstate__ is not object.__getstate__)):

        state = obj.__getstate__()
        if state is None:
            return obj

        # 单例格式
        if isinstance(state, dict) and '__singleton__' in state:
            return {'__vools_singleton__': state['__singleton__']}

        type_name = f'{obj_type.__module__}.{obj_type.__qualname__}'
        base_value = _extract_base_value(obj)
        if base_value is not None and isinstance(state, dict):
            state['__base__'] = base_value

        return {
            '__vools_obj__': True,
            'type': type_name,
            'state': state,
        }

    # 3. 递归处理容器类型
    if isinstance(obj, dict):
        return {k: vools_preprocess(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(vools_preprocess(item) for item in obj)

    return obj


def vools_default(obj: Any) -> Any:
    """
    json/msgpack 的 default 回调：处理非原生可序列化的对象。

    优先级：
    1. 若 type(obj) 在类型注册表中 → 包装为 __vools_type__ 格式
    2. 若 type(obj) 有自定义 __getstate__ → 包装为 __vools_obj__ 格式
    3. 若 state 含 __singleton__ 键 → 简化为 __vools_singleton__ 格式
    4. 回退到 get_handler(obj) + serialize_callable → 旧 __callable__ 格式
    5. 抛 TypeError
    """
    obj_type = type(obj)

    # 1. 检查类型注册表（datetime、set、complex、Decimal 等）
    from .type_registry import get_type_handler, get_type_deserializer
    handler = get_type_handler(obj)
    if handler is not None:
        type_name, serialize_fn = handler
        return {
            '__vools_type__': True,
            'type': type_name,
            'state': serialize_fn(obj),
        }

    # 2. 检查对象是否自身支持自定义 __getstate__（排除 object 默认实现）
    _object_has_getstate = hasattr(object, '__getstate__')
    if hasattr(obj_type, '__getstate__') and (
        not _object_has_getstate or obj_type.__getstate__ is not object.__getstate__
    ):
        # 调用对象的 __getstate__ 获取状态
        state = obj.__getstate__()
        if state is None:
            # 无状态时回退到 handler 系统或抛错
            serializer = get_current_serializer()
            if serializer is not None:
                try:
                    from .callable import get_handler, serialize_callable
                    handler = get_handler(obj)
                    if handler is not None:
                        name, state_bytes = serialize_callable(obj, serializer)
                        return {
                            '__callable__': True,
                            'handler': name,
                            'state': state_bytes if isinstance(state_bytes, (str, int, float, list, dict)) else list(state_bytes) if isinstance(state_bytes, bytes) else str(state_bytes),
                        }
                except Exception:
                    pass
            raise TypeError(f"Object of type {obj_type.__name__} is not serializable")

        # 检查是否是单例标记
        if isinstance(state, dict) and '__singleton__' in state:
            return {'__vools_singleton__': state['__singleton__']}

        # 包装为 __vools_obj__ 格式
        type_name = f'{obj_type.__module__}.{obj_type.__qualname__}'

        # 对于内置子类（str, datetime 等），保存基础类型值
        base_value = _extract_base_value(obj)
        if base_value is not None and isinstance(state, dict):
            state['__base__'] = base_value

        return {
            '__vools_obj__': True,
            'type': type_name,
            'state': state,
        }

    # 3. 回退到 handler 系统
    serializer = get_current_serializer()
    if serializer is not None:
        try:
            from .callable import get_handler, serialize_callable
            handler = get_handler(obj)
            if handler is not None:
                name, state_bytes = serialize_callable(obj, serializer)
                return {
                    '__callable__': True,
                    'handler': name,
                    'state': state_bytes if isinstance(state_bytes, (str, int, float, list, dict)) else list(state_bytes) if isinstance(state_bytes, bytes) else str(state_bytes),
                }
        except Exception:
            pass

    # 4. 无法处理
    raise TypeError(f"Object of type {obj_type.__name__} is not serializable")


def _extract_base_value(obj: Any) -> Any:
    """
    从内置子类中提取基础类型值，用于 json/msgpack 重建时传给 __new__。
    """
    import datetime
    if isinstance(obj, str):
        return str(obj)
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    return None


# ─── 解码（反序列化） ───

def vools_object_hook(d: Dict[str, Any]) -> Any:
    """
    json/msgpack 的 object_hook 回调：在解码每个 dict 时检查是否是
    vools 对象包装，并重建原始对象。
    """
    # 1. 单例格式
    if '__vools_singleton__' in d and len(d) <= 2:
        return _resolve_singleton(d['__vools_singleton__'])

    # 2. __vools_obj__ 格式
    if d.get('__vools_obj__'):
        type_name = d.get('type', '')
        state = d.get('state', {})
        return _reconstruct_object(type_name, state)

    # 3. __vools_type__ 格式（类型注册表，如 datetime / set / complex）
    if d.get('__vools_type__'):
        type_name = d.get('type', '')
        state = d.get('state', {})
        from .type_registry import get_type_deserializer
        deserializer = get_type_deserializer(type_name)
        if deserializer is not None:
            return deserializer(state)
        return d

    # 4. 旧 __callable__ 格式（由 Serializer.loads 在顶层处理）
    #    这里不做处理，原样返回
    return d


def _resolve_singleton(ref: str) -> Any:
    """
    解析单例引用，格式为 'module.path:attr_name' 或 'module.path.attr_name'。
    """
    if ':' in ref:
        module_path, attr_name = ref.rsplit(':', 1)
    else:
        # 最后一部分作为属性名
        parts = ref.rsplit('.', 1)
        if len(parts) == 2:
            module_path, attr_name = parts
        else:
            raise ValueError(f"Invalid singleton reference: {ref}")

    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, attr_name)
    except (ImportError, AttributeError) as e:
        raise ValueError(f"Cannot resolve singleton '{ref}': {e}")


def _reconstruct_object(type_name: str, state: Dict[str, Any]) -> Any:
    """
    根据 type_name 和 state 重建对象。
    """
    cls = _import_class(type_name)
    if cls is None:
        return state  # 无法导入类，返回原始 state

    # 处理内置子类
    base_value = state.pop('__base__', None)
    if base_value is not None:
        obj = _new_builtin_subclass(cls, base_value, state)
    else:
        # 普通类：__new__ 创建空实例，__setstate__ 恢复状态
        try:
            obj = cls.__new__(cls)
        except TypeError:
            # 某些类的 __new__ 需要参数，尝试从 state 推断
            obj = cls.__new__(cls, *(() if base_value is None else (base_value,)))

    # 调用 __setstate__ 恢复状态
    if state and hasattr(cls, '__setstate__'):
        obj.__setstate__(state)

    return obj


def _import_class(type_name: str):
    """
    根据类型全限定名导入类。
    例如 'vools.data.seq._NONE' → import vools.data.seq; return _NONE
    """
    try:
        # 处理嵌套类（qualname 用 . 分隔）
        # 例如 'vools.decorators.curry_core.Curried'
        parts = type_name.rsplit('.', 1)
        if len(parts) != 2:
            return None

        module_path, cls_name = parts
        mod = importlib.import_module(module_path)
        return getattr(mod, cls_name, None)
    except (ImportError, AttributeError):
        return None


def _new_builtin_subclass(cls, base_value: Any, state: Dict[str, Any]) -> Any:
    """
    为内置子类（str, datetime 等）创建实例。
    """
    import datetime

    if issubclass(cls, str):
        return cls(base_value)

    if issubclass(cls, datetime.datetime):
        fmt = state.get('fmt', '%Y-%m-%d')
        try:
            dt = datetime_fromisoformat(base_value)
            return cls(dt, fmt=fmt) if fmt != '%Y-%m-%d' else cls(dt)
        except (ValueError, TypeError):
            return cls(datetime.datetime.now(), fmt=fmt)

    if issubclass(cls, datetime.date):
        try:
            return cls(date_fromisoformat(base_value))
        except (ValueError, TypeError):
            return cls(datetime.date.today())

    # 其他情况：尝试直接用 base_value 构造
    try:
        return cls(base_value)
    except TypeError:
        return cls.__new__(cls)


# ─── orjson / msgpack 后处理 ───

def post_process_orjson(obj: Any) -> Any:
    """
    orjson 不支持 object_hook，需要递归后处理反序列化结果，
    找到 __vools_obj__ / __vools_singleton__ / __vools_type__ 标记并重建对象。
    """
    if isinstance(obj, dict):
        # 先递归处理值
        processed = {k: post_process_orjson(v) for k, v in obj.items()}

        # 然后检查是否需要重建
        if '__vools_singleton__' in processed and len(processed) <= 2:
            return _resolve_singleton(processed['__vools_singleton__'])
        if processed.get('__vools_obj__'):
            type_name = processed.get('type', '')
            state = processed.get('state', {})
            return _reconstruct_object(type_name, state)
        if processed.get('__vools_type__'):
            type_name = processed.get('type', '')
            state = processed.get('state', {})
            from .type_registry import get_type_deserializer
            deserializer = get_type_deserializer(type_name)
            if deserializer is not None:
                return deserializer(state)

        return processed

    if isinstance(obj, list):
        return [post_process_orjson(item) for item in obj]

    if isinstance(obj, tuple):
        return tuple(post_process_orjson(item) for item in obj)

    return obj


# msgpack 新版 (>=1.0) 不支持 object_hook，后处理逻辑与 orjson 相同
post_process_msgpack = post_process_orjson


# ─── Pickle 序列化（带 Nim 加速） ───


def _pickle_encode_py(obj: Any, protocol: int = pickle.HIGHEST_PROTOCOL) -> bytes:
    """
    纯 Python pickle 编码

    Args:
        obj: 要序列化的对象
        protocol: pickle 协议版本

    Returns:
        序列化的 bytes
    """
    return pickle.dumps(obj, protocol=protocol)


def _pickle_decode_py(data: bytes) -> Any:
    """
    纯 Python pickle 解码

    Args:
        data: pickle 序列化的 bytes

    Returns:
        反序列化后的对象
    """
    return pickle.loads(data)


# 尝试导入 Nim 桥接函数
_nim_pickle_encode = None
_nim_pickle_decode = None

try:
    from ..bridge.nim import nim_pickle_encode as _nim_encode
    from ..bridge.nim import nim_pickle_decode as _nim_decode
    if callable(_nim_encode):
        _nim_pickle_encode = _nim_encode
    if callable(_nim_decode):
        _nim_pickle_decode = _nim_decode
except ImportError:
    pass


def pickle_encode(obj: Any, protocol: int = pickle.HIGHEST_PROTOCOL) -> bytes:
    """
    序列化对象为字节串

    当 Nim 桥接库可用时，使用 Nim 高性能实现；
    否则回退到纯 Python pickle 实现。

    Args:
        obj: 要序列化的对象
        protocol: pickle 协议版本（仅 Python 实现使用）

    Returns:
        序列化的 bytes
    """
    # Nim 版本返回 None 如果不可用
    if _nim_pickle_encode is not None:
        result = _nim_pickle_encode(obj)
        if result is not None:
            return result
    return _pickle_encode_py(obj, protocol)


def pickle_decode(data: bytes) -> Any:
    """
    反序列化字节串为对象

    当 Nim 桥接库可用时，使用 Nim 高性能实现；
    否则回退到纯 Python pickle 实现。

    Args:
        data: pickle 序列化的 bytes

    Returns:
        反序列化后的对象
    """
    if _nim_pickle_decode is not None:
        result = _nim_pickle_decode(data)
        if result is not None:
            return result
    return _pickle_decode_py(data)