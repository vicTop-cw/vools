"""vools.security.otp —— 双因素动态码算法（HOTP/TOTP 变体）。

供 Actus Vault 等安全子系统调用。
不依赖外部库，纯 Python 标准库实现。

算法：
    1. 时间窗口计数 = floor(当前Unix时间戳 / time_step)
    2. 种子 = HMAC-SHA256(密钥=seed_key, 消息=struct.pack(">Q", counter))
    3. 动态码 = HOTP-Truncate(种子, digits)
    4. 完整密钥 = PBKDF2-HMAC-SHA256(pin + dynamic_code, salt, iterations, dklen=32)

API:
    generate_dynamic_code(seed_key, time_step=60, digits=6) -> str
    verify_dynamic_code(code, seed_key, time_step=60, window=1, used_codes=None) -> bool
    derive_master_key(pin, dynamic_code, salt, iterations=100000) -> bytes
    generate_seed_key() -> bytes
"""

import hashlib
import hmac
import secrets
import struct
import time

__all__ = [
    "generate_dynamic_code",
    "verify_dynamic_code",
    "derive_master_key",
    "generate_seed_key",
]


def generate_dynamic_code(seed_key: bytes, time_step: int = 60, digits: int = 6) -> str:
    """生成当前时间窗口的动态码。

    Args:
        seed_key: 种子密钥（bytes，建议 >= 32 bytes）
        time_step: 时间窗口秒数（默认 60）
        digits: 动态码位数（默认 6）

    Returns:
        纯数字字符串，如 "123456"
    """
    counter = int(time.time()) // time_step
    return _hotp_truncate(seed_key, counter, digits)


def verify_dynamic_code(
    code: str,
    seed_key: bytes,
    time_step: int = 60,
    window: int = 1,
    used_codes: set = None,
) -> bool:
    """验证动态码，支持前后窗口容错。

    Args:
        code: 用户输入的动态码
        seed_key: 种子密钥
        time_step: 时间窗口秒数
        window: 容错窗口数（默认 1，即当前窗口 ±1 窗口）
        used_codes: 已使用过的动态码集合（防重放）。如果提供，
                    验证成功后自动把当前 code 加入集合。

    Returns:
        bool: 验证是否通过
    """
    # 长度校验与 generate_dynamic_code 的 digits 语义对齐：_hotp_truncate 按
    # len(code) 位重算期望码，硬编码 6 会让 digits!=6 生成的码永远验证失败
    # （BUG-201）。isdigit 已防非数字，这里只设合理上限防滥用。
    if not code or not code.isdigit() or not 1 <= len(code) <= 10:
        return False

    # 防重放：已用过的动态码直接拒绝（否则同一码在时间窗内可无限重放）
    if used_codes is not None and code in used_codes:
        return False

    current_counter = int(time.time()) // time_step
    for offset in range(-window, window + 1):
        expected = _hotp_truncate(seed_key, current_counter + offset, len(code))
        if hmac.compare_digest(code, expected):
            if used_codes is not None:
                used_codes.add(code)
            return True
    return False


def derive_master_key(
    pin: str, dynamic_code: str, salt: bytes, iterations: int = 100000, dklen: int = 32
) -> bytes:
    """派生主密钥（PBKDF2-HMAC-SHA256）。

    Args:
        pin: 6 位 PIN 码
        dynamic_code: 6 位动态码
        salt: 随机盐值（bytes）
        iterations: 迭代次数（默认 100000）
        dklen: 派生密钥长度（默认 32 bytes = AES-256）

    Returns:
        bytes: 派生的主密钥
    """
    password = (pin + dynamic_code).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", password, salt, iterations, dklen)


def generate_seed_key(length: int = 32) -> bytes:
    """生成随机种子密钥。"""
    return secrets.token_bytes(length)


# ── 内部 ──

def _hotp_truncate(seed_key: bytes, counter: int, digits: int = 6) -> str:
    """HOTP 截断算法（RFC 4226）。"""
    msg = struct.pack(">Q", counter)
    digest = hmac.new(seed_key, msg, hashlib.sha256).digest()
    # 取最后 4 字节的低 31 位
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    # 模 10^digits，补零
    return str(code % (10 ** digits)).zfill(digits)
