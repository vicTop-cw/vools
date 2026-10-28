# -*- coding: utf-8 -*-
"""vault（密钥保险库）的往返与静态加密契约（第 29 轮探测沉淀）。

结论：**本轮未发现缺陷**。Vault 在隔离 meta_dir 下：
  - 7 种值形态往返一致（ASCII / 空格 / 中文 / emoji / 500 字 / 换行 / 空串）
  - 覆盖写生效、删除生效、不存在的 key 返回 None
  - `list()` 只回元数据（key/scope/description/时间），**不含明文**
  - 落盘的 keys.json / meta.json 中**搜不到任何明文**（静态加密有效）

注意类接口是 `Vault.set/get/delete/list`（模块级函数才是 set_key/get_key/…）。
"""
import os

import pytest

from vools.actus.vault import Vault
from vools.actus.vault2 import Vault2

MASTER = "test-master-key"


@pytest.fixture()
def vault(tmp_path):
    return Vault(meta_dir=str(tmp_path), master_key=MASTER)


VALUES = [
    "sk-abc123",
    "a b c",
    "密钥值中文",
    "🔐secret",
    "x" * 500,
    "line1\nline2",
    "",
]


@pytest.mark.parametrize("value", VALUES, ids=["ascii", "space", "cjk", "emoji",
                                               "long", "newline", "empty"])
def test_roundtrip(vault, value):
    vault.set("probe.key", value)
    assert vault.get("probe.key") == value


def test_overwrite(vault):
    vault.set("probe.key", "first")
    vault.set("probe.key", "second")
    assert vault.get("probe.key") == "second"


def test_missing_key_returns_none(vault):
    assert vault.get("no.such.key") is None


def test_delete(vault):
    vault.set("probe.key", "v")
    vault.delete("probe.key")
    assert vault.get("probe.key") is None


def test_list_has_no_plaintext(vault):
    secret = "super-secret-value-42"
    vault.set("probe.key", secret, description="desc")
    entries = vault.list()
    assert entries, "list() 应返回条目"
    blob = repr(entries)
    assert secret not in blob, "list() 泄露了明文！"
    assert "value" not in entries[0], entries[0]
    assert "key" in entries[0] and "scope" in entries[0]


def test_at_rest_is_encrypted(vault, tmp_path):
    """落盘文件不得包含明文（静态加密）。"""
    secrets = ["plain-alpha-111", "明文-中文-222", "🔐-emoji-333"]
    for i, s in enumerate(secrets):
        vault.set("probe.key.%d" % i, s)
    leaked = []
    for root, _dirs, files in os.walk(tmp_path):
        for f in files:
            raw = open(os.path.join(root, f), "rb").read()
            for s in secrets:
                if s.encode("utf-8") in raw:
                    leaked.append((f, s))
    assert not leaked, "落盘文件里出现明文: %s" % leaked


def test_scope_isolation(vault):
    vault.set("probe.key", "global-v", scope="global")
    vault.set("probe.key", "proj-v", scope="project")
    assert vault.get("probe.key", scope="global") == "global-v"
    assert vault.get("probe.key", scope="project") == "proj-v"


# ---------------------------------------------------------------------------
# 显式目录（不依赖环境变量）—— 防止"跨测试环境泄漏"再次发生
# ---------------------------------------------------------------------------

def test_vault2_explicit_dir_roundtrip(tmp_path, monkeypatch):
    """退步了会怎样（第 19 轮 `~/.actus` 污染根因）：只靠环境变量隔离的测试，在
    teardown 把 `ACTUS_VAULT2_DIR` 恢复成"未设置"后，其它测试构造 `Vault2()` 会走
    默认目录 `~/.actus/vault2` 建库。

    断言：**显式删掉 `ACTUS_VAULT2_DIR`** 后，`Vault2(vault_dir=<tmp>)` 的 register/
    auth/set/get 全部成功，且库文件落在传入的 tmp 目录（不依赖环境、不碰真实 HOME）。
    """
    monkeypatch.delenv("ACTUS_VAULT2_DIR", raising=False)
    vault = Vault2(vault_dir=str(tmp_path / "explicit-v2"))

    registered = vault.register("explicit", "123456", security_level="L1")
    assert registered["status"] == "ok", registered
    auth = vault.auth(registered["identity_id"], registered["machine_id"], "123456")
    assert auth["status"] == "ok", auth
    assert vault.set_secret(auth["session_token"], "k", "V")["status"] == "ok"

    got = vault.get_secret(auth["session_token"], "k")
    assert got["status"] == "ok" and got["value"] == "V", got
    assert os.path.isfile(str(tmp_path / "explicit-v2" / "vault2.db"))


def test_session_dirs_are_pinned_away_from_real_home():
    """退步了会怎样（3 次污染的历史）：session 级 fixture 失效（被删/降成 function
    scope），后续测试又会在"未设置环境变量"的瞬间用默认 `~/.actus`。

    断言：`HOME`/`ACTUS_VAULT2_DIR`/`ACTUS_META_DIR` 都指向本次 pytest 的 tmp
    会话目录，且**不是**真实用户主目录（`~` 展开值）。
    """
    required = ("HOME", "USERPROFILE", "ACTUS_META_DIR", "ACTUS_VAULT2_DIR")
    # ACTUS_INSTALLED_DIR 有意不强制钉（默认由 HOME 推导）；若外部设置了则也必须落 tmp
    optional = ("ACTUS_INSTALLED_DIR",)
    for name in required + optional:
        value = os.environ.get(name)
        if name in optional and not value:
            continue
        assert value, "session fixture 没有钉住 %s" % name
        normalized = os.path.normcase(os.path.abspath(value))
        assert "pytest-" in normalized or "session-isolation" in normalized, (
            "%s 没有指向 pytest 临时目录: %r" % (name, value))
        assert normalized != os.path.normcase(os.path.abspath(
            os.path.expanduser("~/.actus"))), "%s 仍可能落到 ~/.actus" % name
