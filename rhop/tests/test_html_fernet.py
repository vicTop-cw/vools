"""静态 HTML 配置生成器的密码学互通测试。

页面里的"生成密文"用纯 JS 实现 Fernet（PBKDF2-HMAC-SHA256 + AES-128-CBC + HMAC-SHA256），
必须与 Python 侧 ``vools.rhop.crypto`` 字节兼容，否则页面上生成的密文到了运行时解不开。
本测试把 HTML 内联脚本抽出来交给 Node 跑，做**双向**验证（无 node 时跳过并说明原因）。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

from vools.rhop.crypto import RhopCrypto, SECRET_PREFIX

HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "tools", "config_generator.html")

#: 覆盖 ASCII / 中文 / emoji（代理对）/ 特殊字符 / 长文本 / 单字符
PAYLOADS = [
    ("ascii", "rhop-secret-123"),
    ("cjk", "跨机密文-密码"),
    ("emoji", "emoji-\U0001F600-\U0001F1E8\U0001F1F3"),
    ("special", 'quote" back\\slash tab\t newline\npunct;|&$'),
    ("single", "x"),
    ("long", "长" * 500),
]

KEY = "html-unit-key"


def _html() -> str:
    with open(HTML_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def _extract_crypto_script() -> str:
    match = re.search(r'<script id="rhop-crypto">(.*?)</script>', _html(), re.S)
    assert match, "HTML 里找不到 id=rhop-crypto 的脚本块"
    return match.group(1)


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("未找到 node，可选的 JS↔Python 密文互通交叉验证跳过")
    return node


def _run_node(driver: str, js_module: str, job: dict) -> dict:
    """跑一次 Node 驱动脚本，返回解析后的 JSON 结果。"""
    node = _node()
    work = tempfile.mkdtemp(prefix="rhop-html-")
    job_path = os.path.join(work, "job.json")
    with open(job_path, "w", encoding="utf-8") as fh:
        json.dump(job, fh, ensure_ascii=False)
    proc = subprocess.run([node, driver, js_module, job_path],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise AssertionError("node 执行失败: %s" % (proc.stderr or proc.stdout))
    return json.loads(proc.stdout)


DRIVER = """
const fs = require("fs");
const m = require(process.argv[2]);
const job = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const out = { results: [], meta: {} };
if (job.mode === "selftest") {
  out.meta.self = m.selfTest(job.items[0].key);
}
for (const item of job.items) {
  const r = { name: item.name };
  try {
    if (job.mode === "roundtrip") {
      const enc = m.encryptSecret(item.key, item.plain);
      r.enc = enc;
      r.dec = m.decryptSecret(item.key, enc);
      r.ok = r.dec === item.plain;
    } else if (job.mode === "derive") {
      r.derived = m.deriveFernetKey(item.key);
    } else if (job.mode === "decrypt") {
      r.dec = m.decryptSecret(item.key, item.cipher);
      r.ok = r.dec === item.plain;
    }
  } catch (e) {
    r.error = String((e && e.message) || e);
  }
  out.results.push(r);
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def js_env(tmp_path_factory):
    """把 HTML 内联脚本与 Node 驱动脚本落到临时目录（模块级复用）。"""
    work = tmp_path_factory.mktemp("html-js")
    js_path = str(work / "rhop_crypto.js")
    with open(js_path, "w", encoding="utf-8") as fh:
        fh.write(_extract_crypto_script())
    driver_path = str(work / "driver.js")
    with open(driver_path, "w", encoding="utf-8") as fh:
        fh.write(DRIVER)
    return {"module": js_path, "driver": driver_path}


class TestHtmlStructure:
    def test_file_exists_and_is_self_contained(self):
        html = _html()
        assert "vools-rhop 配置生成器" in html
        # 不引用任何外部资源（file:// 离线可用）
        assert not re.search(r'<(script|link)[^>]+(src|href)="https?://', html)

    def test_direction_options_are_only_abc(self):
        html = _html()
        section = html.split('<select id="role">', 1)[1].split("</select>", 1)[0]
        values = re.findall(r'value="([^"]+)"', section)
        assert values == ["A", "B", "C"]

    def test_no_hop_role_values_in_page(self):
        """页面里不提供 P0..P3 作为可选值（说明性文字里提到它们是可以的）。"""
        html = _html()
        assert not re.search(r'value\s*=\s*"p[0-3]"', html, re.I)
        assert not re.search(r'(role|direction)\s*=\s*"p[0-3]"', html, re.I)
        # 方向选项只有 A/B/C
        section = html.split('<select id="role">', 1)[1].split("</select>", 1)[0]
        assert re.findall(r'value="([^"]+)"', section) == ["A", "B", "C"]

    def test_store_kinds_offered(self):
        html = _html()
        section = html.split('<select id="storeKind">', 1)[1].split("</select>", 1)[0]
        assert 'value="sqlite-shared"' in section
        assert 'value="sqlite-local"' in section
        assert "postgres" in section          # 自定义 kind 入口（为后续后端留口）

    def test_required_controls_present(self):
        html = _html()
        for control in ('id="secretKey"', 'class="btn-encrypt"', 'id="btnDownload"',
                        'id="btnGenerate"', 'id="sharedWrite"', 'id="hbInterval"',
                        'id="hbStale"', 'id="execAllow"', 'id="execAllowAny"'):
            assert control in html, "缺少控件 %s" % control

    def test_plaintext_warning_text_present(self):
        html = _html()
        assert "python -m vools.rhop.secret enc" in html
        assert "明文区" in html and "密文区" in html

    def test_crypto_block_exports_api(self):
        js = _extract_crypto_script()
        for name in ("encryptSecret", "decryptSecret", "deriveFernetKey", "selfTest",
                     "fernetEncrypt", "fernetDecrypt"):
            assert name in js
        assert "module.exports" in js


class TestCryptoInterop:
    def test_js_encrypts_python_decrypts(self, js_env):
        job = {"mode": "roundtrip",
               "items": [{"name": name, "key": KEY, "plain": plain}
                         for name, plain in PAYLOADS]}
        out = _run_node(js_env["driver"], js_env["module"], job)
        crypto = RhopCrypto(KEY)
        for item, result in zip(PAYLOADS, out["results"]):
            name, plain = item
            assert "error" not in result, "%s: %s" % (name, result.get("error"))
            assert result["ok"] is True, "%s: JS 自身往返失败" % name
            assert result["enc"].startswith(SECRET_PREFIX)
            assert crypto.decrypt_secret(result["enc"]) == plain, "%s: Python 解不开 JS 密文" % name

    def test_python_encrypts_js_decrypts(self, js_env):
        crypto = RhopCrypto(KEY)
        items = [{"name": name, "key": KEY, "plain": plain,
                  "cipher": crypto.encrypt_secret(plain)} for name, plain in PAYLOADS]
        out = _run_node(js_env["driver"], js_env["module"],
                        {"mode": "decrypt", "items": items})
        for (name, plain), result in zip(PAYLOADS, out["results"]):
            assert "error" not in result, "%s: %s" % (name, result.get("error"))
            assert result["ok"] is True, "%s: JS 解不开 Python 密文" % name
            assert result["dec"] == plain

    def test_derived_key_matches_python(self, js_env):
        import base64
        import hashlib
        out = _run_node(js_env["driver"], js_env["module"],
                        {"mode": "derive", "items": [{"name": "k", "key": KEY}]})
        # 与运行时 vools.data.vtext.VText 的 Fernet 派生逐字节一致：
        #   PBKDF2-HMAC-SHA256(key, salt=sha256(key)[:16], iterations=200000, dkLen=32)
        # 页面必须对齐运行时（运行时才是解密方），否则页面生成的密文运行时解不开。
        key_bytes = KEY.encode("utf-8")
        digest = hashlib.pbkdf2_hmac("sha256", key_bytes,
                                     hashlib.sha256(key_bytes).digest()[:16],
                                     200000, 32)
        expected = base64.urlsafe_b64encode(digest).decode("ascii")
        assert out["results"][0]["derived"] == expected

    def test_wrong_key_fails_closed(self, js_env):
        crypto = RhopCrypto(KEY)
        cipher = crypto.encrypt_secret("top-secret")
        out = _run_node(js_env["driver"], js_env["module"],
                        {"mode": "decrypt",
                         "items": [{"name": "wrong", "key": "another-key",
                                    "cipher": cipher, "plain": "top-secret"}]})
        result = out["results"][0]
        assert result.get("ok") is not True
        assert "error" in result
        assert "HMAC" in result["error"] or "校验" in result["error"]

    def test_non_cipher_input_rejected(self, js_env):
        out = _run_node(js_env["driver"], js_env["module"],
                        {"mode": "decrypt",
                         "items": [{"name": "plain", "key": KEY,
                                    "cipher": "just-a-plain-string", "plain": "x"}]})
        assert "error" in out["results"][0]

    def test_page_self_test_passes(self, js_env):
        out = _run_node(js_env["driver"], js_env["module"],
                        {"mode": "selftest", "items": [{"name": "self", "key": KEY}]})
        assert out["meta"]["self"]["ok"] is True


class TestGeneratedConfigCompatibility:
    def test_python_can_load_config_with_page_generated_cipher(self, js_env, tmp_path):
        """端到端：页面生成的密文填进配置，Python 侧能正常解密使用。"""
        from vools.rhop.task.config import TaskConfig

        out = _run_node(js_env["driver"], js_env["module"],
                        {"mode": "roundtrip",
                         "items": [{"name": "pw", "key": KEY, "plain": "sftp-password"}]})
        cipher = out["results"][0]["enc"]

        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "B", "key": KEY, "shared": {"write": str(tmp_path)},
             "online": [{"kind": "sftp", "host": "h", "password_cipher": cipher}],
             "queue": {"store": {"kind": "sqlite-local"}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        assert cfg.resolved["online"][0]["password"] == "sftp-password"

    def test_cli_secret_command_round_trips_with_page_cipher(self, js_env):
        """页面密文与 `python -m vools.rhop.secret` 输出必须互相可解。"""
        from vools.rhop.secret import main as secret_main
        out = _run_node(js_env["driver"], js_env["module"],
                        {"mode": "roundtrip",
                         "items": [{"name": "pw", "key": KEY, "plain": "shared-secret"}]})
        js_cipher = out["results"][0]["enc"]

        # Python CLI 反解页面密文（用 --key 显式指定密钥）
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = secret_main(["dec", js_cipher, "--key", KEY])
        assert code == 0
        assert buffer.getvalue().strip() == "shared-secret"

        # Python CLI 生成的密文，页面也能解
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert secret_main(["enc", "cli-secret", "--key", KEY]) == 0
        cli_cipher = buffer.getvalue().strip()
        out2 = _run_node(js_env["driver"], js_env["module"],
                         {"mode": "decrypt",
                          "items": [{"name": "cli", "key": KEY, "cipher": cli_cipher,
                                     "plain": "cli-secret"}]})
        assert out2["results"][0]["ok"] is True