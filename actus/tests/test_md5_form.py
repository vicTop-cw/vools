# -*- coding: utf-8 -*-
"""阶段1：md5 target 形态的回归（32 位 hex 内容指纹）。

缺陷：`parse_cfg_from_file` 在 `.actus.schema.md` 分支调用
`_parse_schema_md_action(raw, path, sha)` 时**漏传 md5**（md5 已经在上面
算好），导致新格式动作的 `Action.md5` 恒为 '' ⇒ 索引 by_md5 收不到它们
⇒ resolver 的「32 位 hex 内容指纹」形态形同虚设（实测索引 7 条里只有旧
格式的 3 条有 md5）。
"""
import hashlib

from vools.actus.model import parse_cfg_from_file

SCHEMA_ACTION = """---
id: myapp.md5probe
name: Md5Probe
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
description: md5 形态探针
---

# Probe

```python #!run tag=main
print("ok")
```
"""


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="")
    return p


def test_schema_md_action_has_md5(tmp_path):
    """新格式动作必须带 md5（缺陷的直接回归）。"""
    p = _write(tmp_path, "probe.actus.schema.md", SCHEMA_ACTION)
    action = parse_cfg_from_file(str(p))
    assert len(action.md5) == 32, "新格式动作的 md5 为空: %r" % action.md5
    assert action.md5 == hashlib.md5(SCHEMA_ACTION.encode("utf-8")).hexdigest()
    assert action.brief().get("md5") == action.md5


def test_index_records_md5_for_schema_actions(tmp_path):
    """索引必须把新格式动作的 md5 收进 by_md5。"""
    from vools.actus.indexer import scan_actions
    _write(tmp_path, "probe.actus.schema.md", SCHEMA_ACTION)
    # 测试卫生：关掉 mtime 缓存，避免 scan_actions 把缓存写进真实仓库 _meta/。
    actions = scan_actions(str(tmp_path), validate=False, use_cache=False)
    hit = actions.get("myapp.md5probe")
    assert hit is not None, "索引里找不到动作"
    assert len(hit.md5) == 32, "索引里的 md5 为空"
