"""配置层测试：方向归一、默认值、存储后端选择、路径模板、敏感值掩码。"""

import json
import os

import pytest

from vools.rhop.crypto import RhopCrypto
from vools.rhop.task.config import (
    DEFAULT_EXEC,
    DEFAULT_QUEUE,
    SHORT_ROLES,
    TaskConfig,
    load_task_config,
    normalize_role,
)
from vools.rhop.task.errors import SecretError, PlaintextSecretError, StoreUnavailable


def _cfg(role="B", base_dir=None, warner=None, **overrides):
    data = {"name": "unit", "role": role, "key": "unit-key",
            "shared": {"write": str(base_dir)}, "queue": {"store": {"kind": "sqlite-local"}}}
    data.update(overrides)
    return TaskConfig.from_dict(data, base_dir=str(base_dir), warner=warner,
                                warn_plaintext=False)


class TestRoleNormalization:
    @pytest.mark.parametrize("given,expected", [
        ("A", "SEND"), ("a", "SEND"), ("SEND", "SEND"), ("requester", "SEND"),
        ("B", "RECV"), ("b", "RECV"), ("RECV", "RECV"), ("executor", "RECV"),
        ("server", "RECV"), ("worker", "RECV"),
        ("C", "RELAY"), ("relay", "RELAY"), ("relay_server", "RELAY"),
    ])
    def test_aliases(self, given, expected):
        assert normalize_role(given) == expected

    @pytest.mark.parametrize("given", ["P0", "p1", "P2", "p3", "", None, "unknown"])
    def test_rejected(self, given):
        with pytest.raises(SecretError):
            normalize_role(given)

    def test_direction_alias_used_when_role_absent(self, tmp_path):
        cfg = TaskConfig.from_dict({"name": "n", "direction": "A", "key": "k",
                                    "queue": {"store": {"kind": "sqlite-local"}}},
                                   base_dir=str(tmp_path), warn_plaintext=False)
        assert cfg.role_short() == "A"
        assert SHORT_ROLES[cfg.role] == "A"

    def test_no_p0_to_p3_anywhere_in_config(self, tmp_path):
        """方向字段里不允许再出现跳板角色写法（p0..p3）。

        只看配置语义字段，不看 base_dir 路径（临时目录名可能随机含 p1 之类）。
        """
        cfg = _cfg(base_dir=tmp_path)
        fields = [cfg.role_short(), cfg.role, cfg.worker_id(),
                  cfg.queue["heartbeat"]["file"], cfg.queue["store"]["kind"],
                  str(cfg.queue["heartbeat"]["closed_token"])]
        for text in fields:
            lowered = text.lower()
            for token in ("p0", "p1", "p2", "p3"):
                assert token not in lowered, "%s 含跳板角色 %s" % (text, token)
        assert cfg.role_short() in ("A", "B", "C")


class TestDefaults:
    def test_queue_defaults_applied(self, tmp_path):
        cfg = _cfg(base_dir=tmp_path)
        assert cfg.queue["heartbeat"]["file"] == "unit.heartbeat"
        assert cfg.queue["heartbeat"]["interval_sec"] == DEFAULT_QUEUE["heartbeat"]["interval_sec"]
        assert cfg.queue["heartbeat"]["stale_after_sec"] == 15
        assert cfg.queue["heartbeat"]["closed_token"] == "closed"
        assert cfg.queue["poll_interval_sec"] == DEFAULT_QUEUE["poll_interval_sec"]
        assert cfg.queue["max_retries"] == 3
        assert cfg.queue["encrypt_result"] is True
        assert cfg.worker_id() == "unit-b"

    def test_exec_defaults_deny_arbitrary_cli(self, tmp_path):
        cfg = _cfg(base_dir=tmp_path)
        assert cfg.exec["allow"] == DEFAULT_EXEC["allow"]
        assert "action:*" in cfg.exec["allow"]
        assert "handler:*" in cfg.exec["allow"]
        assert cfg.exec["allow_any"] is False

    def test_queue_overrides_merge(self, tmp_path):
        cfg = _cfg(base_dir=tmp_path, queue={"store": {"kind": "sqlite-local"},
                                             "heartbeat": {"interval_sec": 1},
                                             "poll_interval_sec": 0.5})
        assert cfg.queue["heartbeat"]["interval_sec"] == 1
        assert cfg.queue["heartbeat"]["stale_after_sec"] == 15   # 未覆盖的保留默认
        assert cfg.poll_interval() == 0.5

    def test_store_string_shorthand(self, tmp_path):
        cfg = _cfg(base_dir=tmp_path, queue={"store": "sqlite-local"})
        assert cfg.queue["store"]["kind"] == "sqlite-local"

    def test_heartbeat_string_shorthand(self, tmp_path):
        cfg = _cfg(base_dir=tmp_path, queue={"store": {"kind": "sqlite-local"},
                                             "heartbeat": "custom.hb"})
        assert cfg.queue["heartbeat"]["file"] == "custom.hb"

    def test_bad_queue_and_exec_types(self, tmp_path):
        with pytest.raises(SecretError):
            _cfg(base_dir=tmp_path, queue=["x"])
        with pytest.raises(SecretError):
            _cfg(base_dir=tmp_path, exec=["x"])
        with pytest.raises(SecretError):
            _cfg(base_dir=tmp_path, queue={"heartbeat": 5})


class TestStoreSelection:
    def test_local_kind_needs_no_shared(self, tmp_path):
        cfg = TaskConfig.from_dict({"name": "n", "role": "A", "key": "k",
                                    "queue": {"store": {"kind": "sqlite-local"}}},
                                   base_dir=str(tmp_path), warn_plaintext=False)
        store = cfg.build_store()
        try:
            assert os.path.basename(store.path) == "rhop-a.db"
        finally:
            store.close()

    def test_shared_kind_without_shared_path_errors(self, tmp_path):
        cfg = TaskConfig.from_dict({"name": "n", "role": "A", "key": "k",
                                    "queue": {"store": {"kind": "sqlite-shared"}}},
                                   base_dir=str(tmp_path), warn_plaintext=False)
        with pytest.raises(StoreUnavailable) as exc:
            cfg.build_store()
        assert "sqlite-local" in str(exc.value)

    def test_path_template_expansion(self, tmp_path):
        cfg = TaskConfig.from_dict(
            {"name": "link", "role": "B", "key": "k", "shared": {"write": str(tmp_path)},
             "queue": {"store": {"kind": "sqlite-shared",
                                 "path": "{shared}/db/{name}-{role}.db"}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        store = cfg.build_store()
        try:
            assert store.path == os.path.join(str(tmp_path), "db", "link-b.db")
        finally:
            store.close()

    def test_explicit_path_needs_no_shared(self, tmp_path):
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "A", "key": "k",
             "queue": {"store": {"kind": "sqlite-shared",
                                 "path": os.path.join(str(tmp_path), "explicit.db")}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        store = cfg.build_store()
        try:
            assert store.path.endswith("explicit.db")
        finally:
            store.close()

    def test_http_shared_is_not_a_filesystem_medium(self, tmp_path):
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "B", "key": "k",
             "shared": {"write": "http://nas:8080/rhop"},
             "queue": {"store": {"kind": "sqlite-shared"}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        assert cfg.shared_read_root() is None
        with pytest.raises(StoreUnavailable):
            cfg.build_store()


class TestMasterKey:
    def test_plain_string_key_warns(self, tmp_path):
        calls = []
        TaskConfig.from_dict({"name": "n", "role": "A", "key": "plain-master",
                              "queue": {"store": {"kind": "sqlite-local"}}},
                             base_dir=str(tmp_path), warner=calls.append)
        assert len(calls) == 1
        assert "明文主密钥" in calls[0]
        assert "python -m vools.rhop.secret enc" in calls[0]

    def test_key_plain_node_warns(self, tmp_path):
        calls = []
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "A", "key": {"plain": "mk"},
             "queue": {"store": {"kind": "sqlite-local"}}},
            base_dir=str(tmp_path), warner=calls.append)
        assert cfg.rhop.key == "mk"
        assert any("key.plain" in c for c in calls)

    def test_key_cipher_needs_unlock_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RHOP_KEY", "outer-key")
        wrapped = RhopCrypto("outer-key").encrypt_secret("real-master")
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "A", "key": {"cipher": wrapped, "env": "RHOP_KEY"},
             "queue": {"store": {"kind": "sqlite-local"}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        assert cfg.rhop.key == "real-master"

    def test_key_cipher_wrong_unlock_errors(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RHOP_KEY", "right-key")
        wrapped = RhopCrypto("right-key").encrypt_secret("real-master")
        monkeypatch.setenv("RHOP_KEY", "wrong-key")
        with pytest.raises(SecretError) as exc:
            TaskConfig.from_dict(
                {"name": "n", "role": "A", "key": {"cipher": wrapped, "env": "RHOP_KEY"},
                 "queue": {"store": {"kind": "sqlite-local"}}},
                base_dir=str(tmp_path), warn_plaintext=False)
        assert "key.cipher" in str(exc.value)

    def test_key_file_source(self, tmp_path):
        key_file = os.path.join(str(tmp_path), "rhop.key")
        with open(key_file, "w", encoding="utf-8") as fh:
            fh.write("  file-based-key\n")
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "A", "key": {"path": key_file},
             "queue": {"store": {"kind": "sqlite-local"}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        assert cfg.rhop.key == "file-based-key"

    def test_strict_secrets_blocks_plaintext(self, tmp_path):
        with pytest.raises(PlaintextSecretError):
            TaskConfig.from_dict({"name": "n", "role": "A", "key": "plain",
                                  "queue": {"store": {"kind": "sqlite-local"}}},
                                 base_dir=str(tmp_path), strict_secrets=True,
                                 warner=lambda m: None)

    def test_missing_key_yields_no_crypto(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RHOP_KEY", raising=False)
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "A", "queue": {"store": {"kind": "sqlite-local"}}},
            base_dir=str(tmp_path), warn_plaintext=False)
        assert cfg.rhop.key == ""
        assert cfg.build_crypto() is None


class TestDisplay:
    def test_to_dict_masks_sensitive_values(self, tmp_path):
        crypto = RhopCrypto("secret-master")
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "A", "key": "secret-master",
             "shared": {"write": str(tmp_path)},
             "online": [{"kind": "sftp",
                         "password_cipher": crypto.encrypt_secret("sftp-pw")}],
             "relay": {"host": "127.0.0.1",
                       "token_cipher": crypto.encrypt_secret("relay-token")}},
            base_dir=str(tmp_path), warn_plaintext=False)
        dumped = cfg.to_dict()
        assert dumped["key"] == "***"
        text = json.dumps(dumped, ensure_ascii=False)
        assert "sftp-pw" not in text
        assert "relay-token" not in text
        assert "RHOP-ENC:" not in text
        # 但已解析出来的明文确实进去了（说明这是"打码展示"而非"没解出来"）
        assert cfg.resolved["online"][0]["password"] == "sftp-pw"

    def test_describe_fields(self, tmp_path):
        calls = []
        cfg = TaskConfig.from_dict(
            {"name": "link", "role": "B", "key": "k", "shared": {"write": str(tmp_path)},
             "online": [{"kind": "sftp", "password_plain": "p"}]},
            base_dir=str(tmp_path), warner=calls.append)
        info = cfg.describe()
        assert info["role"] == "B"
        assert info["role_long"] == "RECV"
        assert info["shared"]["read"] == str(tmp_path)
        assert info["heartbeat"]["file"] == "link.heartbeat"
        assert info["worker_id"] == "link-b"
        assert any("password" in p for p in info["plaintext_fields"])

    def test_from_file_uses_config_dir_as_base_dir(self, tmp_path):
        path = os.path.join(str(tmp_path), "conf.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"name": "n", "role": "A", "key": "k",
                       "queue": {"store": {"kind": "sqlite-local"}}}, fh)
        cfg = load_task_config(path, warn_plaintext=False)
        assert cfg.base_dir == str(tmp_path)
        store = cfg.build_store()
        try:
            assert store.path == os.path.join(str(tmp_path), "rhop-a.db")
        finally:
            store.close()

    def test_plaintext_findings_filter(self, tmp_path):
        calls = []
        cfg = TaskConfig.from_dict(
            {"name": "n", "role": "A", "key": "k", "shared": {"write": str(tmp_path)},
             "online": [{"kind": "sftp", "password_plain": "p"}],
             "queue": {"store": {"kind": "sqlite-local"}}},
            base_dir=str(tmp_path), warner=calls.append)
        assert [f["path"] for f in cfg.plaintext_findings()] == ["key", "online[0].password"]
        assert len(calls) == 2