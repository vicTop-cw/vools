# -*- coding: utf-8 -*-
"""actus/tests/test_filter_by_dimension_r109.py — indexer.filter_by_dimension 专项
（统帅轮-15时，COVERAGE_AUDIT_R105 第三批）。

测什么 / 为什么
---------------
`indexer.filter_by_dimension(dimension, value, meta_dir)` 是分类维度查询的
统一出口（docs/03 §2.6），此前零直接测试。锚定：
  * V-19 归一语义：查询端与建键端同口径（'Transform'/'transform' 命中同一键，
    值两侧 strip）；
  * 未知维度键 → 空列表不报错（by_{dimension} 缺失兼容旧索引）；
  * 命中结果已排序（build_index 落盘时 sorted）；
  * 索引不存在时先构建（build=True 默认链路）。

py3.8+（pyproject requires-python>=3.8），标准库。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.indexer import filter_by_dimension  # noqa: E402


def _write_index(meta_dir, index):
    os.makedirs(meta_dir, exist_ok=True)
    with open(os.path.join(meta_dir, "actions.index.json"), "w",
              encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)


# 注意：load_index 有 parser_fingerprint 失效判定（build=True 时指纹不匹配
# 会自动重建）。手写索引没有指纹字段 → 按过期处理重建 → 反向索引被重算。
# 因此本文件的「手写索引」用例只锚**兼容性语义**（旧索引缺键不报错），
# 命中语义走 build_index 真实构建的索引（端到端口径）。


def test_dimension_query_via_real_build(tmp_path):
    """端到端：scan 真实动作目录建索引 → 三维度查询命中。"""
    actions = tmp_path / "actions"
    actions.mkdir()
    meta = tmp_path / "_meta"
    CFG_TPL = ('{"id": "%s", "name": "%s", "version": "1.0.0", '
               '"trust": "sandbox", "entry": "main", '
               '"kind": "exec", "purpose": ["transform"], '
               '"industry": ["devops"]}')
    for i, (aid, nm) in enumerate([("demo.beta", "B"), ("demo.alpha", "A"),
                                   ("demo.gamma", "G")]):
        p = actions / ("a%d.actus.md" % i)
        p.write_text(
            "```json #!cfg\n" + (CFG_TPL % (aid, nm)) + "\n```\n\n"
            "#!entry main\n```python #!tag=main\nprint(1)\n```\n",
            encoding="utf-8")

    # 先建索引（落盘）
    from vools.actus import indexer
    indexer.build_index(actions_dir=str(actions), meta_dir=str(meta))

    # kind 维度（全部 exec）——归一查询
    assert filter_by_dimension("kind", "exec", meta_dir=str(meta)) == \
        ["demo.alpha", "demo.beta", "demo.gamma"]      # 已排序
    assert filter_by_dimension("kind", "EXEC", meta_dir=str(meta)) == \
        ["demo.alpha", "demo.beta", "demo.gamma"]      # V-19 大小写归一
    # purpose 维度
    assert "demo.alpha" in filter_by_dimension(
        "purpose", "transform", meta_dir=str(meta))
    # industry 维度 + 空白 trim
    assert "demo.alpha" in filter_by_dimension(
        "industry", "  DevOps ", meta_dir=str(meta))


def test_unknown_dimension_returns_empty(tmp_path):
    """未知维度键 → 空列表不报错（旧索引兼容）。"""
    meta = str(tmp_path / "_meta")
    os.makedirs(meta, exist_ok=True)
    # 真实建一个索引再查不存在的维度
    from vools.actus import indexer
    actions = tmp_path / "actions"
    actions.mkdir()
    cfg = ('{"id": "demo.x", "name": "X", "version": "1.0.0", '
           '"trust": "sandbox", "entry": "main"}')
    p = actions / "x.actus.md"
    p.write_text(
        "```json #!cfg\n" + cfg + "\n```\n"
        "#!entry main\n```python #!tag=main\nprint(1)\n```\n",
        encoding="utf-8")
    indexer.build_index(actions_dir=str(actions), meta_dir=meta)
    assert filter_by_dimension("nosuchdim", "v", meta_dir=meta) == []


def test_value_not_present_returns_empty(tmp_path):
    """维度存在但值未命中 → 空列表。"""
    meta = str(tmp_path / "_meta")
    from vools.actus import indexer
    actions = tmp_path / "actions"
    actions.mkdir()
    cfg = ('{"id": "demo.x", "name": "X", "version": "1.0.0", '
           '"trust": "sandbox", "entry": "main", "kind": "exec"}')
    p = actions / "x.actus.md"
    p.write_text(
        "```json #!cfg\n" + cfg + "\n```\n"
        "#!entry main\n```python #!tag=main\nprint(1)\n```\n",
        encoding="utf-8")
    indexer.build_index(actions_dir=str(actions), meta_dir=meta)
    assert filter_by_dimension("kind", "template", meta_dir=meta) == []


def test_value_whitespace_and_case_normalized(tmp_path):
    """V-19：value 两侧空白与大小写都归一。"""
    meta = str(tmp_path / "_meta")
    from vools.actus import indexer
    actions = tmp_path / "actions"
    actions.mkdir()
    p = actions / "x.actus.md"
    cfg = ('{"id": "demo.x", "name": "X", "version": "1.0.0", '
           '"trust": "sandbox", "entry": "main", "purpose": ["transform"]}')
    p.write_text(
        "```json #!cfg\n" + cfg + "\n```\n"
        "#!entry main\n```python #!tag=main\nprint(1)\n```\n",
        encoding="utf-8")
    indexer.build_index(actions_dir=str(actions), meta_dir=meta)
    assert filter_by_dimension("purpose", "  TRANSFORM ", meta_dir=meta) == \
        ["demo.x"]
