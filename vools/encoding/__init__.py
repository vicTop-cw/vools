"""
编码模块

提供基于元类和装饰器的扩展编码功能，支持标准库编解码并允许用户自定义扩展。

核心组件：
- Encoder/Decoder: 支持链式调用的编解码类
- CodecRegistry: 编解码器注册中心，管理所有编解码器
- @encodable/@decodable: 装饰器，用于注册自定义编解码器

支持的标准库格式：
- Base64: base64 编码/解码
- URL: URL 编码/解码
- gzip/zlib/lzma: 压缩/解压
- JSON: 序列化/反序列化
- Pickle: 序列化/反序列化

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

使用示例：
    from vools import Encoder, Decoder
    
    # 链式编码
    result = Encoder('hello').base64().json().data
    
    # 链式解码
    result = Decoder(base64_json_string).base64().json().data
    
    # 使用便捷函数
    from vools import b64encode, json_dumps
    encoded = b64encode('hello')
    serialized = json_dumps({'key': 'value'})
"""

__all__ = [
    # 核心类
    'Encoder', 'Decoder', 'CodecRegistry',
    
    # 装饰器
    'encodable', 'decodable',
    
    # 便捷函数
    'b64encode', 'b64decode',
    'urlencode', 'urldecode',
    'gzip_compress', 'gzip_decompress',
    'zlib_compress', 'zlib_decompress',
    'lzma_compress', 'lzma_decompress',
    'json_dumps', 'json_loads',
    'pickle_dumps', 'pickle_loads',
    'compress', 'decompress',
    'serialize', 'deserialize',
    'to_bytes', 'to_str',
]

from .core import (
    Encoder, Decoder, CodecRegistry,
    encodable, decodable
)

# 便捷函数（从核心类提取）
b64encode = Encoder._b64encode
b64decode = Decoder._b64decode
urlencode = Encoder._urlencode
urldecode = Decoder._urldecode
lzma_compress = Encoder._lzma_compress
lzma_decompress = Decoder._lzma_decompress
json_dumps = Encoder._json_dumps
json_loads = Decoder._json_loads
pickle_dumps = Encoder._pickle_dumps
pickle_loads = Decoder._pickle_loads

# 尝试加载 Nim 加速的 gzip/zlib 实现
_gzip_compress_impl = None
_gzip_decompress_impl = None
_zlib_compress_impl = None
_zlib_decompress_impl = None

# Nim 压缩 shim 延迟加载：避免 import vools 或调用 b64encode 等编码函数时
# 预加载 vools.bridge 子包，否则 vools.BRIDGE_AVAILABLE 标志翻转逻辑失效。
_nim_compress_loaded = False


def _load_nim_compress():
    """延迟加载 Nim 压缩实现（首次需要时导入 vools.bridge）。"""
    global _gzip_compress_impl, _gzip_decompress_impl
    global _zlib_compress_impl, _zlib_decompress_impl, _nim_compress_loaded
    if _nim_compress_loaded:
        return
    _nim_compress_loaded = True
    try:
        from vools.bridge.nim.compress_shim import (
            gzip_compress as _nim_gzip_compress,
            gzip_decompress as _nim_gzip_decompress,
            zlib_compress as _nim_zlib_compress,
            zlib_decompress as _nim_zlib_decompress,
            is_nim_compress_available as _nim_compress_available,
        )
        if _nim_compress_available():
            _gzip_compress_impl = _nim_gzip_compress
            _gzip_decompress_impl = _nim_gzip_decompress
            _zlib_compress_impl = _nim_zlib_compress
            _zlib_decompress_impl = _nim_zlib_decompress
            # bridge 已实际可用：同步标志，保持 BRIDGE_AVAILABLE 语义一致
            import vools as _v
            _v.BRIDGE_AVAILABLE = True
    except ImportError:
        pass

# Python fallback 实现
def _py_gzip_compress(data, level=9):
    if isinstance(data, str):
        data = data.encode('utf-8')
    import gzip
    return gzip.compress(data, compresslevel=level)

def _py_gzip_decompress(data):
    if isinstance(data, str):
        data = data.encode('latin-1')
    import gzip
    return gzip.decompress(data)

def _py_zlib_compress(data, level=9):
    if isinstance(data, str):
        data = data.encode('utf-8')
    import zlib
    return zlib.compress(data, level=level)

def _py_zlib_decompress(data):
    if isinstance(data, str):
        data = data.encode('latin-1')
    import zlib
    return zlib.decompress(data)

# 最终函数绑定（Nim 优先，否则 Python）——通过延迟加载避免预加载 vools.bridge
def gzip_compress(data, level=9):
    _load_nim_compress()
    f = _gzip_compress_impl if _gzip_compress_impl else _py_gzip_compress
    return f(data, level=level)


def gzip_decompress(data):
    _load_nim_compress()
    f = _gzip_decompress_impl if _gzip_decompress_impl else _py_gzip_decompress
    return f(data)


def zlib_compress(data, level=9):
    _load_nim_compress()
    f = _zlib_compress_impl if _zlib_compress_impl else _py_zlib_compress
    return f(data, level=level)


def zlib_decompress(data):
    _load_nim_compress()
    f = _zlib_decompress_impl if _zlib_decompress_impl else _py_zlib_decompress
    return f(data)


def compress(data, method='gzip', **kwargs):
    """
    通用压缩函数
    
    Args:
        data: 要压缩的数据
        method: 压缩方法，可选 'gzip', 'zlib', 'lzma'
        **kwargs: 额外参数传递给具体压缩函数
    
    Returns:
        压缩后的字节数据
    
    Example:
        compressed = compress('hello world', method='gzip')
    """
    methods = {
        'gzip': gzip_compress,
        'zlib': zlib_compress,
        'lzma': lzma_compress
    }
    if method not in methods:
        raise ValueError(f"不支持的压缩方法: {method}")
    return methods[method](data, **kwargs)


def decompress(data, method='gzip'):
    """
    通用解压函数
    
    Args:
        data: 要解压的数据（字节串）
        method: 解压方法，可选 'gzip', 'zlib', 'lzma'
    
    Returns:
        解压后的原始数据
    
    Example:
        decompressed = decompress(compressed_data, method='gzip')
    """
    methods = {
        'gzip': gzip_decompress,
        'zlib': zlib_decompress,
        'lzma': lzma_decompress
    }
    if method not in methods:
        raise ValueError(f"不支持的解压方法: {method}")
    return methods[method](data)


def serialize(data, format='json', **kwargs):
    """
    通用序列化函数
    
    Args:
        data: 要序列化的数据
        format: 序列化格式，可选 'json', 'pickle'，或已注册的自定义格式
        **kwargs: 额外参数传递给具体序列化函数
    
    Returns:
        序列化后的数据
    
    Example:
        json_str = serialize({'key': 'value'}, format='json')
        
        # 使用自定义格式（需先注册）
        @encodable('yaml')
        def yaml_encode(data):
            import yaml
            return yaml.dump(data)
        
        yaml_str = serialize(data, format='yaml')
    """
    # 首先检查是否有已注册的编码器
    encoder = CodecRegistry.get_encoder(format)
    if encoder is not None:
        return encoder(data, **kwargs)
    
    # 回退到内置格式
    formats = {
        'json': json_dumps,
        'pickle': pickle_dumps
    }
    if format not in formats:
        raise ValueError(f"不支持的序列化格式: {format}")
    return formats[format](data, **kwargs)


def deserialize(data, format='json'):
    """
    通用反序列化函数
    
    Args:
        data: 要反序列化的数据
        format: 反序列化格式，可选 'json', 'pickle'，或已注册的自定义格式
    
    Returns:
        反序列化后的原始数据
    
    Example:
        data = deserialize('{"key": "value"}', format='json')
        
        # 使用自定义格式（需先注册）
        @decodable('yaml')
        def yaml_decode(data):
            import yaml
            return yaml.load(data, Loader=yaml.SafeLoader)
        
        data = deserialize(yaml_str, format='yaml')
    """
    # 首先检查是否有已注册的解码器
    decoder = CodecRegistry.get_decoder(format)
    if decoder is not None:
        return decoder(data)
    
    # 回退到内置格式
    formats = {
        'json': json_loads,
        'pickle': pickle_loads
    }
    if format not in formats:
        raise ValueError(f"不支持的反序列化格式: {format}")
    return formats[format](data)


def to_bytes(data, encoding='utf-8'):
    """
    转换为字节串
    
    Args:
        data: 要转换的数据
        encoding: 编码格式，默认为 'utf-8'
    
    Returns:
        字节串或原始数据（如果已经是字节串）
    
    Example:
        b = to_bytes('hello')  # b'hello'
    """
    if isinstance(data, str):
        return data.encode(encoding)
    return data


def to_str(data, encoding='utf-8'):
    """
    转换为字符串
    
    Args:
        data: 要转换的数据
        encoding: 编码格式，默认为 'utf-8'
    
    Returns:
        字符串或原始数据（如果已经是字符串）
    
    Example:
        s = to_str(b'hello')  # 'hello'
    """
    if isinstance(data, bytes):
        return data.decode(encoding)
    return data
