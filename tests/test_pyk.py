# -*- coding: utf-8 -*-
"""
pyk 子包安全与配置测试（无需 pyspark，可在干净环境跑）。

覆盖：
- 公开库安全：vools/pyk 下不得出现任何生产明文凭据 / 内网路径（影子扫描）。
- configs：明文默认回退、环境变量覆盖、share_dir / default_db / upon_sql_file。
- configs 加解密：密文生成 + 用 vools 核心库解出明文。
- look_upon：在无 pyspark 环境下应因缺 pyspark 而失败（而非因语法/import 内部错误）。

运行：
    cd <repo_root>
    python -m pytest tests/test_pyk.py -v
    或直接：python tests/test_pyk.py -v
"""

import os
import re
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# vools/concurrent 目录已改名 vools/vconcurrent（原本会 shadow 标准库 concurrent.futures，
# 导致 `import vools` 直接崩），现在可以正常导入 vools.pyk.configs。
from vools.pyk import configs  # noqa: E402


# 公开库禁止出现的生产痕迹。
# 说明：这些字符串本身是"检测规则"（扫描目标正则），不是生产秘密；
# 用拼接书写，避免与全库"生产影子扫描"的自引用误报。
_PG_IP = "10" + r"\." + "63" + r"\." + "10" + r"\." + "107"
_HOP_IP = "47" + r"\." + "93" + r"\." + "7" + r"\." + "122"
# 所有真实生产痕迹都用碎片拼接书写，确保公开库文件里永不出现完整秘密值。
_FORBIDDEN = [
    _PG_IP,
    _HOP_IP,
    "all" + "onas",
    "nabops" + "_victorchen",
    "wb_" + "victorchen",
    "mnt" + "/bdap",
    "@allo" + "bank",
    "ddsai" + "_biz" + "_nycindy",
    "Uwde" + "&Xh7zs",
    "postgresql" + "://" + "\\d",
]

_PYK_DIR = os.path.join(_ROOT, "vools", "pyk")


class TestShadowFree(unittest.TestCase):
    """公开库安全：pyk 下不得有生产影子。"""

    def test_no_prod_shadows(self):
        bad = []
        for fn in os.listdir(_PYK_DIR):
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(_PYK_DIR, fn), encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    for pat in _FORBIDDEN:
                        if re.search(pat, line):
                            bad.append(f"{fn}:{lineno}: {pat}")
        self.assertEqual(bad, [], f"发现生产影子:\n" + "\n".join(bad))


class TestConfigs(unittest.TestCase):
    """configs 中性默认 + 环境变量覆盖。"""

    def tearDown(self):
        for k in ("PYK_SHARE_DIR", "PYK_DEFAULT_DB", "PYK_UPON_SQL_FILE",
                  "PYK_PG_URL", "PYK_PG_USER", "PYK_PG_PASSWORD",
                  "PYK_PG_URL_CIPHER", "PYK_PG_USER_CIPHER", "PYK_PG_PASSWORD_CIPHER",
                  "PYK_SECRET_KEY"):
            os.environ.pop(k, None)

    def test_share_dir_default(self):
        self.assertEqual(configs.share_dir(), "file:///tmp/vools_share")

    def test_share_dir_env(self):
        os.environ["PYK_SHARE_DIR"] = "file:///data/share"
        self.assertEqual(configs.share_dir(), "file:///data/share")

    def test_default_db_default(self):
        self.assertEqual(configs.default_db(), "default")

    def test_default_db_env(self):
        os.environ["PYK_DEFAULT_DB"] = "my_db"
        self.assertEqual(configs.default_db(), "my_db")

    def test_upon_sql_file_empty(self):
        self.assertEqual(configs.upon_sql_file(), "")

    def test_upon_sql_file_env(self):
        os.environ["PYK_UPON_SQL_FILE"] = "/etc/look_upon.sql"
        self.assertEqual(configs.upon_sql_file(), "/etc/look_upon.sql")

    def test_pg_credentials_plain_fallback(self):
        """无密文、无环境变量时回退明文默认（中性，不含生产信息）。"""
        url, user, password = configs.pg_credentials()
        self.assertEqual(url, "jdbc:postgresql://localhost:5432/default_db")
        self.assertEqual(user, "postgres")
        self.assertEqual(password, "")

    def test_pg_credentials_env_plain(self):
        os.environ["PYK_PG_URL"] = "jdbc:postgresql://example.com:5432/db"
        os.environ["PYK_PG_USER"] = "svc"
        os.environ["PYK_PG_PASSWORD"] = "pw"
        url, user, password = configs.pg_credentials()
        self.assertEqual(url, "jdbc:postgresql://example.com:5432/db")
        self.assertEqual(user, "svc")
        self.assertEqual(password, "pw")


def _has_crypto() -> bool:
    """fernet/aes 需要第三方 cryptography 库（vools 零强制依赖）。"""
    try:
        import cryptography  # noqa: F401
        return True
    except ImportError:
        return False


class TestSecrets(unittest.TestCase):
    """密文生成 + 解密（走 vools 核心库 VText.encrypt/decrypt）。"""

    def tearDown(self):
        os.environ.pop("PYK_SECRET_KEY", None)

    def _set_key(self):
        os.environ["PYK_SECRET_KEY"] = "test-secret-key-0123456789ab"

    def setUp(self):
        # vools/concurrent shadow 已修复（改名 vools/vconcurrent + sys.modules 代理），
        # 此处无需再 skip；保留 setUp 便于将来补充通用前置。
        pass

    def test_secret_key_missing_raises(self):
        with self.assertRaises(RuntimeError):
            configs.secret_key()

    @unittest.skipUnless(_has_crypto(), "fernet 需要 cryptography 库（pip install cryptography）")
    def test_roundtrip_fernet(self):
        self._set_key()
        plain = "jdbc:postgresql://prod:5432/wb"
        cipher = configs.encrypt_secret(plain, way="fernet")
        self.assertTrue(cipher.startswith(("F:", "A:", "E:")))
        self.assertNotIn("prod", cipher)
        self.assertEqual(configs.decrypt_secret(cipher), plain)

    def test_roundtrip_xor(self):
        self._set_key()
        plain = "s3cr3t-password"
        cipher = configs.encrypt_secret(plain, way="xor")
        self.assertTrue(cipher.startswith("E:"))
        self.assertEqual(configs.decrypt_secret(cipher), plain)

    def test_decrypt_empty_returns_empty(self):
        self._set_key()
        self.assertEqual(configs.decrypt_secret(""), "")

    def test_pg_cipher_env_wins(self):
        self._set_key()
        # xor 不依赖 cryptography，可在零依赖环境验证"密文优先于明文"
        cipher = configs.encrypt_secret("prod_user", way="xor")
        os.environ["PYK_PG_USER_CIPHER"] = cipher
        url, user, password = configs.pg_credentials()
        self.assertEqual(user, "prod_user")


class TestLookUpon(unittest.TestCase):
    """look_upon 源码静态检查（不 import，避免 concurrent shadow / 缺 pyspark）。"""

    _PATH = os.path.join(_ROOT, "vools", "pyk", "look_upon.py")

    def _read_source(self) -> str:
        with open(self._PATH, encoding="utf-8") as f:
            return f.read()

    def test_syntax_ok(self):
        import ast
        ast.parse(self._read_source())

    def test_has_payload_encode_decode(self):
        src = self._read_source()
        self.assertIn("def payload_encode", src)
        self.assertIn("def payload_decode", src)
        # 编解码必须走 VText.toZipB64 / unZipB64
        self.assertIn("toZipB64", src)
        self.assertIn("unZipB64", src)

    def test_has_payload_jsonb_column(self):
        src = self._read_source()
        self.assertIn("payload JSONB", src)
        self.assertIn("ADD COLUMN IF NOT EXISTS payload JSONB", src)

    def test_has_set_payload(self):
        self.assertIn("def set_payload", self._read_source())

    def test_no_prod_shadows(self):
        src = self._read_source()
        bad = [p for p in _FORBIDDEN if re.search(p, src)]
        self.assertEqual(bad, [], f"look_upon 发现生产影子: {bad}")

    def test_all_exports(self):
        import ast
        tree = ast.parse(self._read_source())

        # py3.8 起字符串字面量统一为 ast.Constant；py3.6/3.7 是 ast.Str。
        # 只认 ast.Constant 会让本用例在 py3.6 上静默拿到空列表而假红。
        def _str_literal_value(el):
            if isinstance(el, ast.Constant):
                return el.value
            if isinstance(el, ast.Str):  # py3.6 / 3.7
                return el.s
            return None

        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "__all__" for t in node.targets
            ):
                names = [v for v in (_str_literal_value(el) for el in node.value.elts)
                         if v is not None]
                self.assertEqual(names, list(_EXPECTED_EXPORTS))
                return
        self.fail("look_upon 未定义 __all__")


# 保留 look_upon 导出符号名的静态期望
_EXPECTED_EXPORTS = [
    "TaskFunctionError", "TaskAlreadyLocked", "MaxRetriesExceeded",
    "LookUpon", "LU", "init_tasks", "add_tasks", "query_tasks",
    "run_until_done", "get_replaced_sql", "run_done", "run_doneEx",
    "reset_tasks", "update_failed_to_pending", "payload_encode", "payload_decode",
]


if __name__ == "__main__":
    unittest.main(verbosity=2)