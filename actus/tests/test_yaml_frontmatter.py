# -*- coding: utf-8 -*-
"""YAML front-matter 解析的行为契约（第 27 轮探测沉淀）。

结论：front-matter 走的是**真 PyYAML**（不是手写解析），因此多行块、列表、
注释、类型推断都符合规范；两处「报错」也是**正确的 YAML 行为**而非缺陷：
  - 值里出现未加引号的 `: `（`description: 用法: 直接运行`）
  - 顶层键被缩进（`  description: x`）
本组把这些行为锁住，防止有人把手写解析器塞进来时悄悄改变语义。
"""
import os

import pytest

from vools.actus.model import parse_cfg_from_file

BASE = """id: myapp.probe
name: Probe
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
"""

DOC = """---
{meta}---

# N

```python #!run tag=main
print(1)
```
"""


def _parse(tmp_path, meta):
    path = tmp_path / "a.actus.schema.md"
    path.write_text(DOC.format(meta=meta), encoding="utf-8", newline="")
    return parse_cfg_from_file(str(path))


def test_multiline_literal_block(tmp_path):
    a = _parse(tmp_path, BASE + "description: |\n  第一行\n  第二行\n")
    assert a.meta["description"] == "第一行\n第二行"


def test_multiline_folded_block(tmp_path):
    a = _parse(tmp_path, BASE + "description: >\n  第一行\n  第二行\n")
    assert a.meta["description"] == "第一行 第二行"


def test_inline_list(tmp_path):
    a = _parse(tmp_path, BASE + "tags: [a, b, c]\n")
    assert a.meta["tags"] == ["a", "b", "c"]


def test_block_list(tmp_path):
    a = _parse(tmp_path, BASE + "tags:\n  - a\n  - b\n")
    assert a.meta["tags"] == ["a", "b"]


def test_quoted_value_with_colon(tmp_path):
    """含 `: ` 的值必须加引号——加了就能正确解析。"""
    a = _parse(tmp_path, BASE + 'description: "用法: 直接运行"\n')
    assert a.meta["description"] == "用法: 直接运行"


def test_unquoted_colon_is_rejected(tmp_path):
    """未加引号的 `: ` 是非法 YAML——必须报 action_invalid 而不是悄悄截断。"""
    with pytest.raises(Exception) as exc:
        _parse(tmp_path, BASE + "description: 用法: 直接运行\n")
    assert getattr(exc.value, "code", "") == "action_invalid", exc.value


def test_comment_line_ignored(tmp_path):
    a = _parse(tmp_path, BASE + "# 注释\ndescription: ok\n")
    assert a.meta["description"] == "ok"


def test_types_are_inferred(tmp_path):
    a = _parse(tmp_path, BASE + "deprecated: true\npriority: 3\n")
    assert a.meta["deprecated"] is True
    assert a.meta["priority"] == 3


def test_unicode_value(tmp_path):
    a = _parse(tmp_path, BASE + "description: 中文描述 带空格\n")
    assert a.meta["description"] == "中文描述 带空格"


def test_hash_in_value_needs_quotes(tmp_path):
    """` #` 在 YAML 里是注释起点——要保留井号必须加引号。"""
    a = _parse(tmp_path, BASE + "description: a # 会被当注释\n")
    assert a.meta["description"] == "a"
    b = _parse(tmp_path, BASE + 'description: "a # 保留"\n')
    assert b.meta["description"] == "a # 保留"
