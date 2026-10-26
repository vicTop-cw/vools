# -*- coding: utf-8 -*-
"""计划 §六.6：三轨查找收口 —— 按 id 查找动作文件必须格式无关。

缺陷：dependency._find_action_file 用**字符串搜** `"id": "xxx"` 判断身份，
只认旧格式 JSON；新格式 YAML front-matter 的 `.actus.schema.md` 全部找不到
（实测 4 个种子动作全返回 None）。现在统一委托给 resolver.find_action_file
（按解析后的 meta['id'] 比对）。
"""
from vools.actus.resolver import find_action_file

NEW_FORMAT = """---
id: myapp.newfmt
name: NewFmt
version: 1.0.0
trust: sandbox
kind: exec
entry: main
platform: desktop
description: 新格式
---

# NewFmt

```python #!run tag=main
print("ok")
```
"""

OLD_FORMAT = """```json #!cfg
{"id": "myapp.oldfmt", "name": "OldFmt", "version": "1.0.0",
 "trust": "sandbox", "entry": "main", "platform": "desktop"}
```

# OldFmt

```python #!run tag=main
print("ok")
```
"""


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="")
    return p


def test_find_action_file_new_format(tmp_path):
    """新格式（YAML front-matter）必须能被按 id 找到。"""
    _write(tmp_path, "newfmt.actus.schema.md", NEW_FORMAT)
    hit = find_action_file("myapp.newfmt", str(tmp_path))
    assert hit is not None, "新格式动作找不到（原缺陷）"
    assert hit.endswith("newfmt.actus.schema.md")


def test_find_action_file_old_format(tmp_path):
    """旧格式（#!cfg JSON）不能因这次收口回归。"""
    _write(tmp_path, "oldfmt.actus.md", OLD_FORMAT)
    hit = find_action_file("myapp.oldfmt", str(tmp_path))
    assert hit is not None, "旧格式动作找不到"
    assert hit.endswith("oldfmt.actus.md")


def test_find_action_file_unknown_returns_none(tmp_path):
    _write(tmp_path, "newfmt.actus.schema.md", NEW_FORMAT)
    assert find_action_file("myapp.missing", str(tmp_path)) is None


def test_find_action_file_tolerates_bad_files(tmp_path):
    """坏文件不能让查找整体失败（跳过即可）。"""
    _write(tmp_path, "broken.actus.schema.md", "not a valid action at all")
    _write(tmp_path, "newfmt.actus.schema.md", NEW_FORMAT)
    assert find_action_file("myapp.newfmt", str(tmp_path)) is not None


def test_dependency_lookup_delegates_and_finds_new_format(tmp_path):
    """dependency 的查找必须委托给单一实现（三轨收口）。"""
    from vools.actus.dependency import DependencyResolver
    _write(tmp_path, "newfmt.actus.schema.md", NEW_FORMAT)
    r = DependencyResolver(actions_root=str(tmp_path))
    assert r._find_action_file("myapp.newfmt") is not None


def test_seed_actions_resolvable_via_shared_helper():
    """真实种子动作（全是新格式）必须能被共享查找找到。"""
    import os
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "vools", "actus", "actions")
    hit = find_action_file("actus.basics.calculator", root)
    assert hit is not None, "种子动作找不到 —— 三轨收口未生效"


def test_no_string_search_identity_antipattern():
    """禁止再用『字符串搜 \"id\": \"xxx\"』判断动作身份（计划 §六.6 反模式）。

    这类写法只认旧格式 JSON 的带引号 id，新格式 YAML front-matter 的动作
    全部匹配不上。允许的例外：mdtest.py 是**生成**夹具的模板，不是查找。
     """
    import glob
    import os
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "vools", "actus")
    offenders = []
    # 第 30 轮补强：还要拦「把 id 包在引号里搜全文」这种更宽松的形态。
    # omega.py 里的那种写法就是这样漏网的——既误命中「描述里提到该 id」的文件，
    # 又认不出新格式 YAML 的 id: xxx。
    # 注意：用 AST 排除 **docstring 行**，否则解释这条反模式的文字本身会被判违规。
    import ast
    import re
    generic = re.compile(
        r"""f["']\\?["']\{(?:action_id|aid)\}\\?["']\\?["']\s+in\s+content""")

    def _doc_lines(tree):
        out = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if body and isinstance(body[0], ast.Expr) and \
                        isinstance(body[0].value, ast.Constant) and \
                        isinstance(body[0].value.value, str):
                    out.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
        return out

    for path in glob.glob(os.path.join(base, "**", "*.py"), recursive=True):
        name = os.path.basename(path)
        if name in ("mdtest.py",):        # 夹具生成器，允许
            continue
        try:
            text = open(path, encoding="utf-8").read()
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue
        skip = _doc_lines(tree)
        for i, line in enumerate(text.splitlines(), 1):
            if i in skip or line.lstrip().startswith("#"):
                continue
            if '"id": "{"' in line or '"id":"{"' in line or generic.search(line):
                offenders.append("%s:%d" % (name, i))
    assert not offenders, "仍有『字符串搜 id』的判断: %s" % offenders
