"""
测试加密模块
"""
from vools import (
    Encryptor, Decryptor, CryptoRegistry,
    encryptable, decryptable,
    md5, sha1, sha256, sha512,
    hmac_md5, hmac_sha256,
    generate_key, generate_token
)

print("="*60)
print("测试标准库 Hash 函数")
print("="*60)

# 测试 Hash 函数
test_data = 'hello world'

print("md5('%s'):" % test_data)
md5_result = md5(test_data)
print("  ", md5_result)
assert len(md5_result) == 32

print("sha1('%s'):" % test_data)
sha1_result = sha1(test_data)
print("  ", sha1_result)
assert len(sha1_result) == 40

print("sha256('%s'):" % test_data)
sha256_result = sha256(test_data)
print("  ", sha256_result)
assert len(sha256_result) == 64

print("sha512('%s'):" % test_data)
sha512_result = sha512(test_data)
print("  ", sha512_result)
assert len(sha512_result) == 128

print("\n" + "="*60)
print("测试 HMAC 函数")
print("="*60)

key = 'my_secret_key'

print("hmac_md5('%s', key='%s'):" % (test_data, key))
hmac_md5_result = hmac_md5(test_data, key)
print("  ", hmac_md5_result)
assert len(hmac_md5_result) == 32

print("hmac_sha256('%s', key='%s'):" % (test_data, key))
hmac_sha256_result = hmac_sha256(test_data, key)
print("  ", hmac_sha256_result)
assert len(hmac_sha256_result) == 64

print("\n" + "="*60)
print("测试 Encryptor 类")
print("="*60)

# 测试 Encryptor 链式调用
e = Encryptor('hello')
result = e.sha256().data
print("Encryptor('hello').sha256().data = '%s'" % result)
assert result == sha256('hello')

# 测试 HMAC
e2 = Encryptor('data')
result2 = e2.hmac_sha256(key='secret').data
print("Encryptor('data').hmac_sha256(key='secret').data = '%s'" % result2)
assert result2 == hmac_sha256('data', 'secret')

print("\n" + "="*60)
print("测试密钥和令牌生成")
print("="*60)

key_32 = generate_key(32)
print("generate_key(32): %s" % key_32)
assert len(key_32) == 64  # 32 bytes = 64 hex chars

key_16 = generate_key(16)
print("generate_key(16): %s" % key_16)
assert len(key_16) == 32  # 16 bytes = 32 hex chars

token = generate_token(32)
print("generate_token(32): %s" % token)
assert len(token) == 43  # URL-safe base64

print("\n" + "="*60)
print("测试 CryptoRegistry 自定义扩展")
print("="*60)

# 测试自定义加密器
@encryptable('custom_xor')
def xor_encrypt(data, key='secret'):
    """简单的 XOR 加密示例"""
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
    """简单的 XOR 解密示例"""
    if isinstance(key, str):
        key = key.encode('utf-8')
    data_bytes = bytes.fromhex(data)
    result = bytearray()
    for i, byte in enumerate(data_bytes):
        result.append(byte ^ key[i % len(key)])
    return result.decode('utf-8')

print("自定义 XOR 加密器已注册")
print("支持的算法:", CryptoRegistry.supported_algorithms())

# 使用注册的加密器
encrypted = xor_encrypt('hello world', key='key')
print("xor_encrypt('hello world', key='key') = '%s'" % encrypted)

decrypted = xor_decrypt(encrypted, key='key')
print("xor_decrypt(..., key='key') = '%s'" % decrypted)
assert decrypted == 'hello world'

# 使用 Encryptor 类调用自定义加密器
result = Encryptor('test').encrypt('custom_xor', key='key').data
print("Encryptor('test').encrypt('custom_xor', key='key').data = '%s'" % result)
assert xor_decrypt(result, key='key') == 'test'

print("\n" + "="*60)
print("测试 CryptoRegistry 功能")
print("="*60)

# 测试算法检查
assert CryptoRegistry.is_algorithm_supported('sha256') == True
assert CryptoRegistry.is_algorithm_supported('custom_xor') == True
assert CryptoRegistry.is_algorithm_supported('unknown') == False
print("算法检查测试通过")

# 测试注销算法
CryptoRegistry.unregister_algorithm('custom_xor')
assert CryptoRegistry.is_algorithm_supported('custom_xor') == False
print("注销算法测试通过")

# 重新注册
CryptoRegistry.register_crypto('custom_xor', xor_encrypt, xor_decrypt)
assert CryptoRegistry.is_algorithm_supported('custom_xor') == True
print("重新注册测试通过")

print("\n" + "="*60)
print("所有测试通过!")
print("="*60)
