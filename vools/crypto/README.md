# vools.crypto

加密模块，提供加密和解密功能。

## 主要功能

- **哈希**: MD5、SHA1、SHA256、SHA512
- **加密**: AES、DES、RSA（基础支持）
- **随机生成**: `random_string`, `random_hex`

## 核心功能

| 名称 | 说明 |
|------|------|
| `md5` | MD5 哈希 |
| `sha256` | SHA256 哈希 |
| `encrypt` | 加密 |
| `decrypt` | 解密 |

## 使用示例

```python
from vools.crypto import md5, sha256, encrypt, decrypt

# 哈希
hash_value = md5('hello')
hash_value = sha256('hello')

# 加密
encrypted = encrypt('secret', key='mykey')
decrypted = decrypt(encrypted, key='mykey')
```

## 注意事项

- 加密算法需要安装额外依赖