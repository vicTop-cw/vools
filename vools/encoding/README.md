# vools.encoding

编码模块，提供数据编码和解码功能。

## 主要功能

- **编码**: `Encoder` - Base64、URL、HTML 编码
- **解码**: `Decoder` - Base64、URL、HTML 解码
- **编码检测**: `detect_encoding` - 自动检测编码

## 核心类

| 名称 | 说明 |
|------|------|
| `Encoder` | 编码器 |
| `Decoder` | 解码器 |

## 使用示例

```python
from vools.encoding import Encoder, Decoder

# Base64 编码
encoded = Encoder.base64_encode('hello')

# URL 编码
encoded = Encoder.url_encode('hello world')

# HTML 编码
encoded = Encoder.html_encode('<script>')

# 解码
decoded = Decoder.base64_decode(encoded)
```

## 注意事项

- 支持多种编码格式，自动检测