"""
测试编码模块 - 新版（含自定义扩展）
"""
from vools import (
    Encoder, Decoder, CodecRegistry,
    encodable, decodable,
    b64encode, b64decode,
    gzip_compress, gzip_decompress,
    zlib_compress, zlib_decompress,
    json_dumps, json_loads,
    urlencode, urldecode,
    serialize, deserialize
)

print("="*60)
print("测试标准库功能")
print("="*60)

# 测试 base64
encoded = b64encode('hello')
print("b64encode('hello') = '%s'" % encoded)
assert b64decode(encoded) == 'hello'

# 测试 URL 编码
encoded_url = urlencode('hello world')
print("urlencode('hello world') = '%s'" % encoded_url)
assert urldecode(encoded_url) == 'hello world'

# 测试 JSON
data = {'key': 'value', 'number': 42}
json_str = json_dumps(data)
print("json_dumps(%s) = %s" % (data, json_str))
assert json_loads(json_str) == data

# 测试链式调用
result = Encoder('hello').base64().json().data
print("Encoder('hello').base64().json().data = %s" % result)

print("\n" + "="*60)
print("测试 CodecRegistry 自定义扩展")
print("="*60)

# 测试自定义编码器 - 模拟 YAML 格式
@encodable('yaml')
def mock_yaml_encode(data):
    """模拟 YAML 编码"""
    if isinstance(data, dict):
        return '\n'.join(f"{k}: {v}" for k, v in data.items())
    return str(data)

@decodable('yaml')  
def mock_yaml_decode(data):
    """模拟 YAML 解码"""
    result = {}
    for line in data.strip().split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            result[key.strip()] = value.strip()
    return result

print("自定义 YAML 编码器已注册")
print("支持的格式:", CodecRegistry.supported_formats())

# 使用注册的编码器
encoder = CodecRegistry.get_encoder('yaml')
decoder = CodecRegistry.get_decoder('yaml')
assert encoder({'name': 'test', 'value': '123'}) == 'name: test\nvalue: 123'
assert decoder('name: test\nvalue: 123') == {'name': 'test', 'value': '123'}
print("自定义编码器测试通过")

# 测试动态调用
yaml_result = Encoder({'key': 'value'}).encode('yaml').data
print("Encoder({'key': 'value'}).encode('yaml').data = '%s'" % yaml_result)
assert yaml_result == 'key: value'

yaml_decoded = Decoder('key: value').decode('yaml').data
print("Decoder('key: value').decode('yaml').data = %s" % yaml_decoded)
assert yaml_decoded == {'key': 'value'}

# 测试通用接口
serialized = serialize({'a': 1}, format='yaml')
print("serialize({'a': 1}, 'yaml') = '%s'" % serialized)
assert serialized == 'a: 1'

deserialized = deserialize('a: 1', format='yaml')
print("deserialize('a: 1', 'yaml') = %s" % deserialized)
assert deserialized == {'a': '1'}

print("\n" + "="*60)
print("测试 CodecRegistry 其他功能")
print("="*60)

# 测试格式检查
assert CodecRegistry.is_format_supported('json') == True
assert CodecRegistry.is_format_supported('yaml') == True
assert CodecRegistry.is_format_supported('unknown') == False
print("格式检查测试通过")

# 测试注销格式
CodecRegistry.unregister_format('yaml')
assert CodecRegistry.is_format_supported('yaml') == False
print("注销格式测试通过")

# 重新注册
CodecRegistry.register_codec('yaml', mock_yaml_encode, mock_yaml_decode)
assert CodecRegistry.is_format_supported('yaml') == True
print("重新注册测试通过")

print("\n" + "="*60)
print("所有测试通过!")
print("="*60)
