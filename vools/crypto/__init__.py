"""
加密模块

提供基于元类和装饰器的扩展加密功能，支持标准库加密算法并允许用户自定义扩展。

核心组件：
- Encryptor/Decryptor: 支持链式调用的加密解密类
- CryptoRegistry: 加密算法注册中心，管理所有加密解密器
- @encryptable/@decryptable: 装饰器，用于注册自定义加密解密器

支持的标准库算法：
- Hash: MD5, SHA-1, SHA-224, SHA-256, SHA-384, SHA-512
- HMAC: HMAC-MD5, HMAC-SHA1, HMAC-SHA256
- Random: 安全随机数生成（generate_key, generate_token）

扩展机制：
用户可以通过以下方式扩展自定义算法：

1. 使用装饰器注册：
    @encryptable('custom')
    def custom_encrypt(data, key):
        # 自定义加密逻辑
        return encrypted_data
    
    @decryptable('custom')
    def custom_decrypt(data, key):
        # 自定义解密逻辑
        return decrypted_data

2. 使用注册表注册：
    CryptoRegistry.register_encryptor('custom', custom_encrypt)
    CryptoRegistry.register_decryptor('custom', custom_decrypt)

3. 动态调用：
    # 注册后可直接使用
    Encryptor(data).encrypt('custom', key=secret_key)
    Decryptor(data).decrypt('custom', key=secret_key)

使用示例：
    from vools import Encryptor, sha256, generate_key
    
    # 使用便捷函数
    hash_value = sha256('hello')
    key = generate_key(32)
    
    # 使用 Encryptor 类
    result = Encryptor('hello').sha256().data
    hmac_result = Encryptor('data').hmac_sha256(key='secret').data
"""

__all__ = [
    # 核心类
    'Encryptor', 'Decryptor', 'CryptoRegistry',
    
    # 装饰器
    'encryptable', 'decryptable',
    
    # Hash 函数
    'md5', 'sha1', 'sha224', 'sha256', 'sha384', 'sha512',
    
    # HMAC 函数
    'hmac_md5', 'hmac_sha1', 'hmac_sha256',
    
    # 密钥/令牌生成
    'generate_key', 'generate_token',
]

from .core import (
    Encryptor, Decryptor, CryptoRegistry,
    encryptable, decryptable,
    md5, sha1, sha224, sha256, sha384, sha512,
    hmac_md5, hmac_sha1, hmac_sha256,
    generate_key, generate_token
)
