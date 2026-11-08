# -*- coding: utf-8 -*-
"""统帅轮-10 时：索引自动失效（REFACTOR_COMPLETION §六.4）契约回归。

使命：格式解析逻辑变更时索引自动失效 —— parser_fingerprint 写入索引缓存，
load_index(build=True) 指纹不匹配（含老缓存无指纹字段）⇒ 判定过期 ⇒ 自动
重建并在结果中可见（rebuild_reason + logging.info），终结「解析逻辑改了、
旧索引继续用」的静默错配。

覆盖矩阵：
  * 指纹一致 → 直接用缓存不重建（返回值与磁盘内容逐字段相等）
  * 指纹变化 → 自动重建、rebuild_reason 可见、重建内容与手工重建等价、
    二次 load 不再重建（不每次重建）
  * 老缓存无 parser_fingerprint 字段 → 按过期处理重建一次（向后兼容）
  * 指纹计算对解析器源码变化敏感（monkeypatch _fingerprint_source_texts）
  * build=False 只读路径维持零副作用契约：过期也照返、不重建
  * build_index 落盘缓存携带当前指纹
"""
import json
import logging
import os

import pytest

from vools.actus import indexer
from vools.actus.indexer import (
    INDEX_FINGERPRINT_KEY,
    _fingerprint_source_texts,
    _parser_fingerprint,
    build_index,
    load_index,
)

SCHEMA_ACTION = """---
id: myapp.idxprobe
name: IdxProbe
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
description: 索引自动失效探针
---

# Probe

```python #!run tag=main
print("ok")
```
"""


def _write_action(tmp_path, name="probe.actus.schema.md", text=SCHEMA_ACTION):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="")
    return p


def test_new_cache_carries_fingerprint(tmp_path):
    """build_index 落盘缓存必须携带当前解析器指纹（失效判定的前置条件）。"""
    meta = tmp_path / "meta"
    _write_action(tmp_path)
    idx = build_index(actions_dir=str(tmp_path), meta_dir=str(meta))
    assert idx.get(INDEX_FINGERPRINT_KEY) == _parser_fingerprint()
    with open(os.path.join(str(meta), "actions.index.json"),
              encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk.get(INDEX_FINGERPRINT_KEY) == _parser_fingerprint()


def test_load_index_reuses_cache_when_fingerprint_matches(tmp_path, monkeypatch):
    """指纹一致 → 直接用缓存，不重建（返回值与磁盘内容逐字段相等）。"""
    monkeypatch.setattr(indexer, "_fingerprint_source_texts",
                        lambda: {"model": "parser-src-A"})
    meta = tmp_path / "meta"
    _write_action(tmp_path)
    idx1 = build_index(actions_dir=str(tmp_path), meta_dir=str(meta))
    assert idx1[INDEX_FINGERPRINT_KEY] == _parser_fingerprint()

    idx2 = load_index(meta_dir=str(meta))
    assert "rebuild_reason" not in idx2, "指纹一致却被重建"
    assert idx2 == idx1, "指纹一致时应原样返回磁盘缓存（含 generated_at）"


def test_load_index_auto_rebuilds_when_fingerprint_mismatches(
        tmp_path, monkeypatch, caplog):
    """指纹变化 → 自动重建且结果正确；rebuild_reason 可见；二次 load 不重建。"""
    monkeypatch.setattr(indexer, "_fingerprint_source_texts",
                        lambda: {"model": "parser-src-A"})
    meta = tmp_path / "meta"
    _write_action(tmp_path)
    stale_fp = build_index(actions_dir=str(tmp_path),
                           meta_dir=str(meta))[INDEX_FINGERPRINT_KEY]

    # 解析逻辑"变更"：指纹源换文本 → 当前指纹 != 缓存指纹
    monkeypatch.setattr(indexer, "_fingerprint_source_texts",
                        lambda: {"model": "parser-src-B"})

    with caplog.at_level(logging.INFO, logger="vools.actus.indexer"):
        idx2 = load_index(meta_dir=str(meta))
    assert "rebuild_reason" in idx2, "指纹不匹配却未自动重建"
    assert idx2[INDEX_FINGERPRINT_KEY] == _parser_fingerprint()
    assert idx2[INDEX_FINGERPRINT_KEY] != stale_fp
    assert "mismatch" in idx2["rebuild_reason"]

    # 结果正确性：自动重建内容与同条件下手工重建等价（actions 逐字段相等）
    manual = build_index(actions_dir=None, meta_dir=str(tmp_path / "meta2"),
                         write=False, write_cache=False)
    assert idx2["actions"] == manual["actions"]

    # 过期标记不得落盘（避免残留到新鲜缓存误导后续读取）
    with open(os.path.join(str(meta), "actions.index.json"),
              encoding="utf-8") as f:
        on_disk = json.load(f)
    assert "rebuild_reason" not in on_disk
    assert on_disk[INDEX_FINGERPRINT_KEY] == _parser_fingerprint()

    # 二次 load：缓存已新鲜 → 不再重建（失效是"过期一次"，不是"每次重建"）
    idx3 = load_index(meta_dir=str(meta))
    assert "rebuild_reason" not in idx3

    # 失效可见性：logging.info 留痕，绝不静默
    assert any("index stale" in r.getMessage() for r in caplog.records), \
        "指纹失效重建未记录 logging.info"


def test_load_index_rebuilds_legacy_cache_without_fingerprint(tmp_path):
    """老缓存无 parser_fingerprint 字段 → 按过期处理，重建一次（向后兼容）。"""
    meta = tmp_path / "meta"
    os.makedirs(str(meta))
    legacy = {
        "schema_version": "2.0.0",
        "classification_version": "2.0",
        "generated_at": "2020-01-01T00:00:00+08:00",
        "actions": {"myapp.idxprobe": {"name": "IdxProbe", "status": "valid"}},
    }
    with open(os.path.join(str(meta), "actions.index.json"), "w",
              encoding="utf-8") as f:
        json.dump(legacy, f, ensure_ascii=False)

    idx = load_index(meta_dir=str(meta))
    assert "rebuild_reason" in idx, "无指纹老缓存应按过期处理重建"
    assert "no parser_fingerprint" in idx["rebuild_reason"]
    assert idx[INDEX_FINGERPRINT_KEY] == _parser_fingerprint()
    # 重建后的缓存已补上指纹 → 二次 load 不再重建
    assert "rebuild_reason" not in load_index(meta_dir=str(meta))


def test_parser_fingerprint_sensitive_to_parser_source_changes():
    """指纹计算对解析器源码变化敏感：任一层文本变化 ⇒ 指纹变化。"""
    base = {"model": "A", "frontmatter": "B"}
    fp_base = _parser_fingerprint_with(base)

    assert fp_base == _parser_fingerprint_with(dict(base)), "同输入应得同指纹"

    changed = dict(base)
    changed["model"] = "A2"
    assert fp_base != _parser_fingerprint_with(changed), "model 层变化未改变指纹"

    changed = dict(base)
    changed["frontmatter"] = "B2"
    assert fp_base != _parser_fingerprint_with(changed), \
        "frontmatter 层变化未改变指纹"

    with_layer = dict(base)
    with_layer["blocks"] = "C"
    assert fp_base != _parser_fingerprint_with(with_layer), \
        "新增指纹层未参与指纹计算"

    assert fp_base != _parser_fingerprint_with({}), \
        "全部源缺失的退化指纹不应与正常指纹相同"


def _parser_fingerprint_with(texts):
    """经指纹源函数注入文本后计算指纹（测试专用间接层）。"""
    orig = indexer._fingerprint_source_texts
    indexer._fingerprint_source_texts = lambda: texts
    try:
        return _parser_fingerprint()
    finally:
        indexer._fingerprint_source_texts = orig


def test_load_index_build_false_returns_cache_as_is(tmp_path, monkeypatch):
    """build=False 只读路径零副作用契约不变：过期缓存也照返、不重建。"""
    monkeypatch.setattr(indexer, "_fingerprint_source_texts",
                        lambda: {"model": "parser-src-A"})
    meta = tmp_path / "meta"
    _write_action(tmp_path)
    build_index(actions_dir=str(tmp_path), meta_dir=str(meta))

    monkeypatch.setattr(indexer, "_fingerprint_source_texts",
                        lambda: {"model": "parser-src-B"})
    with open(os.path.join(str(meta), "actions.index.json"),
              encoding="utf-8") as f:
        stale_on_disk = json.load(f)

    idx = load_index(meta_dir=str(meta), build=False)
    assert "rebuild_reason" not in idx, "build=False 不应触发重建"
    assert idx == stale_on_disk, "build=False 应回原样返回磁盘内容（哪怕过期）"
