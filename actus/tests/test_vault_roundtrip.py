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
