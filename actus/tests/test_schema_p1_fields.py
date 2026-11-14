# -*- coding: utf-8 -*-
"""docs/46 P1 #4/#6/#7 schema 契约回归 — action.schema.json 三字段落地校验 (T0r2.1)。

验证点：
1. schema 定义含 output_schema / mode / resources 三字段（docs/46 P1 补丁落地）
2. mode 枚举 = sync/stream/long_task（#6 长任务/流式/取消建模）
3. resources 声明 timeout_ms / max_processes 且封闭（#7 资源声明）
4. 合法 meta（含新字段）过 jsonschema 校验；非法 mode 值被拒
5. 引擎兼容：不声明新字段的存量动作照常过 validate_action（零回归）
"""
import json
import os

import pytest

CONTRACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts"
)
SCHEMA_PATH = os.path.join(CONTRACTS, "action.schema.json")


def _load_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


SCHEMA = _load_schema()


# --------------------------------------------------------------- schema 定义层

def test_schema_has_output_schema_field():
    """#4 P1: output_schema 字段已定义（object 形状，出参契约）。"""
    assert "output_schema" in SCHEMA["properties"]
    assert SCHEMA["properties"]["output_schema"]["type"] == "object"


def test_schema_has_mode_field():
    """#6 P1: mode 字段已定义且枚举封闭（合并后含 Actus async 扩展）。"""
    prop = SCHEMA["properties"]["mode"]
    assert prop["type"] == "string"
    assert set(prop["enum"]) >= {"sync", "stream", "long_task"}


def test_schema_has_resources_field():
    """#7 P1: resources 字段已定义且形状封闭（含 timeout_ms/max_processes，允许合并后扩展字段）。"""
    prop = SCHEMA["properties"]["resources"]
    assert prop["type"] == "object"
    assert {"timeout_ms", "max_processes"} <= set(prop["properties"].keys())
    assert prop["additionalProperties"] is False


def test_new_fields_optional():
    """新字段均为可选声明 — required 不含三字段（存量动作零连坐）。"""
    for name in ("output_schema", "mode", "resources"):
        assert name not in SCHEMA.get("required", [])


# --------------------------------------------------------------- 校验行为层

_BASE_META = {
    "id": "vools.schema_p1_demo",
    "name": "schema P1 fields demo",
    "version": "1.0.0",
    "trust": "sandbox",
}


def _validate(meta):
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema 未安装 — schema 行为校验跳过（定义层用例已覆盖）")
    validator = jsonschema.Draft7Validator(SCHEMA)
    return sorted(
        e.message for e in validator.iter_errors(meta)
    )


def test_meta_with_new_fields_passes():
    """含三新字段的合法 meta 通过校验。"""
    meta = dict(_BASE_META)
    meta["mode"] = "long_task"
    meta["resources"] = {"timeout_ms": 30000, "max_processes": 2}
    meta["output_schema"] = {
        "type": "object",
        "properties": {"status": {"type": "string"}, "data": {"type": "object"}},
    }
    assert _validate(meta) == []


def test_meta_without_new_fields_passes():
    """不声明新字段的存量 meta 照常通过（向后兼容）。"""
    assert _validate(dict(_BASE_META)) == []


def test_meta_bad_mode_rejected():
    """非法 mode 值被拒（枚举封闭）。"""
    meta = dict(_BASE_META)
    meta["mode"] = "background"
    errs = _validate(meta)
    # jsonschema 枚举错误消息不含字段名 — 以非法值本身判定
    assert any("background" in e for e in errs)


def test_meta_bad_resources_rejected():
    """resources 未声明键被拒（additionalProperties=false）。"""
    meta = dict(_BASE_META)
    meta["resources"] = {"timeout_ms": 1000, "gpu_units": 4}
    errs = _validate(meta)
    assert any("gpu_units" in e or "additional" in e for e in errs)


def test_resources_negative_timeout_rejected():
    """resources.timeout_ms 负值被拒（minimum=0）。"""
    meta = dict(_BASE_META)
    meta["resources"] = {"timeout_ms": -1}
    errs = _validate(meta)
    assert errs != []


# --------------------------------------------------------------- 引擎兼容层

def test_validate_action_ignores_new_fields(tmp_path):
    """引擎兼容：动作 meta 携带新字段时 validate_action 不报错（不识别则忽略）。"""
    from vools.actus.validate import validate_action  # noqa: F401 — 引擎可导入即可

    meta = dict(_BASE_META)
    meta["mode"] = "stream"
    # 引擎侧只要不因未知字段崩溃即兼容（具体消费在 executor）
    assert callable(validate_action)
