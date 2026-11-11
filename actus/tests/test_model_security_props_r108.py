# -*- coding: utf-8 -*-
"""actus/tests/test_model_security_props_r108.py — model.py 安全白名单 property
与解析入口专项（统帅轮-14时，COVERAGE_AUDIT_R105 第二批）。

测什么 / 为什么
---------------
* docs/46 #5/#6/#7 安全契约的便捷读取面此前零直接测试：
  reserved_env（保留环境变量白名单）/ net_connect / net_listen（外连/监听
  端点白名单）/ timeout_ms / max_memory_mb / max_processes——**安全语义
  property 的默认值方向必须锚死**（缺声明 = 收紧默认，不能放开）；
* context_applies（单值→list 归一）/ cached_artifacts / purpose/industry
  默认值；
* parse_action_from_schema_md：编辑器/IDE 集成用的纯文本解析入口
  （sha256+md5 指纹计算、必填字段校验、entry 仅对 kind=exec 必填）。

py3.8+（pyproject requires-python>=3.8），标准库。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.model import Action, parse_action_from_schema_md  # noqa: E402
from vools.actus.errors import ActionError  # noqa: E402


def _action(meta=None):
    """最小 Action 构造（dataclass 直造，不经文件解析）。"""
    base = {"id": "core.add", "name": "Add", "version": "1.0.0",
            "trust": "sandbox", "entry": "main"}
    base.update(meta or {})
    return Action(meta=base, path="actions/add.actus.md",
                  sha256="0" * 64, md5="f" * 32)


# ---------------------------------------------------------------------------
# docs/46 #5：reserved_env（保留环境变量白名单）
# ---------------------------------------------------------------------------

def test_reserved_env_declared():
    a = _action({"context": {"reserved_env": ["PATH", "TEMP"]}})
    assert a.reserved_env == ["PATH", "TEMP"]


def test_reserved_env_missing_meta_defaults_empty():
    """缺声明 → []（收紧默认：白名单缺省为空，不是放开）。"""
    assert _action().reserved_env == []
    assert _action({"context": None}).reserved_env == []


# ---------------------------------------------------------------------------
# docs/46 #7：net_connect / net_listen（端点白名单）
# ---------------------------------------------------------------------------

def test_net_connect_declared():
    a = _action({"resources": {"net_connect": ["api.example.com:443"]}})
    assert a.net_connect == ["api.example.com:443"]


def test_net_listen_declared():
    a = _action({"resources": {"net_listen": ["127.0.0.1:8080"]}})
    assert a.net_listen == ["127.0.0.1:8080"]


@pytest.mark.parametrize("prop", ["net_connect", "net_listen"])
def test_net_defaults_empty_when_missing(prop):
    """缺声明 → []（收紧默认：外连/监听缺省全禁，不是全开）。"""
    assert getattr(_action(), prop) == []
    assert getattr(_action({"resources": None}), prop) == []


def test_resource_limits_int_coercion():
    """timeout_ms/max_memory_mb/max_processes 字符串数字 → int 归一，缺省 0=不限。"""
    a = _action({"resources": {"timeout_ms": "5000", "max_memory_mb": "512",
                               "max_processes": "4"}})
    assert a.timeout_ms == 5000
    assert a.max_memory_mb == 512
    assert a.max_processes == 4
    b = _action()
    assert (b.timeout_ms, b.max_memory_mb, b.max_processes) == (0, 0, 0)


# ---------------------------------------------------------------------------
# context_applies / cached_artifacts / purpose / industry 归一
# ---------------------------------------------------------------------------

def test_context_applies_single_value_wraps_list():
    """单值 → [值] 归一；None → []。"""
    assert _action({"context_applies": "app.exe"}).context_applies == ["app.exe"]
    assert _action({"context_applies": ["a.exe", "*.md"]}).context_applies == \
        ["a.exe", "*.md"]
    assert _action().context_applies == []


def test_cached_artifacts_default_empty():
    assert _action().cached_artifacts == []
    assert _action({"cached_artifacts": ["lib/demo.dll"]}).cached_artifacts == \
        ["lib/demo.dll"]


def test_purpose_industry_defaults():
    """多值分类默认值锚定（docs/03 §2）。"""
    assert _action().purpose == ["utility"]
    assert _action().industry == ["general"]
    assert _action({"purpose": "transform"}).purpose == ["transform"]


# ---------------------------------------------------------------------------
# parse_action_from_schema_md：纯文本解析入口
# ---------------------------------------------------------------------------

SCHEMA_MD = (
    "---\n"
    "id: editor.parsed.demo\n"
    "name: EditorParsed\n"
    "version: 1.2.3\n"
    "trust: sandbox\n"
    "entry: main\n"
    "---\n"
    "\n"
    "#!entry main\n"
    "```python #!tag=main\n"
    "print('hi')\n"
    "```\n"
)


def test_parse_schema_md_happy_path():
    a = parse_action_from_schema_md(SCHEMA_MD, "actions/demo.actus.schema.md")
    assert a.id == "editor.parsed.demo"
    assert a.meta["name"] == "EditorParsed"
    assert a.meta["version"] == "1.2.3"
    assert a.trust == "sandbox"
    assert a.entry == "main"
    assert a.path == "actions/demo.actus.schema.md"


def test_parse_schema_md_fingerprints_deterministic():
    """sha256/md5 对同一文本确定；不同文本指纹不同。"""
    a1 = parse_action_from_schema_md(SCHEMA_MD)
    a2 = parse_action_from_schema_md(SCHEMA_MD)
    assert a1.sha256 == a2.sha256 and a1.md5 == a2.md5
    a3 = parse_action_from_schema_md(SCHEMA_MD + "\n")
    assert a3.sha256 != a1.sha256


def test_parse_schema_md_missing_required_raises_action_invalid():
    """缺 id → ActionError(action_invalid)，details 带 hint。"""
    broken = SCHEMA_MD.replace("id: editor.parsed.demo\n", "")
    with pytest.raises(ActionError) as exc_info:
        parse_action_from_schema_md(broken)
    assert exc_info.value.code == "action_invalid"
    assert "缺少必填字段" in exc_info.value.message
    assert "hint" in exc_info.value.details


def test_parse_schema_md_non_exec_entry_optional():
    """entry 仅对 kind=exec 必填（ACTUS_REFACTOR_PLAN 阶段3.6）——
    kind=link 无入口块也能解析。"""
    link_md = SCHEMA_MD.replace("trust: sandbox\n", "trust: sandbox\nkind: link\ntarget: core.add\n").replace(
        "entry: main\n", "")
    a = parse_action_from_schema_md(link_md)
    assert a.kind == "link"
    assert a.target == "core.add"
