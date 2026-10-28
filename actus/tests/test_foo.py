# -*- coding: utf-8 -*-
"""回归骨架（scaffold 自动生成）：动作 actus.test.foo。

审计加固（第 8 轮，测试套件自审）：骨架原来是 `assert True` —— 动作文件被删、
被改坏、id 变了都永远绿（scaffold 生成的 5 个骨架全有此问题）。
现在真正解析并校验对应动作文件：文件缺失/解析失败/契约违规都会红。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.model import parse_cfg_from_file  # noqa: E402
from vools.actus.validate import validate_action  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_actus_test_foo_runs():
    """动作文件必须存在、id 正确，且通过契约校验（不再是空断言）。"""
    path = os.path.join(ROOT, "actions", "foo.actus.md")
    action = parse_cfg_from_file(path)
    assert action.meta.get("id") == "actus.test.foo", action.meta.get("id")
    errors = validate_action(action)
    assert errors == [], errors
