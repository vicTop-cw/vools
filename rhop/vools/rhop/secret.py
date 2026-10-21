"""vools.rhop.secret - 配置密文工具（明文 ↔ RHOP-ENC 密文）

配置里的敏感信息（密码 / token / 密钥）支持**明文与密文双区**：
运行时只要明文区非空就用明文（并打警告），否则用密文区。本工具负责生成密文：

    # 1) 生成密文（密钥来源：--key > --key-file > 环境变量 RHOP_KEY）
    python -m vools.rhop.secret enc "my-plain-password"
    # 2) 把输出的 RHOP-ENC:... 填到配置的 *_cipher 字段，并把 *_plain 置空
    # 3) 需要核对时反解
    python -m vools.rhop.secret dec "RHOP-ENC:..."
    # 4) 没有密钥时先生成一个（写进环境变量或密钥文件，勿提交进版本库）
    python -m vools.rhop.secret keygen

密钥只从 --key / --key-file / 环境变量读取，代码里不落明文密钥。
"""

from __future__ import absolute_import

import argparse
import base64
import os
import sys
from typing import List, Optional

from .crypto import ENV_RHOP_KEY, RhopCrypto, load_key


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m vools.rhop.secret",
        description="rhop 配置密文工具：生成/还原 RHOP-ENC 密文",
    )
    sub = parser.add_subparsers(dest="command")

    def _add_key_args(p):
        p.add_argument("--key", default=None, help="直接给密钥文本（优先级最高）")
        p.add_argument("--key-file", default=None, help="从文件读密钥")
        p.add_argument("--env", default=ENV_RHOP_KEY,
                       help="密钥所在环境变量名（默认 %s）" % ENV_RHOP_KEY)

    p_enc = sub.add_parser("enc", help="明文 → RHOP-ENC 密文")
    p_enc.add_argument("plaintext", help="要加密的明文")
    _add_key_args(p_enc)

    p_dec = sub.add_parser("dec", help="RHOP-ENC 密文 → 明文")
    p_dec.add_argument("ciphertext", help="要解密的密文（RHOP-ENC:...）")
    _add_key_args(p_dec)

    p_key = sub.add_parser("keygen", help="生成一个随机密钥（32 字节 urlsafe base64）")
    p_key.add_argument("--out", default=None, help="写入文件（缺省打印到 stdout）")

    return parser


def _load_crypto(args) -> RhopCrypto:
    """按 --key > --key-file > 环境变量 的优先级构造 RhopCrypto。"""
    key = load_key(source=args.key, path=args.key_file, env_name=args.env)
    return RhopCrypto(key)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口，返回退出码（0 成功 / 1 失败 / 2 参数错误）。"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    if args.command == "keygen":
        key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(key)
            sys.stderr.write("[rhop-secret] 密钥已写入 %s（请勿提交进版本库）\n" % args.out)
        else:
            print(key)
        return 0

    try:
        crypto = _load_crypto(args)
    except Exception as exc:
        sys.stderr.write("[rhop-secret] 取密钥失败: %s\n" % exc)
        return 1

    try:
        if args.command == "enc":
            print(crypto.encrypt_secret(args.plaintext))
        elif args.command == "dec":
            print(crypto.decrypt_secret(args.ciphertext))
        else:  # pragma: no cover - argparse 已挡住
            parser.print_help()
            return 2
    except Exception as exc:
        sys.stderr.write("[rhop-secret] 失败: %s\n" % exc)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())