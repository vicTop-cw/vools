# -*- coding: utf-8 -*-
"""第 18 轮（T0.1.1）：md5 指纹一致性校验回归。

ACTUS_REFACTOR_PLAN §3.6「指纹一致性校验」：索引 md5 vs 文件实际 md5 的一致性告警。
- 一致 → 通过（无告警）
- 文件被改、索引较新 → warning「可能文件被篡改或索引写入异常」
- 文件被改、索引较旧 → warning「索引可能陈旧」
- md5 字段缺失 → 降级不告警
- 索引不存在 → 冷启动不告警
- check_index=False → 跳过（build_index 阶段）
"""
import os
import hashlib
import json
import time

from vools.actus.model import Action, parse_cfg_from_file
from vools.actus.validate import check_md5_consistency, _known_action_ids


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="")
    return p


def _make_action(tmp_path, body_text="print('ok')", md5_override=None, action_id="probe.md5cons"):
    """构造一个 Action（带 md5）+ 写索引到 meta_dir。"""
    raw = (
        "---\n"
        "id: %s\n"
        "name: Md5Cons\n"
        "version: 1.0.0\n"
        "trust: sandbox\n"
        "kind: exec\n"
        "entry: main\n"
        "platform: desktop\n"
        "description: md5 一致性探针\n"
        "---\n\n"
        "# Cons\n\n"
        "```python #!run tag=main\n"
        "%s\n"
        "```\n" % (action_id, body_text)
    )
    p = _write(tmp_path, "probe.actus.schema.md", raw)
    action = parse_cfg_from_file(str(p))
    # 覆盖 md5（用于注入不一致场景）
    if md5_override is not None:
        action.md5 = md5_override
    return action, p, raw


def _write_index(meta_dir, entry_md5, path_mtime=None, extra_fields=None):
    """写一个最小 actions.index.json。"""
    import os
    os.makedirs(meta_dir, exist_ok=True)
    entry = {"id": "probe.md5cons", "md5": entry_md5}
    if extra_fields:
        entry.update(extra_fields)
    idx_path = os.path.join(meta_dir, "actions.index.json")
    obj = {"actions": {"probe.md5cons": entry}}
    # mtime 控制
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    if path_mtime is not None:
        os.utime(idx_path, (path_mtime, path_mtime))
    return idx_path


def _parse_md5(text):
    """从返回的 warning 里提取两个 md5 前缀用于断言。"""
    import re
    m = re.search(r"索引 ([0-9a-f]{8})… ≠ 实际 ([0-9a-f]{8})…", text)
    return m


# ── 核心场景 ──────────────────────────────────────────────

def test_md5_consistency_ok_no_warning(tmp_path):
    """md5 一致 → 无告警。"""
    action, path, raw = _make_action(tmp_path)
    real_md5 = hashlib.md5(raw.encode("utf-8")).hexdigest()
    meta_dir = str(tmp_path / "_meta")
    _write_index(meta_dir, real_md5)
    # 索引 mtime 晚于文件（正常重建后的状态）
    warnings = check_md5_consistency(action, meta_dir)
    assert warnings == [], "md5 一致不应告警: %r" % warnings


def test_md5_consistency_tampered_index_newer(tmp_path):
    """文件被改、索引 mtime 晚于文件 → 告警「篡改/异常」。"""
    action, path, raw = _make_action(tmp_path)
    real_md5 = hashlib.md5(raw.encode("utf-8")).hexdigest()
    wrong_md5 = hashlib.md5(b"tampered").hexdigest()
    meta_dir = str(tmp_path / "_meta")
    # 索引写个错误的 md5，但 mtime 设为 file mtime + 1（索引较新）
    file_mtime = os.path.getmtime(path)
    _write_index(meta_dir, wrong_md5, path_mtime=file_mtime + 10)
    # action.md5 仍是文件真实 md5（parse 得来）
    assert action.md5 == real_md5
    warnings = check_md5_consistency(action, meta_dir)
    assert len(warnings) == 1, "应有一条告警: %r" % warnings
    assert "篡改" in warnings[0] or "异常" in warnings[0], "索引较新应报篡改/异常: %r" % warnings[0]
    m = _parse_md5(warnings[0])
    assert m, "告警应包含两个 md5 前缀: %r" % warnings[0]
    assert m.group(1) == wrong_md5[:8]
    assert m.group(2) == real_md5[:8]


def test_md5_consistency_stale_index_older(tmp_path):
    """文件被改、索引 mtime 早于文件 → 告警「索引陈旧」。"""
    action, path, raw = _make_action(tmp_path)
    real_md5 = hashlib.md5(raw.encode("utf-8")).hexdigest()
    old_md5 = hashlib.md5(b"old content").hexdigest()
    meta_dir = str(tmp_path / "_meta")
    # 索引写旧 md5，但 mtime 设为 file mtime - 10（索引较旧）
    file_mtime = os.path.getmtime(path)
    _write_index(meta_dir, old_md5, path_mtime=file_mtime - 10)
    warnings = check_md5_consistency(action, meta_dir)
    assert len(warnings) == 1, "应有一条告警: %r" % warnings
    assert "陈旧" in warnings[0], "索引较旧应报陈旧: %r" % warnings[0]


def test_md5_consistency_missing_index_md5_skips(tmp_path):
    """索引 md5 字段缺失 → 降级不告警。"""
    action, path, raw = _make_action(tmp_path)
    meta_dir = str(tmp_path / "_meta")
    _write_index(meta_dir, "")  # md5 为空
    warnings = check_md5_consistency(action, meta_dir)
    assert warnings == [], "索引 md5 缺失应降级不告警: %r" % warnings


def test_md5_consistency_missing_action_md5_skips(tmp_path):
    """动作 md5 字段缺失 → 降级不告警。"""
    action, path, raw = _make_action(tmp_path)
    action.md5 = ""  # 清空
    meta_dir = str(tmp_path / "_meta")
    _write_index(meta_dir, hashlib.md5(raw.encode("utf-8")).hexdigest())
    warnings = check_md5_consistency(action, meta_dir)
    assert warnings == [], "动作 md5 缺失应降级不告警: %r" % warnings


def test_md5_consistency_no_index_skips(tmp_path):
    """索引文件不存在 → 冷启动不告警。"""
    action, path, raw = _make_action(tmp_path)
    warnings = check_md5_consistency(action, str(tmp_path / "_meta"))
    assert warnings == [], "索引不存在应冷启动不告警: %r" % warnings


# ── check_index=False 路径 ─────────────────────────────────

def test_validate_action_skips_md5_when_check_index_false(tmp_path, monkeypatch):
    """build_index 阶段（check_index=False）不跑 md5 一致性。"""
    from vools.actus.validate import validate_action
    from vools.actus import paths as _paths
    action, path, raw = _make_action(tmp_path)
    # 把 paths.meta_dir 指向一个带不一致索引的目录
    meta_dir = str(tmp_path / "_meta")
    _write_index(meta_dir, hashlib.md5(b"wrong").hexdigest(), path_mtime=os.path.getmtime(path) + 10)
    monkeypatch.setattr(_paths, "meta_dir", lambda: meta_dir, raising=False)
    # validate.py 里 from .paths import meta_dir as _paths_meta_dir 是导入时绑定，
    # 需要重新导入或直接 patch validate 模块里的名字
    from vools.actus import validate as _v
    # _paths_meta_dir 在 validate 模块里是导入时绑定的名字
    if hasattr(_v, "_paths_meta_dir"):
        monkeypatch.setattr(_v, "_paths_meta_dir", lambda: meta_dir)
    errors = validate_action(action, check_index=False)
    md5_warns = [e for e in errors if "md5" in e and "不一致" in e]
    assert md5_warns == [], "check_index=False 不应跑 md5 一致性: %r" % md5_warns
    # 对照：check_index=True 应产生 md5 告警
    errors_ci = validate_action(action, check_index=True)
    md5_warns_ci = [e for e in errors_ci if "md5" in e and "不一致" in e]
    assert len(md5_warns_ci) == 1, "check_index=True 应跑 md5 一致性并告警: %r" % md5_warns_ci
