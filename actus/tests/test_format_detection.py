# -*- coding: utf-8 -*-
"""计划 §3.4/§六.5：任意「新格式后缀」的动作文件都必须能解析。

缺陷：格式检测原先**只看后缀** `.actus.schema.md`——计划 §3.4 后缀矩阵里的
*.demo.actus.md / *.link.actus.md / *.template.actus.md 同样是 YAML
front-matter 形态，却被丢进旧格式分支，报「缺少 ```json #!cfg 元数据块」。
实测 4 个 demo 文件全部中招（§六.5 说的『存量 error』就是这个味道）。

第一次修（只看首行 `---`）又误伤了旧格式文件：actions/foo.actus.md 开头的
`---` 是 **Markdown 分隔线**，后面跟 AIGC 元数据块。最终判据要求
front-matter 里必须含 `id:` 行。
"""
import os

from vools.actus.model import _has_yaml_frontmatter, parse_cfg_from_file

NEW_DEMO = """---
id: myapp.demo
name: Demo
version: 1.0.0
trust: sandbox
kind: demo
platform: desktop
description: demo 资产
---

# 演示

```bash
actus run myapp.target
```
"""

OLD_WITH_RULE = """---

AIGC:

    Label: "1"

    ContentProducer: 001191440300708461136T1XGW3

```json #!cfg
{"id": "myapp.legacy", "name": "Legacy", "version": "1.0.0",
 "trust": "sandbox", "entry": "main", "platform": "desktop"}
```

# Legacy

```python #!run tag=main
print("ok")
```
"""


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="")
    return p


def test_demo_suffix_parses_as_new_format(tmp_path):
    """.demo.actus.md（非 .actus.schema.md 后缀）必须按 YAML 解析成功。"""
    p = _write(tmp_path, "x.demo.actus.md", NEW_DEMO)
    action = parse_cfg_from_file(str(p))
    assert action.meta["id"] == "myapp.demo"
    assert action.kind == "demo"


def test_old_format_with_leading_rule_still_uses_classic_parser(tmp_path):
    """旧格式文件开头的 `---` 是分隔线，不能误判成 front-matter。"""
    p = _write(tmp_path, "legacy.actus.md", OLD_WITH_RULE)
    action = parse_cfg_from_file(str(p))
    assert action.meta["id"] == "myapp.legacy"
    assert len(action.md5) == 32


def test_has_yaml_frontmatter_discriminates():
    assert _has_yaml_frontmatter(NEW_DEMO) is True
    assert _has_yaml_frontmatter(OLD_WITH_RULE) is False
    assert _has_yaml_frontmatter("# just markdown\n") is False


def test_all_shipped_action_files_parse():
    """仓库里所有动作文件都必须能解析（§六.5 存量 error 的真实口径）。"""
    from vools.actus.constants import is_action_file
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "vools", "actus", "actions")
    bad = []
    for root, _dirs, files in os.walk(base):
        for fname in files:
            if not is_action_file(fname):
                continue
            path = os.path.join(root, fname)
            try:
                action = parse_cfg_from_file(path)
                if not action.meta.get("id"):
                    bad.append((fname, "缺少 id"))
            except Exception as exc:
                bad.append((fname, str(exc)[:80]))
    assert not bad, "仍有动作文件解析失败: %s" % bad
