"""
加密模块核心类

提供基于元类和装饰器的扩展加密功能，支持标准库加密算法并允许用户自定义扩展。

核心组件：
- CryptoRegistry: 加密算法注册中心，管理所有加密解密器
- Encryptor/Decryptor: 支持链式调用的加密解密类
- @encryptable/@decryptable: 装饰器，用于注册自定义加密解密器

支持的标准库算法：
- Hash: MD5, SHA-1, SHA-224, SHA-256, SHA-384, SHA-512
- HMAC: 支持所有 hash 算法的 HMAC
- Symmetric: AES（需要 pycryptodome 或使用 secrets 进行简单加密）
- Random: 安全随机数生成

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
"""

__all__ = ['Encryptor', 'Decryptor', 'encryptable', 'decryptable', 'CryptoRegistry',
           'md5', 'sha1', 'sha224', 'sha256', 'sha384', 'sha512',
           'hmac_md5', 'hmac_sha1', 'hmac_sha256',
           'generate_key', 'generate_token']

import hashlib
import hmac
import secrets
import binascii
from typing import Any, Callable, Type, Dict, Optional, Union


class CryptoRegistry:
    """
    加密算法注册中心
    
    提供加密解密器的注册、查询和管理功能。
    
    Example:
        # 注册自定义加密解密器
        CryptoRegistry.register_encryptor('custom', custom_encrypt)
        CryptoRegistry.register_decryptor('custom', custom_decrypt)
        
        # 查询支持的算法
        algorithms = CryptoRegistry.supported_algorithms()
        
        # 获取加密解密器
        encryptor = CryptoRegistry.get_encryptor('sha256')
        decryptor = CryptoRegistry.get_decryptor('custom')
        
        # 使用加密解密器
        encrypted = encryptor(data)
        decrypted = decryptor(encrypted_data, key)
    """
    
    _encryptors: Dict[str, Callable] = {}
    _decryptors: Dict[str, Callable] = {}
    
    @classmethod
    def register_encryptor(cls, algorithm_name: str, encryptor: Callable) -> None:
        """
        注册加密器
        
        Args:
            algorithm_name: 算法名称（如 'sha256', 'aes', 'custom'）
            encryptor: 加密函数，接受数据和可选参数并返回加密结果
        
        Example:
            def custom_encrypt(data, key=None):
                # 自定义加密逻辑
                return encrypted_data
            
            CryptoRegistry.register_encryptor('custom', custom_encrypt)
        """
        cls._encryptors[algorithm_name] = encryptor
    
    @classmethod
    def register_decryptor(cls, algorithm_name: str, decryptor: Callable) -> None:
        """
        注册解密器
        
        Args:
            algorithm_name: 算法名称（如 'aes', 'custom'）
            decryptor: 解密函数，接受加密数据和可选参数并返回原始数据
        
        Example:
            def custom_decrypt(data, key=None):
                # 自定义解密逻辑
                return decrypted_data
            
            CryptoRegistry.register_decryptor('custom', custom_decrypt)
        """
        cls._decryptors[algorithm_name] = decryptor
    
    @classmethod
    def get_encryptor(cls, algorithm_name: str) -> Optional[Callable]:
        """
        获取加密器
        
        Args:
            algorithm_name: 算法名称
        
        Returns:
            加密器函数，如果未找到返回 None
        """
        return cls._encryptors.get(algorithm_name)
    
    @classmethod
    def get_decryptor(cls, algorithm_name: str) -> Optional[Callable]:
        """
        获取解密器
        
        Args:
            algorithm_name: 算法名称
        
        Returns:
            解密器函数，如果未找到返回 None
        """
        return cls._decryptors.get(algorithm_name)
    
    @classmethod
    def supported_algorithms(cls) -> list:
        """
        获取支持的算法列表
        
        Returns:
            所有已注册算法的列表
        """
        return list(set(cls._encryptors.keys()) | set(cls._decryptors.keys()))
    
    @classmethod
    def is_algorithm_supported(cls, algorithm_name: str) -> bool:
        """
        检查算法是否支持
        
        Args:
            algorithm_name: 算法名称
        
        Returns:
            如果算法已注册返回 True，否则返回 False
        """
        return algorithm_name in cls._encryptors or algorithm_name in cls._decryptors
    
    @classmethod
    def register_crypto(cls, algorithm_name: str, encryptor: Callable, decryptor: Callable = None) -> None:
        """
        同时注册加密器和解密器
        
        Args:
            algorithm_name: 算法名称
            encryptor: 加密函数
            decryptor: 解密函数（可选，某些算法如 hash 不需要解密）
        
        Example:
            CryptoRegistry.register_crypto('aes', aes_encrypt, aes_decrypt)
        """
        cls.register_encryptor(algorithm_name, encryptor)
        if decryptor:
            cls.register_decryptor(algorithm_name, decryptor)
    
    @classmethod
    def unregister_algorithm(cls, algorithm_name: str) -> None:
        """
        注销算法
        
        Args:
            algorithm_name: 要注销的算法名称
        """
        cls._encryptors.pop(algorithm_name, None)
        cls._decryptors.pop(algorithm_name, None)
    
    @classmethod
    def get_encryptors(cls) -> Dict[str, Callable]:
        """
        获取所有加密器
        
        Returns:
            加密器字典 {algorithm_name: encryptor_func}
        """
        return cls._encryptors.copy()
    
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

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
    def get_decryptors(cls) -> Dict[str, Callable]:
        """
        获取所有解密器
        
        Returns:
            解密器字典 {algorithm_name: decryptor_func}
        """
        return cls._decryptors.copy()


def encryptable(algorithm_name: str):
    """
    装饰器：标记函数为加密器
    
    将装饰的函数注册到 CryptoRegistry 中，作为指定算法的加密器。
    
    Args:
        algorithm_name: 算法名称
        
    Example:
        @encryptable('custom')
        def custom_encrypt(data, key=None):
            # 自定义加密逻辑
            return encrypted_data
        
        # 使用
        encryptor = CryptoRegistry.get_encryptor('custom')
        result = encryptor('secret data', key='mykey')
    """
    def decorator(func: Callable) -> Callable:
        CryptoRegistry.register_encryptor(algorithm_name, func)
        return func
    return decorator


def decryptable(algorithm_name: str):
    """
    装饰器：标记函数为解密器
    
    将装饰的函数注册到 CryptoRegistry 中，作为指定算法的解密器。
    
    Args:
        algorithm_name: 算法名称
        
    Example:
        @decryptable('custom')
        def custom_decrypt(data, key=None):
            # 自定义解密逻辑
            return decrypted_data
        
        # 使用
        decryptor = CryptoRegistry.get_decryptor('custom')
        result = decryptor(encrypted_data, key='mykey')
    """
    def decorator(func: Callable) -> Callable:
        CryptoRegistry.register_decryptor(algorithm_name, func)
        return func
    return decorator


class CryptoMeta(type):
    """加密器元类"""
    
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



class Encryptor(metaclass=CryptoMeta):
    """
    加密器类 - 提供链式调用的加密操作
    
    支持的操作：
    - md5(): MD5 哈希
    - sha1(): SHA-1 哈希
    - sha224(): SHA-224 哈希
    - sha256(): SHA-256 哈希
    - sha384(): SHA-384 哈希
    - sha512(): SHA-512 哈希
    - hmac_md5(key): HMAC-MD5
    - hmac_sha1(key): HMAC-SHA1
    - hmac_sha256(key): HMAC-SHA256
    - encrypt(algorithm, **kwargs): 使用已注册的自定义加密器
    
    Example:
        # 基本使用
        e = Encryptor('hello world')
        result = e.sha256().data  # 哈希值
        
        # 链式调用（注意：hash 算法通常不需要链式）
        e = Encryptor('data')
        result = e.hmac_sha256(key='secret').data
        
        # 使用自定义加密器（需先注册）
        @encryptable('custom')
        def custom_encrypt(data, key):
            return data + key
        
        e = Encryptor('hello').encrypt('custom', key='world').data
    """
    
    def __init__(self, data: Any):
        """
        初始化加密器
        
        Args:
            data: 要加密的数据
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
        """应用加密函数"""
        try:
            self._data = func(self._data, **kwargs)
            self._history.append(name)
            return self
        except Exception as e:
            raise ValueError(f"Failed to apply {name}: {e}")
    
    def md5(self):
        """
        MD5 哈希
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encryptor('hello').md5().data  # md5 hash
        """
        return self._apply(self._md5, 'md5')
    
    def sha1(self):
        """
        SHA-1 哈希
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encryptor('hello').sha1().data  # sha1 hash
        """
        return self._apply(self._sha1, 'sha1')
    
    def sha224(self):
        """
        SHA-224 哈希
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encryptor('hello').sha224().data  # sha224 hash
        """
        return self._apply(self._sha224, 'sha224')
    
    def sha256(self):
        """
        SHA-256 哈希
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encryptor('hello').sha256().data  # sha256 hash
        """
        return self._apply(self._sha256, 'sha256')
    
    def sha384(self):
        """
        SHA-384 哈希
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encryptor('hello').sha384().data  # sha384 hash
        """
        return self._apply(self._sha384, 'sha384')
    
    def sha512(self):
        """
        SHA-512 哈希
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encryptor('hello').sha512().data  # sha512 hash
        """
        return self._apply(self._sha512, 'sha512')
    
    def hmac_md5(self, key: Union[str, bytes]):
        """
        HMAC-MD5
        
        Args:
            key: HMAC 密钥
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encryptor('hello').hmac_md5(key='secret').data
        """
        return self._apply(self._hmac_md5, 'hmac_md5', key=key)
    
    def hmac_sha1(self, key: Union[str, bytes]):
        """
        HMAC-SHA1
        
        Args:
            key: HMAC 密钥
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encryptor('hello').hmac_sha1(key='secret').data
        """
        return self._apply(self._hmac_sha1, 'hmac_sha1', key=key)
    
    def hmac_sha256(self, key: Union[str, bytes]):
        """
        HMAC-SHA256
        
        Args:
            key: HMAC 密钥
        
        Returns:
            self，支持链式调用
        
        Example:
            result = Encryptor('hello').hmac_sha256(key='secret').data
        """
        return self._apply(self._hmac_sha256, 'hmac_sha256', key=key)
    
    def encrypt(self, algorithm_name: str, **kwargs):
        """
        使用已注册的加密器进行加密
        
        通过 CryptoRegistry 获取指定算法的加密器并应用。
        
        Args:
            algorithm_name: 算法名称（需先注册）
            **kwargs: 传递给加密器的额外参数
        
        Returns:
            self，支持链式调用
        
        Raises:
            ValueError: 如果算法未注册
        
        Example:
            @encryptable('custom')
            def custom_encrypt(data, key):
                return data + key
            
            result = Encryptor('hello').encrypt('custom', key='world').data
        """
        encryptor = CryptoRegistry.get_encryptor(algorithm_name)
        if encryptor is None:
            raise ValueError(f"Unknown encrypt algorithm: {algorithm_name}. "
                           f"Supported algorithms: {CryptoRegistry.supported_algorithms()}")
        
        def wrapper(data, **kw):
            return encryptor(data, **kw)
        
        return self._apply(wrapper, algorithm_name, **kwargs)
    
    @staticmethod
    def _hash(data: Any, algorithm: str) -> str:
        """通用哈希函数"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        h = hashlib.new(algorithm)
        h.update(data)
        return h.hexdigest()
    
    @staticmethod
    def _md5(data: Any) -> str:
        return Encryptor._hash(data, 'md5')
    
    @staticmethod
    def _sha1(data: Any) -> str:
        return Encryptor._hash(data, 'sha1')
    
    @staticmethod
    def _sha224(data: Any) -> str:
        return Encryptor._hash(data, 'sha224')
    
    @staticmethod
    def _sha256(data: Any) -> str:
        return Encryptor._hash(data, 'sha256')
    
    @staticmethod
    def _sha384(data: Any) -> str:
        return Encryptor._hash(data, 'sha384')
    
    @staticmethod
    def _sha512(data: Any) -> str:
        return Encryptor._hash(data, 'sha512')
    
    @staticmethod
    def _hmac(data: Any, key: Union[str, bytes], algorithm: str) -> str:
        """通用 HMAC 函数"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        if isinstance(key, str):
            key = key.encode('utf-8')
        # 获取哈希函数，而不是创建哈希对象
        hash_func = getattr(hashlib, algorithm)
        h = hmac.new(key, data, hash_func)
        return h.hexdigest()
    
    @staticmethod
    def _hmac_md5(data: Any, key: Union[str, bytes]) -> str:
        return Encryptor._hmac(data, key, 'md5')
    
    @staticmethod
    def _hmac_sha1(data: Any, key: Union[str, bytes]) -> str:
        return Encryptor._hmac(data, key, 'sha1')
    
    @staticmethod
    def _hmac_sha256(data: Any, key: Union[str, bytes]) -> str:
        return Encryptor._hmac(data, key, 'sha256')
    
    def __repr__(self):
        return f"Encryptor(data={repr(self._data)}, history={self._history})"
    

    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)

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
    def __str__(self):
        return str(self._data)


class Decryptor(metaclass=CryptoMeta):
    """
    解密器类 - 提供链式调用的解密操作
    
    支持的操作：
    - decrypt(algorithm, **kwargs): 使用已注册的自定义解密器
    
    Note:
        大部分哈希算法是单向的，不支持解密。此类主要用于对称加密算法。
    
    Example:
        # 使用自定义解密器（需先注册）
        @decryptable('custom')
        def custom_decrypt(data, key):
            return data.replace(key, '')
        
        d = Decoder(encrypted_data).decrypt('custom', key='world').data
    """
    
    def __init__(self, data: Any):
        """
        初始化解密器
        
        Args:
            data: 要解密的数据
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
        """应用解密函数"""
        try:
            self._data = func(self._data, **kwargs)
            self._history.append(name)
            return self
        except Exception as e:
            raise ValueError(f"Failed to apply {name}: {e}")
    
    def decrypt(self, algorithm_name: str, **kwargs):
        """
        使用已注册的解密器进行解密
        
        通过 CryptoRegistry 获取指定算法的解密器并应用。
        
        Args:
            algorithm_name: 算法名称（需先注册）
            **kwargs: 传递给解密器的额外参数
        
        Returns:
            self，支持链式调用
        
        Raises:
            ValueError: 如果算法未注册
        
        Example:
            @decryptable('custom')
            def custom_decrypt(data, key):
                # 自定义解密逻辑
                return decrypted_data
            
            result = Decoder(encrypted_data).decrypt('custom', key='secret').data
        """
        decryptor = CryptoRegistry.get_decryptor(algorithm_name)
        if decryptor is None:
            raise ValueError(f"Unknown decrypt algorithm: {algorithm_name}. "
                           f"Supported algorithms: {CryptoRegistry.supported_algorithms()}")
        
        def wrapper(data, **kw):
            return decryptor(data, **kw)
        
        return self._apply(wrapper, algorithm_name, **kwargs)
    
    def __repr__(self):
        return f"Decryptor(data={repr(self._data)}, history={self._history})"
    
    def __str__(self):
        return str(self._data)

    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function applied after f (no return expected)

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


# 便捷函数
def md5(data: Any) -> str:
    """MD5 哈希"""
    return Encryptor._md5(data)


def sha1(data: Any) -> str:
    """SHA-1 哈希"""
    return Encryptor._sha1(data)


def sha224(data: Any) -> str:
    """SHA-224 哈希"""
    return Encryptor._sha224(data)


def sha256(data: Any) -> str:
    """SHA-256 哈希"""
    return Encryptor._sha256(data)


def sha384(data: Any) -> str:
    """SHA-384 哈希"""
    return Encryptor._sha384(data)


def sha512(data: Any) -> str:
    """SHA-512 哈希"""
    return Encryptor._sha512(data)


def hmac_md5(data: Any, key: Union[str, bytes]) -> str:
    """HMAC-MD5"""
    return Encryptor._hmac_md5(data, key)


def hmac_sha1(data: Any, key: Union[str, bytes]) -> str:
    """HMAC-SHA1"""
    return Encryptor._hmac_sha1(data, key)


def hmac_sha256(data: Any, key: Union[str, bytes]) -> str:
    """HMAC-SHA256"""
    return Encryptor._hmac_sha256(data, key)


def generate_key(length: int = 32) -> str:
    """
    生成安全随机密钥
    
    Args:
        length: 密钥长度（字节），默认为 32（256 位）
    
    Returns:
        十六进制编码的密钥字符串
    
    Example:
        key = generate_key(32)  # 64 字符的十六进制字符串
    """
    return binascii.hexlify(secrets.token_bytes(length)).decode('utf-8')


def generate_token(length: int = 32) -> str:
    """
    生成安全随机令牌
    
    Args:
        length: 令牌长度（字节），默认为 32
    
    Returns:
        URL 安全的 base64 编码令牌
    
    Example:
        token = generate_token()  # URL 安全的令牌
    """
    return secrets.token_urlsafe(length)


# 注册默认加密器
CryptoRegistry.register_encryptor('md5', md5)
CryptoRegistry.register_encryptor('sha1', sha1)
CryptoRegistry.register_encryptor('sha224', sha224)
CryptoRegistry.register_encryptor('sha256', sha256)
CryptoRegistry.register_encryptor('sha384', sha384)
CryptoRegistry.register_encryptor('sha512', sha512)
CryptoRegistry.register_encryptor('hmac_md5', hmac_md5)
CryptoRegistry.register_encryptor('hmac_sha1', hmac_sha1)
CryptoRegistry.register_encryptor('hmac_sha256', hmac_sha256)
