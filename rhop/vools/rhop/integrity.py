"""vools.rhop.integrity - 信封完整性校验

checksum 比对 + 文件大小校验（供 SFTP / Git 传输中断检测）。
"""

from typing import Tuple

from .envelope import Envelope


class IntegrityChecker:
    """信封完整性校验：checksum 比对 + 文件大小校验。"""

    @staticmethod
    def verify(env: Envelope, raw_bytes: bytes) -> Tuple[bool, str]:
        """校验信封字节是否完整。

        返回 (bool, error_msg)。
        """
        try:
            restored = Envelope.from_rhop_bytes(raw_bytes)
            return True, ""
        except ValueError as e:
            return False, str(e)

    @staticmethod
    def verify_bytes(raw_bytes: bytes) -> Tuple[bool, str]:
        """直接校验 .rhop 字节（不依赖 Envelope 对象）。"""
        try:
            Envelope.from_rhop_bytes(raw_bytes)
            return True, ""
        except ValueError as e:
            return False, str(e)

    @staticmethod
    def checksum_match(env: Envelope) -> bool:
        """校验 Envelope 对象的 checksum 是否与内容匹配。"""
        try:
            restored = Envelope.from_rhop_bytes(env.to_rhop_bytes())
            return restored.checksum == env.checksum
        except ValueError:
            return False
