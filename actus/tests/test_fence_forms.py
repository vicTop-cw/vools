# -*- coding: utf-8 -*-
"""markdown 围栏形态的兼容性（第 25 轮）。

原解析器 `_FENCE_RE = ^```(\\w*)\\s*(.*)$` 只认**列 0 的反引号围栏**，
而以下都是合法 CommonMark、都会让动作文件的代码块被整块漏掉，用户只看到
莫名的「entry 未找到」：
  - `~~~` 波浪号围栏
  - 缩进 ≤3 空格的围栏
  - 4 个以上反引号开启、内部含 3 个反引号（原实现会提前闭合且丢语言）

现在按 CommonMark 规则解析：0-3 空格缩进、反引号或波浪号 3+ 个、
闭合需同字符且不短于开启长度。
"""
import os

import pytest

from vools.actus.model import parse_cfg_from_file

FENCE = "`" * 3
TILDE = "~" * 3

FM = """---
id: myapp.probe
name: N
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
description: probe
---

# N

{body}
"""


def _parse(tmp_path, body):
    path = tmp_path / "a.actus.schema.md"
    path.write_text(FM.format(body=body), encoding="utf-8", newline="")
    return parse_cfg_from_file(str(path))


def _blocks(action):
    return [(b.get("language"), b.get("tag")) for b in action.blocks]


def test_standard_backtick_fence(tmp_path):
    a = _parse(tmp_path, "%spython #!run tag=main\nprint(1)\n%s\n" % (FENCE, FENCE))
    assert _blocks(a) == [("python", ["main"])]


def test_tilde_fence(tmp_path):
    """`~~~` 是合法 CommonMark 围栏（原实现漏掉）。"""
    a = _parse(tmp_path, "%spython #!run tag=main\nprint(1)\n%s\n" % (TILDE, TILDE))
    assert _blocks(a) == [("python", ["main"])], _blocks(a)


def test_three_space_indented_fence(tmp_path):
    """≤3 空格缩进的围栏是合法的（原实现漏掉）。"""
    a = _parse(tmp_path,
               "   %spython #!run tag=main\n   print(1)\n   %s\n" % (FENCE, FENCE))
    assert _blocks(a) == [("python", ["main"])], _blocks(a)


def test_four_space_indent_is_not_a_fence(tmp_path):
    """4 空格缩进是缩进式代码块，不是围栏——必须仍然不产生动作块。"""
    a = _parse(tmp_path,
               "    %spython #!run tag=main\n    print(1)\n    %s\n" % (FENCE, FENCE))
    assert _blocks(a) == []


def test_longer_fence_with_inner_backticks(tmp_path):
    """4 反引号开启时，内部的 3 反引号不应提前闭合，语言也不能丢。"""
    four = "`" * 4
    a = _parse(tmp_path,
               "%spython #!run tag=main\nprint('%s')\n%s\n" % (four, FENCE, four))
    assert _blocks(a) == [("python", ["main"])], _blocks(a)


def test_fence_with_extra_directives(tmp_path):
    a = _parse(tmp_path,
               "%spython #!run tag=main timeout=10\nprint(1)\n%s\n" % (FENCE, FENCE))
    assert _blocks(a) == [("python", ["main"])]


def test_uppercase_language_normalized(tmp_path):
    a = _parse(tmp_path, "%sPython #!run tag=main\nprint(1)\n%s\n" % (FENCE, FENCE))
    assert _blocks(a)[0][0] == "python"


def test_unclosed_fence_still_parses(tmp_path):
    """未闭合围栏保持宽松（向后兼容）。"""
    a = _parse(tmp_path, "%spython #!run tag=main\nprint(1)\n" % FENCE)
    assert _blocks(a) == [("python", ["main"])]
