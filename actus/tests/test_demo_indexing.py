# -*- coding: utf-8 -*-
"""`.demo.` 文件的两种情形必须区分（第 24 轮）。

历史：demo 文档页原本是纯 markdown（无 front-matter），`indexer` 对
「解析失败 + 文件名含 `.demo.`」一律静默跳过。第 19 轮给 demo 补了
front-matter 之后，这个跳过分支变成了**掩盖真实错误**的通道——实测
「有 front-matter 但内容非法」的 demo 被完全静默忽略（不在 actions、
也不在 invalid），用户毫无提示。

现在按 **有无 front-matter** 区分：
  - 无 front-matter → 纯教学资产，跳过（合法）
  - 有 front-matter 但解析失败 → 坏动作文件，必须上报
"""
import os

import pytest

from vools.actus.indexer import build_index


@pytest.fixture(autouse=True)
def _repo_root_to_tmp(tmp_path, monkeypatch):
    """测试卫生：`scan_actions` 的 mtime 缓存只认 `_repo_root()`（不看
    `ACTUS_META_DIR`），不隔离就会把缓存写进真实仓库 `_meta/`。指到 tmp。"""
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))


GOOD = """---
id: {aid}
name: N
version: 1.0.0
trust: sandbox
kind: doc
platform: desktop
description: doc
---

# Doc
"""

BAD_WITH_FM = """---
id: x.demo
---

坏的内容（缺 name/version/trust/kind/platform）
"""

PLAIN_DOC = """# 纯文档演示

没有任何 front-matter，也没有 #!cfg 块 —— 属合法的教学资产。
"""


def _write(adir, name, text):
    with open(os.path.join(adir, name), "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _index(tmp_path, files):
    adir = tmp_path / "actions"
    adir.mkdir()
    for name, text in files.items():
        _write(str(adir), name, text)
    # 测试卫生：显式 meta_dir，否则 build_index 会把索引/mtime 缓存写进真实仓库
    # `_meta/`（它只认 _repo_root()，不看 ACTUS_META_DIR）。
    return build_index(actions_dir=str(adir), meta_dir=str(tmp_path / "_meta"))


def test_bad_demo_with_frontmatter_is_reported(tmp_path):
    """有 front-matter 却解析失败 → 必须出现在 actions 里（带 _invalid: 前缀）。"""
    idx = _index(tmp_path, {"x.demo.actus.md": BAD_WITH_FM})
    keys = list((idx.get("actions") or {}).keys())
    assert any("_invalid:" in k for k in keys), \
        "坏 demo 被静默忽略了，keys=%r" % (keys,)


def test_plain_doc_demo_is_skipped(tmp_path):
    """无 front-matter 的纯文档 demo → 合法跳过，不占索引。"""
    idx = _index(tmp_path, {"y.demo.actus.md": PLAIN_DOC})
    keys = list((idx.get("actions") or {}).keys())
    assert keys == [], "纯文档 demo 不该进索引，keys=%r" % (keys,)


def test_good_demo_is_indexed(tmp_path):
    """有 front-matter 且合法的 demo → 应正常进索引。"""
    idx = _index(tmp_path, {"z.demo.actus.md": GOOD.format(aid="myapp.z.demo")})
    keys = list((idx.get("actions") or {}).keys())
    assert "myapp.z.demo" in keys, keys


def test_mixed_demo_cases(tmp_path):
    """三种 demo 混在一起时的判定要各自正确。"""
    idx = _index(tmp_path, {
        "good.demo.actus.md": GOOD.format(aid="myapp.good.demo"),
        "bad.demo.actus.md": BAD_WITH_FM,
        "plain.demo.actus.md": PLAIN_DOC,
        "real.actus.schema.md": GOOD.format(aid="myapp.real"),
    })
    keys = list((idx.get("actions") or {}).keys())
    assert "myapp.good.demo" in keys
    assert "myapp.real" in keys
    assert any("_invalid:" in k and "bad.demo" in k for k in keys), keys
    assert not any("plain.demo" in k for k in keys), keys
