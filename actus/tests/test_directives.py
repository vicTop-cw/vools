# -*- coding: utf-8 -*-
"""块指令解析的引号与空格处理（第 26 轮）。

缺陷：裸 `key=value` 路径的值模式是 `\\S+`，于是
  - `title="Calculator App"` 被空格截断成 `"Calculator`
  - 引号**从不剥离** —— 实测种子动作的 title 解析出 `'"Calculator"'`（带引号）
现在值支持成对引号且含空格，并统一剥离成对引号。
"""
import pytest

from vools.bridge.md.directives import parse_block_directives


def test_plain_key_value():
    assert parse_block_directives("#!run tag=main")["tag"] == "main"


def test_quoted_value_with_space():
    """核心回归：带空格的引号值不能被截断。"""
    d = parse_block_directives('#!run title="Calculator App"')
    assert d["title"] == "Calculator App", d


def test_single_quoted_value_with_space():
    d = parse_block_directives("#!run title='a b'")
    assert d["title"] == "a b", d


def test_quotes_are_stripped():
    """引号必须被剥离（此前保留成 '"Calculator"'）。"""
    d = parse_block_directives('#!run title="Calculator"')
    assert d["title"] == "Calculator", d


def test_quoted_value_containing_equals():
    d = parse_block_directives('#!run expr="a=b"')
    assert d["expr"] == "a=b", d


def test_unicode_value_with_space():
    d = parse_block_directives('#!run title="计算器 演示"')
    assert d["title"] == "计算器 演示", d


def test_multiple_keys():
    d = parse_block_directives("#!run tag=main timeout=10 retries=3")
    assert d["tag"] == "main"
    assert d["timeout"] == "10"
    assert d["retries"] == "3"


def test_empty_value_is_kept_as_empty_string():
    """`tag=` 应留下空值键，而不是把整个键丢掉。"""
    d = parse_block_directives("#!run tag=")
    assert "tag" in d and d["tag"] == "", d


def test_unclosed_quote_kept_raw():
    """未闭合引号保持原样（宽松，不抛异常）。"""
    d = parse_block_directives('#!run title="abc')
    assert d["title"] == '"abc', d


def test_no_directive_defaults_to_run():
    assert parse_block_directives("") == {"run": ""}


def test_seed_action_title_has_no_quotes():
    """真实种子动作的 title 不应带引号。"""
    import os
    from vools.actus.model import parse_cfg_from_file
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "vools", "actus", "actions", "basics",
                        "calculator.actus.schema.md")
    action = parse_cfg_from_file(path)
    titles = [b.get("directives", {}).get("title")
              for b in action.blocks if b.get("tag")]
    assert "Calculator" in titles, titles
    assert not any(t and t.startswith('"') for t in titles if t), titles
