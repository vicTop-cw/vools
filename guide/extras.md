# vools 编码、加密与 Result 类型

编码模块（encoding）、加密模块（crypto）和 Result 类型提供了数据转换和安全处理工具。

---

## 编码模块

### 基本用法

```python
from vools import (
    Encoder, Decoder, CodecRegistry,
    b64encode, b64decode,
    urlencode, urldecode,
    json_dumps, json_loads,
    gzip_compress, gzip_decompress,
    serialize, deserialize
)

# Base64 编码
encoded = b64encode('hello')
print(encoded)  # base64 编码结果
assert b64decode(encoded) == 'hello'

# URL 编码
encoded_url = urlencode('hello world')
assert urldecode(encoded_url) == 'hello world'

# JSON 序列化
data = {'key': 'value', 'number': 42}
json_str = json_dumps(data)
assert json_loads(json_str) == data

# 链式调用
result = Encoder('hello').base64().json().data
```

### 自定义编码器

```python
# 注册自定义编码器
from vools import encodable, decodable

@encodable('yaml')
def mock_yaml_encode(data):
    if isinstance(data, dict):
        return '\n'.join(f"{k}: {v}" for k, v in data.items())
    return str(data)

@decodable('yaml')  
def mock_yaml_decode(data):
    result = {}
    for line in data.strip().split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            result[key.strip()] = value.strip()
    return result

# 使用自定义编码器
yaml_result = Encoder({'key': 'value'}).encode('yaml').data
print(yaml_result)  # 'key: value'

yaml_decoded = Decoder('key: value').decode('yaml').data
print(yaml_decoded)  # {'key': 'value'}

# 通用接口
serialized = serialize({'a': 1}, format='yaml')
deserialized = deserialize('a: 1', format='yaml')
```

### CodecRegistry 功能

```python
# 检查支持的格式
print(CodecRegistry.supported_formats())

# 格式检查
assert CodecRegistry.is_format_supported('json') == True
assert CodecRegistry.is_format_supported('yaml') == True
assert CodecRegistry.is_format_supported('unknown') == False

# 注销格式
CodecRegistry.unregister_format('yaml')
assert CodecRegistry.is_format_supported('yaml') == False

# 重新注册
CodecRegistry.register_codec('yaml', mock_yaml_encode, mock_yaml_decode)
```

## 加密模块

vools 提供统一的加密接口，支持多种哈希算法和自定义扩展。

### Hash 函数

```python
from vools import md5, sha1, sha256, sha512

test_data = 'hello world'

print(md5(test_data))    # 32 位十六进制
print(sha1(test_data))   # 40 位十六进制
print(sha256(test_data)) # 64 位十六进制
print(sha512(test_data)) # 128 位十六进制
```

### HMAC 函数

```python
from vools import hmac_md5, hmac_sha256

key = 'my_secret_key'

result = hmac_md5(test_data, key)
print(result)  # HMAC-MD5 结果

result = hmac_sha256(test_data, key)
print(result)  # HMAC-SHA256 结果
```

### Encryptor 类

```python
from vools import Encryptor

# 链式调用
result = Encryptor('hello').sha256().data
print(result)

# HMAC
result = Encryptor('data').hmac_sha256(key='secret').data
print(result)
```

### 密钥和令牌生成

```python
from vools import generate_key, generate_token

# 生成密钥
key_32 = generate_key(32)  # 32 字节 = 64 个十六进制字符
print(key_32)

key_16 = generate_key(16)  # 16 字节 = 32 个十六进制字符
print(key_16)

# 生成令牌（URL-safe base64）
token = generate_token(32)
print(token)  # 43 个字符
```

### 自定义加密器

```python
from vools import encryptable, decryptable, CryptoRegistry

@encryptable('custom_xor')
def xor_encrypt(data, key='secret'):
    if isinstance(data, str):
        data = data.encode('utf-8')
    if isinstance(key, str):
        key = key.encode('utf-8')
    result = bytearray()
    for i, byte in enumerate(data):
        result.append(byte ^ key[i % len(key)])
    return bytes(result).hex()

@decryptable('custom_xor')
def xor_decrypt(data, key='secret'):
    if isinstance(key, str):
        key = key.encode('utf-8')
    data_bytes = bytes.fromhex(data)
    result = bytearray()
    for i, byte in enumerate(data_bytes):
        result.append(byte ^ key[i % len(key)])
    return result.decode('utf-8')

# 使用自定义加密器
encrypted = xor_encrypt('hello world', key='key')
decrypted = xor_decrypt(encrypted, key='key')
assert decrypted == 'hello world'

# 使用 Encryptor 类
result = Encryptor('test').encrypt('custom_xor', key='key').data
print(result)
```

### CryptoRegistry 功能

```python
# 检查支持的算法
print(CryptoRegistry.supported_algorithms())

# 算法检查
assert CryptoRegistry.is_algorithm_supported('sha256') == True
assert CryptoRegistry.is_algorithm_supported('custom_xor') == True

# 注销算法
CryptoRegistry.unregister_algorithm('custom_xor')

# 重新注册
CryptoRegistry.register_crypto('custom_xor', xor_encrypt, xor_decrypt)
```

## Result 类型与 safe 装饰器

vools 提供函数式编程的错误处理支持。

### Result 类型

```python
from vools.functional import Result, Success, Failure, success, failure

# 创建 Result
r1 = Result.success(42)
r2 = Result.failure(ValueError('test error'))

# 检查状态
print(r1.is_success)  # True
print(r2.is_failure)  # True

# 映射操作
result = r1.map(lambda x: x * 2)
print(result)  # Success(84)

# 获取值
print(r1.unwrap())      # 42
print(r2.unwrap_or(0))  # 0
```

### safe 装饰器

```python
from vools.functional import safe

@safe
def divide(a, b):
    return a / b

# 成功情况
result = divide(10, 2)
print(result)  # Success(5.0)

# 失败情况
result = divide(10, 0)
print(result)  # Failure(ZeroDivisionError(...))
```

