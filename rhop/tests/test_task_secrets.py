"""敏感信息明文/密文双支持测试：取值优先级、告警文案、严格模式、字段发现与打码。"""

import os

import pytest

from vools.rhop.crypto import RhopCrypto
from vools.rhop.task.errors import PlaintextSecretError, SecretError
from vools.rhop.task.secrets import (
    SECRET_ENC_COMMAND,
    find_secret_fields,
    is_sensitive_leaf,
    mask_value,
    resolve_config_secrets,
)


def _crypto(key="unit-key"):
    return RhopCrypto(key)


class TestPriority:
    def test_plain_wins_over_cipher(self):
        crypto = _crypto()
        cfg = {"sftp_password_plain": "from-plain",
               "sftp_password_cipher": crypto.encrypt_secret("from-cipher")}
        calls = []
        resolved, findings = resolve_config_secrets(cfg, crypto=crypto, warner=calls.append)
        assert resolved["sftp_password"] == "from-plain"
        assert len(calls) == 1
        assert findings[0]["action"] == "plaintext"

    def test_cipher_used_when_plain_empty(self):
        crypto = _crypto()
        cfg = {"sftp_password_plain": "", "sftp_password_cipher": crypto.encrypt_secret("sekret")}
        calls = []
        resolved, findings = resolve_config_secrets(cfg, crypto=crypto, warner=calls.append)
        assert resolved["sftp_password"] == "sekret"
        assert calls == []
        assert findings[0]["action"] == "cipher"

    def test_both_empty_yields_empty_string(self):
        cfg = {"sftp_password_plain": "", "sftp_password_cipher": ""}
        resolved, _ = resolve_config_secrets(cfg, crypto=_crypto(), warner=lambda m: None)
        assert resolved["sftp_password"] == ""

    def test_secret_node_prefers_plain(self):
        crypto = _crypto()
        cfg = {"token": {"plain": "node-plain", "cipher": crypto.encrypt_secret("node-cipher")}}
        calls = []
        resolved, _ = resolve_config_secrets(cfg, crypto=crypto, warner=calls.append)
        assert resolved["token"] == "node-plain"
        assert len(calls) == 1

    def test_secret_node_uses_path_when_no_plain_or_cipher(self, tmp_path):
        key_file = os.path.join(str(tmp_path), "k.txt")
        with open(key_file, "w", encoding="utf-8") as fh:
            fh.write("from-file\n")
        cfg = {"token": {"plain": "", "cipher": "", "path": key_file}}
        resolved, findings = resolve_config_secrets(cfg, warner=lambda m: None)
        assert resolved["token"] == "from-file"
        assert findings[0]["action"] == "path"

    def test_secret_node_uses_env(self, monkeypatch):
        monkeypatch.setenv("UNIT_TOKEN", "from-env")
        cfg = {"token": {"plain": "", "cipher": "", "env": "UNIT_TOKEN"}}
        resolved, findings = resolve_config_secrets(cfg, warner=lambda m: None)
        assert resolved["token"] == "from-env"
        assert findings[0]["action"] == "env"

    def test_missing_env_is_an_error(self):
        cfg = {"token": {"plain": "", "cipher": "", "env": "UNIT_NOT_SET_ANYWHERE"}}
        with pytest.raises(SecretError) as exc:
            resolve_config_secrets(cfg, warner=lambda m: None)
        assert "UNIT_NOT_SET_ANYWHERE" in str(exc.value)

    def test_env_only_dict_is_not_a_secret_node(self):
        """只有 env 的 dict 不算秘密节点（否则会误伤 exec.env 这类真·配置）。

        主密钥的 env 写法由 TaskConfig._resolve_master_key / _key_from_cfg 专门处理。
        """
        cfg = {"exec": {"env": {"MY_VAR": "1"}, "allow": ["action:*"]}}
        resolved, findings = resolve_config_secrets(cfg, crypto=_crypto(),
                                                    warner=lambda m: None)
        assert resolved["exec"]["env"] == {"MY_VAR": "1"}
        assert findings == []

    def test_leaf_ciphertext_decrypted_in_place(self):
        crypto = _crypto()
        cfg = {"sftp": {"password": crypto.encrypt_secret("leaf-pw")}}
        resolved, findings = resolve_config_secrets(cfg, crypto=crypto, warner=lambda m: None)
        assert resolved["sftp"]["password"] == "leaf-pw"
        assert findings[0]["path"] == "sftp.password"
        assert findings[0]["action"] == "cipher"


class TestWarning:
    def test_warning_contains_command_and_instructions(self):
        calls = []
        resolve_config_secrets({"sftp_password_plain": "p"}, crypto=_crypto(),
                               warner=calls.append)
        message = calls[0]
        # 平铺命名 sftp_password_plain/_cipher → 基础字段是 sftp_password
        assert "sftp_password" in message
        assert SECRET_ENC_COMMAND in message
        assert "sftp_password_cipher" in message      # 回填目标
        assert "sftp_password_plain" in message       # 清空目标

    def test_warning_for_nested_pair_uses_dotted_path(self):
        calls = []
        resolve_config_secrets({"sftp": {"password_plain": "p"}}, crypto=_crypto(),
                               warner=calls.append)
        message = calls[0]
        assert "sftp.password" in message
        assert "sftp.password_cipher" in message

    def test_nested_list_paths_are_precise(self):
        calls = []
        cfg = {"online": [{"kind": "sftp"}, {"kind": "sftp", "password_plain": "x"}]}
        resolve_config_secrets(cfg, crypto=_crypto(), warner=calls.append)
        assert "online[1].password" in calls[0]

    def test_warn_plaintext_false_suppresses_output_but_records(self):
        calls = []
        cfg = {"sftp_password_plain": "p"}
        resolved, findings = resolve_config_secrets(cfg, crypto=_crypto(),
                                                    warner=calls.append,
                                                    warn_plaintext=False)
        assert resolved["sftp_password"] == "p"     # 取值优先级不变
        assert calls == []
        assert findings[0]["action"] == "plaintext"

    def test_strict_raises(self):
        with pytest.raises(PlaintextSecretError):
            resolve_config_secrets({"sftp_password_plain": "p"}, crypto=_crypto(),
                                   strict=True, warner=lambda m: None)

    def test_master_key_skipped_by_default(self):
        """根密钥由主密钥解析器专门处理，通用解析器不应重复告警/解密。"""
        calls = []
        cfg = {"key": "master-plain", "sftp_password_plain": "p"}
        resolved, findings = resolve_config_secrets(cfg, crypto=_crypto(), warner=calls.append)
        assert resolved["key"] == "master-plain"
        assert [f["path"] for f in findings] == ["sftp_password"]
        assert len(calls) == 1


class TestErrors:
    def test_cipher_without_key_is_clear(self):
        cfg = {"sftp_password_cipher": "RHOP-ENC:whatever"}
        with pytest.raises(SecretError) as exc:
            resolve_config_secrets(cfg, crypto=None, warner=lambda m: None)
        assert "RHOP_KEY" in str(exc.value)

    def test_bad_ciphertext_reports_field(self):
        cfg = {"sftp": {"password": "RHOP-ENC:not-a-real-token"}}
        with pytest.raises(SecretError) as exc:
            resolve_config_secrets(cfg, crypto=_crypto(), warner=lambda m: None)
        assert "sftp.password" in str(exc.value)

    def test_non_dict_config_rejected(self):
        with pytest.raises(SecretError):
            resolve_config_secrets(["nope"], crypto=_crypto())


class TestIntrospection:
    def test_find_secret_fields_covers_leaf_pair_and_node(self):
        cfg = {
            "key": {"plain": "", "cipher": "RHOP-ENC:x"},
            "sftp": {"password": "p"},
            "relay_token_plain": "t",
            "online": [{"kind": "sftp", "password_cipher": "RHOP-ENC:y"}],
        }
        found = {item["path"]: item["kind"] for item in find_secret_fields(cfg)}
        assert found["key"] == "node"
        assert found["sftp.password"] == "leaf"
        assert found["relay_token"] == "pair"
        assert found["online[0].password"] == "pair"

    @pytest.mark.parametrize("key,expected", [
        ("password", True), ("user_password", True), ("sftp_password", True),
        ("token", True), ("api_key", True), ("private_key", True),
        ("key_path", False), ("path", False), ("host", False), ("kind", False),
    ])
    def test_sensitive_leaf_detection(self, key, expected):
        assert is_sensitive_leaf(key) is expected

    def test_mask_value(self):
        assert mask_value("") == ""
        assert mask_value(None) == ""
        assert mask_value("ab") == "***"
        assert mask_value("abcdefgh") == "ab***gh"
        masked = mask_value("RHOP-ENC:abcdefghijklmnop")
        assert "abcdefghijklmnop" not in masked
        assert masked.startswith("RHOP-ENC:ab")

    def test_hint_matches_runtime_constants(self):
        assert "vools.rhop.secret" in SECRET_ENC_COMMAND