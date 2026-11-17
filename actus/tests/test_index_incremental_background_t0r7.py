# -*- coding: utf-8 -*-
"""T0r7：P3 索引构建增量与后台重建契约回归。

使命：基于 T0r4 的 scan_actions changed_ids 记录落地两项能力——
  ① 增量重扫只解析 changed_ids 对应的变更文件，未变更文件不重复解析
     （_meta/actions.parse.json 命中短路，修复 V-17「缓存命中仍全量重解析」）；
  ② 后台重建：后台线程在暂存目录重建索引，重建期间查询继续用旧索引，
     重建完成后 os.replace 原子切换（双缓冲/读写锁思路）；
  ③ 重建失败回退旧索引不崩溃。

覆盖矩阵：
  * 重复扫描不重复解析未变更文件（解析文件集合为空、_parse_hits 全命中）
  * 修改单个动作后只解析该变更文件（changed_ids 恰为该动作）
  * build_index(incremental=True) 无变更时增量短路：0 解析、actions 与旧索引
    等价、generated_at 刷新
  * 后台重建期间查询可用旧索引；重建完成后原子切换（查询读到新索引）
  * 后台重建失败回退旧索引（线上索引保持旧内容、error 可见、不崩溃）
  * rebuild_index_background 入口返回句柄并完成切换
"""
import json
import os
import threading
import time

import pytest

from vools.actus import indexer
from vools.actus.indexer import (
    BackgroundIndexRebuilder,
    build_index,
    load_index,
    rebuild_index_background,
)

SCHEMA_ACTION = """---
id: t0r7.{aid}
name: T0r7{aid}
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
description: T0r7 增量索引测试动作 {aid}
---

# {aid}

```python #!run tag=main
print("{aid}")
```
"""


def _write_action(root, aid, text=None, mtime_bump=0):
    """写一个 schema 动作文件；mtime_bump>0 时把 mtime 推到未来，保证缓存判定。"""
    p = root / f"{aid}.actus.schema.md"
    p.write_text(text or SCHEMA_ACTION.format(aid=aid), encoding="utf-8", newline="")
    if mtime_bump:
        now = time.time()
        os.utime(str(p), (now + mtime_bump, now + mtime_bump))
    return p


def _count_parse_calls(monkeypatch):
    """包装 parse_cfg_from_file，收集被解析的文件路径集合（解析文件集合断言）。"""
    parsed = []
    orig = indexer.parse_cfg_from_file

    def counting(path, *args, **kwargs):
        parsed.append(str(path))
        return orig(path, *args, **kwargs)

    monkeypatch.setattr(indexer, "parse_cfg_from_file", counting)
    return parsed


@pytest.fixture()
def isolated_meta(tmp_path, monkeypatch):
    """显式 meta_dir + ACTUS_META_DIR 指向 tmp，防写真实仓库缓存。"""
    meta = tmp_path / "meta"
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))
    return meta


def _reset_scan_attrs():
    """清掉 scan_actions 跨调用残留的函数属性，保证断言起点干净。"""
    for name in ("_changed_ids", "_has_removal", "_parse_hits", "problems"):
        try:
            delattr(indexer.scan_actions, name)
        except AttributeError:
            pass


# ──────────────────────────────────────────────────────────────
# ① 重复扫描不重复解析未变更文件（V-17 修复）
# ──────────────────────────────────────────────────────────────

def test_scan_actions_reuses_parse_cache_unchanged(tmp_path, monkeypatch):
    """二次扫描未变更文件：解析文件集合为空（0 次解析）、changed_ids 为空。"""
    _reset_scan_attrs()
    parsed = _count_parse_calls(monkeypatch)
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid in ("a", "b", "c"):
        _write_action(actions_dir, aid)

    r1 = indexer.scan_actions(str(actions_dir), use_cache=True,
                              write_cache=True, validate=False)
    assert sorted(r1) == ["t0r7.a", "t0r7.b", "t0r7.c"]
    assert len(parsed) == 3, "首次扫描应解析全部 3 个动作"
    assert getattr(indexer.scan_actions, "_parse_hits", 0) == 0

    r2 = indexer.scan_actions(str(actions_dir), use_cache=True,
                              write_cache=True, validate=False)
    assert sorted(r2) == ["t0r7.a", "t0r7.b", "t0r7.c"]
    assert len(parsed) == 3, "未变更文件二次扫描必须 0 次解析（V-17 修复）"
    assert getattr(indexer.scan_actions, "_parse_hits", 0) == 3
    assert getattr(indexer.scan_actions, "_changed_ids", []) == []
    assert getattr(indexer.scan_actions, "_has_removal", False) is False


def test_scan_actions_incremental_only_parses_changed(tmp_path, monkeypatch):
    """修改单个动作后：只解析该变更文件（解析集合 == {变更文件}）。"""
    _reset_scan_attrs()
    parsed = _count_parse_calls(monkeypatch)
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid in ("a", "b", "c"):
        _write_action(actions_dir, aid)

    indexer.scan_actions(str(actions_dir), use_cache=True,
                         write_cache=True, validate=False)
    assert len(parsed) == 3

    # 修改 b：内容变化 + mtime 推到未来（防秒级同 mtime 命中缓存）
    b = _write_action(actions_dir, "b",
                      text=SCHEMA_ACTION.format(aid="b") + "\n# v2\n",
                      mtime_bump=5)
    parsed.clear()

    r3 = indexer.scan_actions(str(actions_dir), use_cache=True,
                              write_cache=True, validate=False)
    assert sorted(r3) == ["t0r7.a", "t0r7.b", "t0r7.c"]
    assert len(parsed) == 1, "变更后只应解析 1 个变更文件"
    assert str(b) in parsed, "解析集合应恰为变更文件 b"
    assert sorted(getattr(indexer.scan_actions, "_changed_ids", [])) == ["t0r7.b"]
    assert getattr(indexer.scan_actions, "_parse_hits", 0) == 2


# ──────────────────────────────────────────────────────────────
# ② build_index 增量短路（无变更时复用旧索引、0 解析）
# ──────────────────────────────────────────────────────────────

def test_build_index_incremental_shortcircuit_no_parse(tmp_path, monkeypatch,
                                                       isolated_meta):
    """incremental=True 且无变更：0 解析 + 复用旧索引 actions + generated_at 刷新。"""
    _reset_scan_attrs()
    parsed = _count_parse_calls(monkeypatch)
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid in ("a", "b", "c"):
        _write_action(actions_dir, aid)

    idx1 = build_index(actions_dir=str(actions_dir), meta_dir=str(isolated_meta),
                       incremental=True, atomic_write=True)
    assert len(idx1["actions"]) == 3
    assert len(parsed) == 3, "首次构建应解析全部动作"
    with open(os.path.join(str(isolated_meta), "actions.index.json"),
              encoding="utf-8") as f:
        disk1 = json.load(f)

    parsed.clear()
    idx2 = build_index(actions_dir=str(actions_dir), meta_dir=str(isolated_meta),
                       incremental=True, atomic_write=True)
    assert len(parsed) == 0, "无变更增量构建必须 0 次解析"
    assert idx2["actions"] == disk1["actions"], "增量短路应复用旧索引 actions"
    assert idx2["actions"] == idx1["actions"]
    assert idx2["generated_at"] >= disk1["generated_at"], "generated_at 应刷新"
    # 增量短路也同步落盘（磁盘索引与返回值等价）
    with open(os.path.join(str(isolated_meta), "actions.index.json"),
              encoding="utf-8") as f:
        disk2 = json.load(f)
    assert disk2["actions"] == disk1["actions"]


def test_build_index_incremental_with_change_rebuilds(tmp_path, monkeypatch,
                                                      isolated_meta):
    """incremental=True 但有变更：不短路，走全量构建但未变更文件免解析。"""
    _reset_scan_attrs()
    parsed = _count_parse_calls(monkeypatch)
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid in ("a", "b"):
        _write_action(actions_dir, aid)
    idx1 = build_index(actions_dir=str(actions_dir), meta_dir=str(isolated_meta),
                       incremental=True)
    assert len(parsed) == 2

    _write_action(actions_dir, "c", mtime_bump=5)
    parsed.clear()
    idx2 = build_index(actions_dir=str(actions_dir), meta_dir=str(isolated_meta),
                       incremental=True)
    assert sorted(idx2["actions"]) == ["t0r7.a", "t0r7.b", "t0r7.c"]
    assert len(parsed) == 1, "有变更时未变更文件不得重复解析（应只解析新文件 c）"


# ──────────────────────────────────────────────────────────────
# ③ 后台重建：重建期间旧索引可用 + 完成后原子切换
# ──────────────────────────────────────────────────────────────

def test_background_rebuild_old_index_during_then_atomic_switch(
        tmp_path, monkeypatch, isolated_meta):
    """重建期间 load_index 继续读旧索引；重建完成后原子切换到新索引。"""
    _reset_scan_attrs()
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid in ("a", "b"):
        _write_action(actions_dir, aid)
    build_index(actions_dir=str(actions_dir), meta_dir=str(isolated_meta))
    # 此时磁盘只有 2 个动作
    assert sorted(load_index(meta_dir=str(isolated_meta))["actions"]) == \
        ["t0r7.a", "t0r7.b"]

    # 新增第 3 个动作（mtime 推到未来，保证增量判定/重建都会带上它）
    _write_action(actions_dir, "c", mtime_bump=10)

    # 慢构建包装：进入真实构建前先发信号 + 睡眠，制造「重建进行中」窗口
    entered = threading.Event()
    orig_build = indexer.build_index

    def slow_build(*args, **kwargs):
        entered.set()
        time.sleep(0.6)
        return orig_build(*args, **kwargs)

    monkeypatch.setattr(indexer, "build_index", slow_build)
    rb = BackgroundIndexRebuilder(actions_dir=str(actions_dir),
                                  meta_dir=str(isolated_meta))
    assert rb.start() is True
    assert rb.running is True
    # 等待线程进入重建（确定落在慢构建窗口内）
    assert entered.wait(10), "后台线程未进入重建阶段"
    # 重建期间：查询方继续用旧索引（只有 2 个动作）
    during = load_index(meta_dir=str(isolated_meta))
    assert sorted(during["actions"]) == ["t0r7.a", "t0r7.b"], \
        "重建期间查询必须继续用旧索引（双缓冲）"

    rb.join(timeout=20)
    assert not rb.running
    assert rb.error is None, f"后台重建不应失败: {rb.error}"
    # 重建完成后：原子切换，查询方读到新索引（3 个动作）
    after = load_index(meta_dir=str(isolated_meta))
    assert sorted(after["actions"]) == ["t0r7.a", "t0r7.b", "t0r7.c"], \
        "重建完成后应原子切换到新索引"
    assert rb.last_index is not None
    assert sorted(rb.last_index["actions"]) == ["t0r7.a", "t0r7.b", "t0r7.c"]


def test_background_rebuild_start_idempotent(tmp_path, monkeypatch,
                                             isolated_meta):
    """start() 幂等：已有重建线程在跑时不叠线程。"""
    _reset_scan_attrs()
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid in ("a", "b"):
        _write_action(actions_dir, aid)
    build_index(actions_dir=str(actions_dir), meta_dir=str(isolated_meta))

    entered = threading.Event()
    orig_build = indexer.build_index

    def slow_build(*args, **kwargs):
        entered.set()
        time.sleep(1.0)
        return orig_build(*args, **kwargs)

    monkeypatch.setattr(indexer, "build_index", slow_build)
    rb = BackgroundIndexRebuilder(actions_dir=str(actions_dir),
                                  meta_dir=str(isolated_meta))
    assert rb.start() is True
    assert entered.wait(10)
    assert rb.start() is False, "已有线程在跑时第二次 start 必须返回 False"
    rb.join(timeout=20)
    assert rb.error is None


# ──────────────────────────────────────────────────────────────
# ④ 后台重建失败：回退旧索引不崩溃
# ──────────────────────────────────────────────────────────────

def test_background_rebuild_failure_keeps_old_index(tmp_path, monkeypatch,
                                                    isolated_meta):
    """构建失败 → 保留线上旧索引、error 可见、查询不崩溃。"""
    _reset_scan_attrs()
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid in ("a", "b"):
        _write_action(actions_dir, aid)
    idx_old = build_index(actions_dir=str(actions_dir),
                          meta_dir=str(isolated_meta))
    with open(os.path.join(str(isolated_meta), "actions.index.json"),
              encoding="utf-8") as f:
        disk_old = json.load(f)

    def boom(*args, **kwargs):
        raise RuntimeError("boom: injected rebuild failure")

    monkeypatch.setattr(indexer, "build_index", boom)
    rb = BackgroundIndexRebuilder(actions_dir=str(actions_dir),
                                  meta_dir=str(isolated_meta))
    assert rb.start() is True
    rb.join(timeout=10)
    assert rb.error is not None and "boom" in rb.error
    # 线上索引未被破坏：内容与重建前一致（旧索引回退）
    with open(os.path.join(str(isolated_meta), "actions.index.json"),
              encoding="utf-8") as f:
        disk_after = json.load(f)
    assert disk_after["actions"] == disk_old["actions"], \
        "重建失败必须保留旧索引（回退）"
    # 查询不崩溃，仍可用旧索引
    loaded = load_index(meta_dir=str(isolated_meta))
    assert loaded["actions"] == idx_old["actions"]
    assert "rebuild_reason" not in loaded, "指纹一致时不应触发再次重建"


def test_rebuild_index_background_entrypoint(tmp_path, monkeypatch,
                                             isolated_meta):
    """rebuild_index_background 入口返回句柄，完成后线上切到新索引。"""
    _reset_scan_attrs()
    actions_dir = tmp_path / "actions"
    actions_dir.mkdir()
    for aid in ("a",):
        _write_action(actions_dir, aid)
    build_index(actions_dir=str(actions_dir), meta_dir=str(isolated_meta))
    _write_action(actions_dir, "b", mtime_bump=10)

    rb = rebuild_index_background(actions_dir=str(actions_dir),
                                  meta_dir=str(isolated_meta))
    assert isinstance(rb, BackgroundIndexRebuilder)
    assert rb.running
    rb.join(timeout=20)
    assert rb.error is None
    assert sorted(load_index(meta_dir=str(isolated_meta))["actions"]) == \
        ["t0r7.a", "t0r7.b"]
