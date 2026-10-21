"""MVP 判据 1: 本地固定密钥能对 JSON 加密，且解密验证通过/失败可明确区分。"""

import json

import pytest

from vools.rhop.crypto import RhopCrypto, VerifyResult, load_key

KEY_A = "fixed-local-key-甲"
KEY_B = "other-key-乙"


class TestCryptoRoundtrip:
    def test_encrypt_json_returns_text(self):
        c = RhopCrypto.from_key(KEY_A)
        out = c.encrypt_json({"task": "demo", "n": 42})
        assert isinstance(out, str)
        # 输出是加密 JSON 文本（可 json 解析的信封）
        env = json.loads(out)
        assert env["v"] == 1
        assert env["alg"] == "fernet"
        assert isinstance(env["ct"], str)

    def test_roundtrip_ok(self):
        c = RhopCrypto.from_key(KEY_A)
        payload = {"task": "demo", "cmd": ["echo", "hi"], "ok": True}
        token = c.encrypt_json(payload)
        result = c.decrypt_verify(token)
        assert result.ok is True
        assert result.reason == "OK"
        assert result.payload == payload

    def test_string_payload_roundtrip(self):
        c = RhopCrypto.from_key(KEY_A)
        token = c.encrypt_json("hello rhop")
        result = c.decrypt_verify(token)
        assert result.ok is True
        assert result.payload["__text__"] == "hello rhop"

    def test_wrong_key_fails_distinctly(self):
        enc = RhopCrypto.from_key(KEY_A)
        dec = RhopCrypto.from_key(KEY_B)
        token = enc.encrypt_json({"task": "demo"})
        result = dec.decrypt_verify(token)
        assert result.ok is False
        assert result.reason == "BAD_TOKEN"

    def test_tampered_token_fails_distinctly(self):
        c = RhopCrypto.from_key(KEY_A)
        token = c.encrypt_json({"task": "demo"})
        # 篡改 ct 中的一个字符
        env = json.loads(token)
        ct = list(env["ct"])
        ct[3] = "A" if ct[3] != "A" else "B"
        env["ct"] = "".join(ct)
        tampered = json.dumps(env)
        result = c.decrypt_verify(tampered)
        assert result.ok is False
        assert result.reason == "BAD_TOKEN"

    def test_malformed_envelope(self):
        c = RhopCrypto.from_key(KEY_A)
        assert c.decrypt_verify("not json at all").reason == "MALFORMED"
        assert c.decrypt_verify('{"v": 99, "alg": "fernet", "ct": "x"}').reason == "MALFORMED"
        assert c.decrypt_verify('{"v": 1, "alg": "nope", "ct": "x"}').reason == "MALFORMED"
        assert c.decrypt_verify('{"v": 1, "alg": "fernet"}').reason == "MALFORMED"


class TestKeyLoading:
    def test_load_key_source_priority(self, monkeypatch):
        monkeypatch.setenv("RHOP_KEY", "from-env")
        assert load_key(source="from-arg") == "from-arg"
        assert load_key(source=b"bytes-key") == "bytes-key"
        # 无 source 时读环境变量
        assert load_key() == "from-env"

    def test_load_key_missing_raises(self, monkeypatch, tmp_path):
        monkeypatch.delenv("RHOP_KEY", raising=False)
        with pytest.raises(ValueError):
            load_key()

    def test_load_key_from_path(self, tmp_path):
        f = tmp_path / "key.txt"
        f.write_text("  file-key\n", encoding="utf-8")
        assert load_key(path=str(f)) == "file-key"

    def test_from_env_and_from_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("RHOP_KEY", "env-key")
        c = RhopCrypto.from_env()
        token = c.encrypt_json({"a": 1})
        assert c.decrypt_verify(token).ok
        f = tmp_path / "k.txt"
        f.write_text("path-key", encoding="utf-8")
        c2 = RhopCrypto.from_path(str(f))
        assert c2.decrypt_verify(c2.encrypt_json({"a": 1})).ok
