# vools 编码、加密与序列化（v0.1.18）

`vools.encoding` / `vools.crypto` / `vools.serialize` 提供了数据转换、哈希、序列化等工具。

> Python 3.9+ 支持

---

## 1. 编码模块

### 便捷函数

```python
from vools import (
    b64encode, b64decode,
    urlencode, urldecode,
    json_dumps, json_loads,
    gzip_compress, gzip_decompress,
)

# Base64
encoded = b64encode("hello")
print(encoded)
assert b64decode(encoded) == "hello"

# URL 编码
u = urlencode("hello world")
print(u)                       # hello+world 或 hello%20world
assert urldecode(u) == "hello world"

# JSON
data = {"key": "value", "number": 42}
s = json_dumps(data)
assert json_loads(s) == data

# Gzip
compressed = gzip_compress("a" * 1000)
decompressed = gzip_decompress(compressed)
print(len(compressed), len(decompressed))
```

### Encoder / Decoder 链式调用

```python
from vools import Encoder, Decoder

result = Encoder("hello").base64().json().data
print(result)

decoded = Decoder(result).json().base64().data
print(decoded)                 # "hello"
```

### CodecRegistry

```python
from vools import CodecRegistry

# 查看支持的格式
print(CodecRegistry.supported_formats())

# 检查某个格式是否支持
assert CodecRegistry.is_format_supported("json") is True

# 注册自定义格式
CodecRegistry.register_codec(
    "custom_reverse",
    lambda data: data[::-1] if isinstance(data, str) else str(data)[::-1],
    lambda data: data[::-1],
)

from vools import Encoder, Decoder
assert Encoder("hello").encode("custom_reverse").data == "olleh"
assert Decoder("olleh").decode("custom_reverse").data == "hello"

# 注销
CodecRegistry.unregister_format("custom_reverse")
```

---

## 2. 加密模块

### Hash 函数

```python
from vools import md5, sha1, sha256, sha512

text = "hello world"
print(md5(text))       # 5eb63bbbe01eeed093cb22bb8f5acdc3
print(sha1(text))      # 2aae6c35c94fcfb415dbe95f4089b8ce92ee5591
print(sha256(text))    # b94d27b9934d3e08a52e52d7da7dabfac484e57f608193ecff...
print(sha512(text))
```

### HMAC

```python
from vools import hmac_md5, hmac_sha256

key = "my_secret_key"
data = "hello world"

print(hmac_md5(data, key))
print(hmac_sha256(data, key))
```

### Encryptor 链式调用

```python
from vools import Encryptor

result = Encryptor("hello").sha256().data
print(result)

result = Encryptor("data").hmac_sha256(key="secret").data
print(result)
```

### 密钥和令牌生成

```python
from vools import generate_key, generate_token

# generate_key 返回指定长度的十六进制字符串（每字节 2 个十六进制字符）
key_32 = generate_key(32)
print(key_32)            # 长度 64

key_16 = generate_key(16)
print(key_16)            # 长度 32

# generate_token 返回 URL-safe base64 编码的令牌
token = generate_token(32)
print(token)
```

### CryptoRegistry

```python
from vools import CryptoRegistry, encryptable, decryptable

print(CryptoRegistry.supported_algorithms())
# ['md5', 'sha1', 'sha256', 'sha512', 'hmac_md5', 'hmac_sha256', ...]

# 注册自定义算法
@encryptable("custom_xor")
def xor_encrypt(data, key="secret"):
    if isinstance(data, str):
        data = data.encode("utf-8")
    if isinstance(key, str):
        key = key.encode("utf-8")
    out = bytearray()
    for i, byte in enumerate(data):
        out.append(byte ^ key[i % len(key)])
    return bytes(out).hex()

@decryptable("custom_xor")
def xor_decrypt(data, key="secret"):
    if isinstance(key, str):
        key = key.encode("utf-8")
    raw = bytes.fromhex(data)
    out = bytearray()
    for i, byte in enumerate(raw):
        out.append(byte ^ key[i % len(key)])
    return out.decode("utf-8")

# 使用 Encryptor / Decryptor
enc = Encryptor("hello").encrypt("custom_xor", key="key").data
print(enc)

# 注销
CryptoRegistry.unregister_algorithm("custom_xor")
```

---

## 3. 序列化模块

`vools.serialize` 提供可跨进程存储的数据序列化支持，含 `JSON`、`msgpack`、`pickle` 多种实现。

### 基本用法

```python
from vools import serialize
from vools.serialize import dumps, loads, dumps_hex, loads_hex

data = {"a": 1, "b": [2, 3], "c": "hello"}

# JSON 序列化
buf = dumps(data, format="json")
restored = loads(buf, format="json")
assert restored == data

# pickle 序列化
buf = dumps(data, format="pickle")
restored = loads(buf, format="pickle")
assert restored == data

# hex 编码的序列化（便于嵌入文本/日志）
hex_buf = dumps_hex(data, format="json")
print(hex_buf)
restored = loads_hex(hex_buf, format="json")
assert restored == data
```

### Serializer 类

```python
from vools.serialize import Serializer

s = Serializer()
buf = s.dumps({"a": 1, "b": 2}, format="json")
print(s.loads(buf, format="json"))
```

---

## 4. 导入位置速查

| 名称 | 导入位置 | 说明 |
|------|----------|------|
| `Encoder` / `Decoder` | `from vools import Encoder, Decoder` | 链式编码/解码 |
| `CodecRegistry` | `from vools import CodecRegistry` | 编码格式注册中心 |
| `b64encode` / `b64decode` | `from vools import b64encode, b64decode` | Base64 |
| `urlencode` / `urldecode` | `from vools import urlencode, urldecode` | URL 编码 |
| `json_dumps` / `json_loads` | `from vools import json_dumps, json_loads` | JSON 便捷函数 |
| `gzip_compress` / `gzip_decompress` | `from vools import gzip_compress, gzip_decompress` | Gzip 压缩 |
| `Encryptor` | `from vools import Encryptor` | 链式加密/哈希 |
| `CryptoRegistry` | `from vools import CryptoRegistry` | 加密算法注册中心 |
| `md5` / `sha1` / `sha256` / `sha512` | `from vools import md5, sha1, sha256, sha512` | 哈希 |
| `hmac_md5` / `hmac_sha256` | `from vools import hmac_md5, hmac_sha256` | HMAC |
| `generate_key` / `generate_token` | `from vools import generate_key, generate_token` | 密钥/令牌生成 |
| `Serializer` | `from vools.serialize import Serializer` | 统一序列化入口 |
| `dumps` / `loads` | `from vools.serialize import dumps, loads` | 便捷序列化函数 |
| `dumps_hex` / `loads_hex` | `from vools.serialize import dumps_hex, loads_hex` | hex 编码序列化 |
