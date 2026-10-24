"""
编码模块核心类

提供基于元类和装饰器的扩展编码功能，支持标准库编解码并允许用户自定义扩展。

核心组件：
- CodecRegistry: 编解码器注册中心，管理所有编解码器
- Encoder/Decoder: 支持链式调用的编解码类
- @encodable/@decodable: 装饰器，用于注册自定义编解码器

扩展机制：
用户可以通过以下方式扩展自定义格式：

1. 使用装饰器注册：
    @encodable('yaml')
    def yaml_encode(data):
        import yaml
        return yaml.dump(data)
    
    @decodable('yaml')
    def yaml_decode(data):
        import yaml
        return yaml.load(data, Loader=yaml.SafeLoader)

2. 使用注册表注册：
    CodecRegistry.register_encoder('xml', xml_encode_func)
    CodecRegistry.register_decoder('xml', xml_decode_func)

3. 动态调用：
    # 注册后可直接使用
    Encoder(data).encode('yaml')
    Decoder(data).decode('yaml')
"""

__all__ = ['Encoder', 'Decoder', 'encodable', 'decodable', 'CodecRegistry']

import base64
import zlib
import gzip
import lzma
import json
import pickle
import urllib.parse
from typing import Any, Callable, Type, Dict, Optional

from ..core.base import VoolsBase


class CodecRegistry(VoolsBase):
    """
    编解码器注册中心
    
    提供编解码器的注册、查询和管理功能。
    
    Example:
        # 注册自定义编解码器
        CodecRegistry.register_encoder('custom', custom_encode)
        CodecRegistry.register_decoder('custom', custom_decode)
        
        # 查询支持的格式
        formats = CodecRegistry.supported_formats()
        
        # 获取编解码器
        encoder = CodecRegistry.get_encoder('json')
        decoder = CodecRegistry.get_decoder('json')
        
        # 使用编解码器
        encoded = encoder(data)
        decoded = decoder(encoded)
    """
    
    _encoders: Dict[str, Callable] = {}
    _decoders: Dict[str, Callable] = {}
    
    @classmethod
    def _validate_registration(cls, format_name: Any, func: Any, kind: str) -> None:
        """校验注册参数（BUG-398）。

        原实现直接 `_encoders[format_name] = encoder`，什么都不检查：

        * `format_name=None` → 污染注册表，之后 `supported_formats()` 的
          `sorted(set(...) | ...)` 会把 None 与 str 比较，**TypeError 崩掉**，
          影响所有调用方；
        * 空串格式名会让错误信息/列表出现空项；
        * 非可调用对象能注册成功，直到真正 encode/decode 时才炸。
        """
        if not isinstance(format_name, str) or not format_name.strip():
            raise ValueError(
                f"格式名必须是非空字符串，收到 "
                f"{type(format_name).__name__}: {format_name!r}")
        if not callable(func):
            raise TypeError(
                f"{kind}必须可调用，收到 "
                f"{type(func).__name__}: {func!r}")

    @classmethod
    def _warn_duplicate(cls, format_name: str, existing: Any, new: Any) -> None:
        """同名覆盖时告警（同一函数重复注册视为幂等，不告警）——BUG-398。"""
        if existing is None or existing is new:
            return
        import warnings as _w
        _w.warn(
            f"编解码格式 {format_name!r} 的注册被覆盖："
            f"{getattr(existing, '__qualname__', existing)!r} -> "
            f"{getattr(new, '__qualname__', new)!r}（如需替换请显式 "
            f"unregister_format 后重新注册）",
            RuntimeWarning, stacklevel=3)

    @classmethod
    def register_encoder(cls, format_name: str, encoder: Callable) -> None:
        """
        注册编码器
        
        Args:
            format_name: 格式名称（如 'json', 'yaml', 'xml'）
            encoder: 编码函数，接受数据并返回编码后的结果
        
        Example:
            def yaml_encode(data):
                import yaml
                return yaml.dump(data)
            
            CodecRegistry.register_encoder('yaml', yaml_encode)
        """
        cls._validate_registration(format_name, encoder, '编码器')
        cls._warn_duplicate(format_name, cls._encoders.get(format_name), encoder)
        cls._encoders[format_name] = encoder
    
    @classmethod
    def register_decoder(cls, format_name: str, decoder: Callable) -> None:
        """
        注册解码器
        
        Args:
            format_name: 格式名称（如 'json', 'yaml', 'xml'）
            decoder: 解码函数，接受编码数据并返回原始数据
        
        Example:
            def yaml_decode(data):
                import yaml
                return yaml.load(data, Loader=yaml.SafeLoader)
            
            CodecRegistry.register_decoder('yaml', yaml_decode)
        """
        cls._validate_registration(format_name, decoder, '解码器')
        cls._warn_duplicate(format_name, cls._decoders.get(format_name), decoder)
        cls._decoders[format_name] = decoder
    
    @classmethod
    def get_encoder(cls, format_name: str) -> Optional[Callable]:
        """
        获取编码器
        
        Args:
            format_name: 格式名称
        
        Returns:
            编码器函数，如果未找到返回 None
        """
        return cls._encoders.get(format_name)
    
    @classmethod
    def get_decoder(cls, format_name: str) -> Optional[Callable]:
        """
        获取解码器
        
        Args:
            format_name: 格式名称
        
        Returns:
            解码器函数，如果未找到返回 None
        """
        return cls._decoders.get(format_name)
    
    @classmethod
    def supported_formats(cls) -> list:
        """
        获取支持的格式列表
        
        Returns:
            所有已注册格式的列表
        """
        # BUG-337: 用 set 合并后直接 list()，顺序随字符串哈希每进程变化——
        # 「支持格式」出现在错误信息与 UI 列表中，应当稳定；统一按字母序返回。
        return sorted(set(cls._encoders.keys()) | set(cls._decoders.keys()))
    
    @classmethod
    def is_format_supported(cls, format_name: str) -> bool:
        """
        检查格式是否支持
        
        Args:
            format_name: 格式名称
        
        Returns:
            如果格式已注册返回 True，否则返回 False
        """
        return format_name in cls._encoders or format_name in cls._decoders
    
    @classmethod
    def register_codec(cls, format_name: str, encoder: Callable, decoder: Callable) -> None:
        """
        同时注册编码器和解码器
        
        Args:
            format_name: 格式名称
            encoder: 编码函数
            decoder: 解码函数
        
        Example:
            CodecRegistry.register_codec('yaml', yaml_encode, yaml_decode)
        """
        cls.register_encoder(format_name, encoder)
        cls.register_decoder(format_name, decoder)
    
    @classmethod
    def unregister_format(cls, format_name: str) -> None:
        """
        注销格式
        
        Args:
            format_name: 要注销的格式名称
        """
        cls._encoders.pop(format_name, None)
        cls._decoders.pop(format_name, None)
    
    @classmethod
    def get_encoders(cls) -> Dict[str, Callable]:
        """
        获取所有编码器
        
        Returns:
            编码器字典 {format_name: encoder_func}
        """
        return cls._encoders.copy()
    
    @classmethod
    def get_encoders(cls) -> Dict[str, Callable]:
        """
        获取所有编码器
        
        Returns:
            编码器字典 {format_name: encoder_func}
        """
        return cls._encoders.copy()
    
    @classmethod
    def get_decoders(cls) -> Dict[str, Callable]:
        """
        获取所有解码器
        
        Returns:
            解码器字典 {format_name: decoder_func}
        """
        return cls._decoders.copy()


def encodable(format_name: str):
    """
    装饰器：标记函数为编码器
    
    将装饰的函数注册到 CodecRegistry 中，作为指定格式的编码器。
    
    Args:
        format_name: 格式名称
        
    Example:
        @encodable('yaml')
        def yaml_encode(data):
            import yaml
            return yaml.dump(data)
        
        # 使用
        encoder = CodecRegistry.get_encoder('yaml')
        result = encoder({'key': 'value'})
    """
    def decorator(func: Callable) -> Callable:
        CodecRegistry.register_encoder(format_name, func)
        return func
    return decorator


def decodable(format_name: str):
    """
    装饰器：标记函数为解码器
    
    将装饰的函数注册到 CodecRegistry 中，作为指定格式的解码器。
    
    Args:
        format_name: 格式名称
        
    Example:
        @decodable('yaml')
        def yaml_decode(data):
            import yaml
            return yaml.load(data, Loader=yaml.SafeLoader)
        
        # 使用
        decoder = CodecRegistry.get_decoder('yaml')
        result = decoder('key: value')
    """
    def decorator(func: Callable) -> Callable:
        CodecRegistry.register_decoder(format_name, func)
        return func
    return decorator


class EncoderMeta(type):
    """编码器元类"""
    
    def __new__(cls, name: str, bases: tuple, attrs: dict):
        new_cls = super().__new__(cls, name, bases, attrs)
        return new_cls
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



class Encoder(VoolsBase, metaclass=EncoderMeta):
    """
    编码器类 - 提供链式调用的编码操作
    
    支持的操作：
    - base64(): Base64 编码
    - url(): URL 编码
    - gzip(level=9): gzip 压缩
    - zlib(level=9): zlib 压缩
    - lzma(): LZMA 压缩
    - json(**kwargs): JSON 序列化
    - pickle(protocol=None): Pickle 序列化
    - to_bytes(encoding='utf-8', errors='strict'): 字符串转字节
    - encode(format_name, **kwargs): 使用已注册的自定义编码器
      （format_name 也可传 Python 编码名如 'utf-8'/'gbk'，等价 to_bytes；
       BUG-312 修正：原文档把本能力写成 encode(encoding=...)，实际方法名是 to_bytes）
    
    Example:
        # 基本使用
        e = Encoder('hello world')
        result = e.base64().data  # 'aGVsbG8gd29ybGQ='
        
        # 链式调用
        e = Encoder({'key': 'value'})
        result = e.json().base64().data
        
        # 使用自定义编码器（需先注册）
        @encodable('yaml')
        def yaml_encode(data):
            import yaml
            return yaml.dump(data)
        
        e = Encoder({'key': 'value'})
        result = e.encode('yaml').data
    """
    
    def __init__(self, data: Any):
        """
        初始化编码器
        
        Args:
            data: 要编码的数据
        """
        self._data = data
        self._history = []
    
    @property
    def data(self):
        """获取当前数据"""
        return self._data
    
    @property
    def history(self):
        """获取操作历史列表"""
        return self._history
    
    def _apply(self, func: Callable, name: str, **kwargs):
        """应用编码函数"""
        try:
            self._data = func(self._data, **kwargs)
            self._history.append(name)
            return self
        except Exception as e:
            raise ValueError(f"Failed to apply {name}: {e}")
    
    def base64(self, encoding: str = 'utf-8'):
        """
        Base64 编码
        
        Args:
            encoding: 字符串编码格式，默认为 'utf-8'
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encoder('hello').base64().data  # 'aGVsbG8='
        """
        return self._apply(self._b64encode, 'base64', encoding=encoding)
    
    def url(self, encoding: str = 'utf-8'):
        """
        URL 编码
        
        Args:
            encoding: 字符串编码格式，默认为 'utf-8'
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encoder('hello world').url().data  # 'hello%20world'
        """
        return self._apply(self._urlencode, 'url', encoding=encoding)
    
    def gzip(self, level: int = 9):
        """
        gzip 压缩
        
        Args:
            level: 压缩级别，范围 0-9，默认为 9（最高压缩）
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encoder('hello world').gzip().data  # bytes
        """
        return self._apply(self._gzip_compress, 'gzip', level=level)
    
    def zlib(self, level: int = 9):
        """
        zlib 压缩
        
        Args:
            level: 压缩级别，范围 0-9，默认为 9（最高压缩）
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encoder('hello world').zlib().data  # bytes
        """
        return self._apply(self._zlib_compress, 'zlib', level=level)
    
    def lzma(self):
        """
        LZMA 压缩
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encoder('hello world').lzma().data  # bytes
        """
        return self._apply(self._lzma_compress, 'lzma')
    
    def json(self, **kwargs):
        """
        JSON 序列化
        
        Args:
            **kwargs: 传递给 json.dumps 的额外参数
        
        Returns:
            self，支持链式调用
        
        Example:
            data = {'key': 'value'}
            result = Encoder(data).json().data  # '{"key": "value"}'
        """
        return self._apply(self._json_dumps, 'json', **kwargs)
    
    def pickle(self, protocol=None):
        """
        Pickle 序列化
        
        Args:
            protocol: Pickle 协议版本，默认为 None（使用默认协议）
        
        Returns:
            self，支持链式调用
        
        Example:
            data = {'key': 'value'}
            result = Encoder(data).pickle().data  # bytes
        """
        return self._apply(self._pickle_dumps, 'pickle', protocol=protocol)
    
    def encode(self, format_name: str, **kwargs):
        """
        使用已注册的编码器进行编码
        
        通过 CodecRegistry 获取指定格式的编码器并应用。
        
        Args:
            format_name: 格式名称（需先注册）
            **kwargs: 传递给编码器的额外参数
        
        Returns:
            self，支持链式调用
        
        Raises:
            ValueError: 如果格式未注册
        
        Example:
            @encodable('yaml')
            def yaml_encode(data):
                import yaml
                return yaml.dump(data)
            
            result = Encoder({'key': 'value'}).encode('yaml').data
        """
        encoder = CodecRegistry.get_encoder(format_name)
        if encoder is None:
            # BUG-312: 类文档曾承诺 encode(encoding='utf-8')「字符串转字节」，
            # 实现却只认注册格式名。此处对合法 Python 编码名回退到 to_bytes，
            # 两种文档写法都成立；非法名仍抛错并同时列出可用编码名。
            import codecs as _codecs
            try:
                _codecs.lookup(format_name)
            except Exception:
                raise ValueError(
                    f"Unknown encoder format: {format_name}. "
                    f"Supported formats: {CodecRegistry.supported_formats()}")
            return self.to_bytes(format_name, **kwargs)
        
        def wrapper(data, **kw):
            return encoder(data, **kw)
        
        return self._apply(wrapper, format_name, **kwargs)
    
    def to_bytes(self, encoding: str = 'utf-8', errors: str = 'strict'):
        """
        字符串转字节
        
        Args:
            encoding: 编码格式，默认为 'utf-8'
            errors: 错误处理方式，默认为 'strict'
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encoder('hello').to_bytes().data  # b'hello'
        """
        return self._apply(self._encode, 'encode', encoding=encoding, errors=errors)
    
    @staticmethod
    def _b64encode(data: Any, encoding: str = 'utf-8') -> str:
        if isinstance(data, str):
            data = data.encode(encoding)
        return base64.b64encode(data).decode(encoding)
    
    @staticmethod
    def _urlencode(data: Any, encoding: str = 'utf-8') -> str:
        # BUG-222: 原实现非 str 输入 `return data` 静默透传（bytes/dict/int
        # 什么都不做还记 history=['url'] 虚假成功），与同场 base64/gzip 对
        # 非法输入明确抛 ValueError 的口径不一。bytes 本可正确编码
        # （quote_from_bytes），其余类型抛 TypeError 交由 _apply 统一包装。
        if isinstance(data, str):
            return urllib.parse.quote(data, encoding=encoding)
        if isinstance(data, (bytes, bytearray)):
            return urllib.parse.quote_from_bytes(bytes(data))
        raise TypeError(
            f"url encode expects str/bytes, got {type(data).__name__}")
    
    @staticmethod
    def _gzip_compress(data: Any, level: int = 9) -> bytes:
        if isinstance(data, str):
            data = data.encode('utf-8')
        return gzip.compress(data, compresslevel=level)
    
    @staticmethod
    def _zlib_compress(data: Any, level: int = 9) -> bytes:
        if isinstance(data, str):
            data = data.encode('utf-8')
        return zlib.compress(data, level=level)
    
    @staticmethod
    def _lzma_compress(data: Any) -> bytes:
        if isinstance(data, str):
            data = data.encode('utf-8')
        return lzma.compress(data)
    
    @staticmethod
    def _json_dumps(data: Any, **kwargs) -> str:
        return json.dumps(data, **kwargs)
    
    @staticmethod
    def _pickle_dumps(data: Any, protocol=None) -> bytes:
        return pickle.dumps(data, protocol=protocol)
    
    @staticmethod
    def _encode(data: Any, encoding: str = 'utf-8', errors: str = 'strict') -> bytes:
        if isinstance(data, str):
            return data.encode(encoding, errors=errors)
        return data
    
    def __repr__(self):
        return f"Encoder(data={repr(self._data)}, history={self._history})"
    def __str__(self):
        return str(self._data)


class Decoder(VoolsBase, metaclass=EncoderMeta):
    """
    解码器类 - 提供链式调用的解码操作
    
    支持的操作：
    - base64(): Base64 解码
    - url(): URL 解码
    - gzip(): gzip 解压
    - zlib(): zlib 解压
    - lzma(): LZMA 解压
    - json(): JSON 反序列化
    - pickle(): Pickle 反序列化
    - to_str(encoding='utf-8', errors='strict'): 字节转字符串
    - decode(format_name, **kwargs): 使用已注册的自定义解码器
      （format_name 也可传 Python 编码名如 'utf-8'/'gbk'，等价 to_str；
       BUG-312 修正：原文档把本能力写成 decode(encoding=...)，实际方法名是 to_str）
    
    Example:
        # 基本使用
        d = Decoder('aGVsbG8=')
        result = d.base64().data  # 'hello'
        
        # 链式调用
        d = Decoder(base64_json_string).base64().json().data
        
        # 使用自定义解码器（需先注册）
        @decodable('yaml')
        def yaml_decode(data):
            import yaml
            return yaml.load(data, Loader=yaml.SafeLoader)
        
        d = Decoder(yaml_string).decode('yaml').data
    """
    
    def __init__(self, data: Any):
        """
        初始化解码器
        
        Args:
            data: 要解码的数据
        """
        self._data = data
        self._history = []
    
    @property
    def data(self):
        """获取当前数据"""
        return self._data
    
    @property
    def history(self):
        """获取操作历史列表"""
        return self._history
    
    def _apply(self, func: Callable, name: str, **kwargs):
        """应用解码函数"""
        try:
            self._data = func(self._data, **kwargs)
            self._history.append(name)
            return self
        except Exception as e:
            raise ValueError(f"Failed to apply {name}: {e}")
    
    def base64(self, encoding: str = 'utf-8'):
        """
        Base64 解码
        
        Args:
            encoding: 字符串编码格式，默认为 'utf-8'
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Decoder('aGVsbG8=').base64().data  # 'hello'
        """
        return self._apply(self._b64decode, 'base64', encoding=encoding)
    
    def url(self, encoding: str = 'utf-8'):
        """
        URL 解码
        
        Args:
            encoding: 字符串编码格式，默认为 'utf-8'
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Decoder('hello%20world').url().data  # 'hello world'
        """
        return self._apply(self._urldecode, 'url', encoding=encoding)
    
    def gzip(self):
        """
        gzip 解压
        
        Returns:
            self，支持链式调用
        
        Example:
            compressed = gzip_compress('hello world')
            result = Decoder(compressed).gzip().data  # b'hello world'
        """
        return self._apply(self._gzip_decompress, 'gzip')
    
    def zlib(self):
        """
        zlib 解压
        
        Returns:
            self，支持链式调用
        
        Example:
            compressed = zlib_compress('hello world')
            result = Decoder(compressed).zlib().data  # b'hello world'
        """
        return self._apply(self._zlib_decompress, 'zlib')
    
    def lzma(self):
        """
        LZMA 解压
        
        Returns:
            self，支持链式调用
        
        Example:
            compressed = lzma_compress('hello world')
            result = Decoder(compressed).lzma().data  # b'hello world'
        """
        return self._apply(self._lzma_decompress, 'lzma')
    
    def json(self):
        """
        JSON 反序列化
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Decoder('{"key": "value"}').json().data  # {'key': 'value'}
        """
        return self._apply(self._json_loads, 'json')
    
    def pickle(self):
        """
        Pickle 反序列化
        
        Returns:
            self，支持链式调用
        
        Example:
            pickled = pickle_dumps({'key': 'value'})
            result = Decoder(pickled).pickle().data  # {'key': 'value'}
        """
        return self._apply(self._pickle_loads, 'pickle')
    
    def decode(self, format_name: str, **kwargs):
        """
        使用已注册的解码器进行解码
        
        通过 CodecRegistry 获取指定格式的解码器并应用。
        
        Args:
            format_name: 格式名称（需先注册）
            **kwargs: 传递给解码器的额外参数
        
        Returns:
            self，支持链式调用
        
        Raises:
            ValueError: 如果格式未注册
        
        Example:
            @decodable('yaml')
            def yaml_decode(data):
                import yaml
                return yaml.load(data, Loader=yaml.SafeLoader)
            
            result = Decoder(yaml_string).decode('yaml').data
        """
        decoder = CodecRegistry.get_decoder(format_name)
        if decoder is None:
            # BUG-312: 与 Encoder.encode 对称——合法 Python 编码名回退 to_str。
            import codecs as _codecs
            try:
                _codecs.lookup(format_name)
            except Exception:
                raise ValueError(
                    f"Unknown decoder format: {format_name}. "
                    f"Supported formats: {CodecRegistry.supported_formats()}")
            return self.to_str(format_name, **kwargs)
        
        def wrapper(data, **kw):
            return decoder(data, **kw)
        
        return self._apply(wrapper, format_name, **kwargs)
    
    def to_str(self, encoding: str = 'utf-8', errors: str = 'strict'):
        """
        字节转字符串
        
        Args:
            encoding: 编码格式，默认为 'utf-8'
            errors: 错误处理方式，默认为 'strict'
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Decoder(b'hello').to_str().data  # 'hello'
        """
        return self._apply(self._decode, 'decode', encoding=encoding, errors=errors)
    
    @staticmethod
    def _b64decode(data: Any, encoding: str = 'utf-8') -> Any:
        if isinstance(data, str):
            data = data.encode(encoding)
        raw = base64.b64decode(data)
        if not encoding:
            return raw
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            # BUG-370: 二进制载荷（gzip/zlib/lzma/pickle 的 base64 形态）不是合法
            # UTF-8，原实现直接抛 UnicodeDecodeError —— 且传 encoding='latin-1'
            # 也无济于事（返回 str，下一步 gzip 仍要求 bytes），使 binary 链
            # **完全无法往返**。这里返回原始 bytes，后续二进制解码器可继续处理；
            # 文本载荷仍按 encoding 解码为 str（docstring 示例 ''.base64().data
            # 期待 str 的行为不变）。
            return raw
    
    @staticmethod
    def _urldecode(data: Any, encoding: str = 'utf-8') -> str:
        # BUG-222: 同 _urlencode——非 str 静默透传改显式口径。unquote 原生
        # 支持 str 与 bytes-like（py3.6+），其余类型抛 TypeError 交 _apply
        # 包装成 ValueError，对齐 base64/gzip 等同类算子。
        if isinstance(data, (str, bytes, bytearray)):
            return urllib.parse.unquote(data, encoding=encoding)
        raise TypeError(
            f"url decode expects str/bytes, got {type(data).__name__}")
    
    @staticmethod
    def _gzip_decompress(data: Any) -> bytes:
        return gzip.decompress(data)
    
    @staticmethod
    def _zlib_decompress(data: Any) -> bytes:
        return zlib.decompress(data)
    
    @staticmethod
    def _lzma_decompress(data: Any) -> bytes:
        return lzma.decompress(data)
    
    @staticmethod
    def _json_loads(data: Any) -> Any:
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        return json.loads(data)
    
    @staticmethod
    def _pickle_loads(data: Any) -> Any:
        return pickle.loads(data)
    
    @staticmethod
    def _decode(data: Any, encoding: str = 'utf-8', errors: str = 'strict') -> str:
        if isinstance(data, bytes):
            return data.decode(encoding, errors=errors)
        return data
    
    def __repr__(self):
        return f"Decoder(data={repr(self._data)}, history={self._history})"
    
    def __str__(self):
        return str(self._data)



# 注册默认编解码器
CodecRegistry.register_encoder('base64', Encoder._b64encode)
CodecRegistry.register_encoder('url', Encoder._urlencode)
CodecRegistry.register_encoder('gzip', Encoder._gzip_compress)
CodecRegistry.register_encoder('zlib', Encoder._zlib_compress)
CodecRegistry.register_encoder('lzma', Encoder._lzma_compress)
CodecRegistry.register_encoder('json', Encoder._json_dumps)
CodecRegistry.register_encoder('pickle', Encoder._pickle_dumps)

CodecRegistry.register_decoder('base64', Decoder._b64decode)
CodecRegistry.register_decoder('url', Decoder._urldecode)
CodecRegistry.register_decoder('gzip', Decoder._gzip_decompress)
CodecRegistry.register_decoder('zlib', Decoder._zlib_decompress)
CodecRegistry.register_decoder('lzma', Decoder._lzma_decompress)
CodecRegistry.register_decoder('json', Decoder._json_loads)
CodecRegistry.register_decoder('pickle', Decoder._pickle_loads)
