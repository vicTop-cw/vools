# -*- coding: utf-8 -*-
"""platform 枚举单一真源对齐回归 (T0r4.2, 统帅轮-02时)。

真源 = actus/vools/actus/constants.py 的 PLATFORMS（8 值：
desktop/web/macos/harmonyos/linux/windows/wsl/android）。

缺陷（本轮修复前）：contracts/action.schema.json 的 platform enum 只声明 5 值
（缺 windows/wsl/android），与 check_platform / is_known_platform 的 8 值口径
分裂——声明 platform=windows 的动作过 schema 校验时被误拒，但语义校验放行，
两道门自相矛盾。

验证点：
1. 定义层：schema 两处 enum（单值形态 / 数组 items 形态）与 constants.PLATFORMS 逐项相等
2. 行为层：windows / wsl / android 单值与数组形态过 jsonschema 校验
3. 行为层：未知平台值仍被拒（枚举封闭性不因扩容松动）
4. 语义层：check_platform 与 is_known_platform 同口径（8 值全通过、未知值报错）
"""
import json
import os

import pytest

CONTRACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts"
)
SCHEMA_PATH = os.path.join(CONTRACTS, "action.schema.json")

with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    SCHEMA = json.load(f)

from vools.actus.constants import PLATFORMS, is_known_platform  # noqa: E402
from vools.actus.validate import check_platform  # noqa: E402

# --------------------------------------------------------------- 定义层：单一真源


def _platform_enum_forms():
    """从 schema 提取 platform 的两处 enum（oneOf 单值 / oneOf 数组 items）。"""
    one_of = SCHEMA["properties"]["platform"]["oneOf"]
    single = next(o for o in one_of if o.get("type") == "string")
    array_items = next(o for o in one_of if o.get("type") == "array")["items"]
    return single["enum"], array_items["enum"]


def test_schema_single_enum_equals_constants():
    """schema 单值形态 enum 与 constants.PLATFORMS 逐项相等（真源 8 值）。"""
    single, _ = _platform_enum_forms()
    assert single == list(PLATFORMS)
    assert "windows" in single and "wsl" in single and "android" in single


def test_schema_array_items_enum_equals_constants():
    """schema 数组 items enum 与 constants.PLATFORMS 逐项相等。"""
    _, items = _platform_enum_forms()
    assert items == list(PLATFORMS)


# --------------------------------------------------------------- 行为层：jsonschema

_BASE_META = {
    "id": "vools.platform_enum_demo",
    "name": "platform enum alignment demo",
    "version": "1.0.0",
    "trust": "sandbox",
}


def _schema_errors(meta):
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema 未安装 — schema 行为校验跳过（定义层用例已覆盖）")
    validator = jsonschema.Draft7Validator(SCHEMA)
    return sorted(e.message for e in validator.iter_errors(meta))


@pytest.mark.parametrize("value", ["windows", "wsl", "android"])
def test_new_platform_single_value_passes(value):
    """此前被 schema 误拒的三个值：单值形态放行。"""
    meta = dict(_BASE_META, platform=value)
    assert _schema_errors(meta) == []


@pytest.mark.parametrize(
    "values",
    [["windows", "desktop"], ["wsl", "linux"], ["android", "web"]],
)
def test_new_platform_array_form_passes(values):
    """数组形态混排新值与旧值：放行。"""
    meta = dict(_BASE_META, platform=values)
    assert _schema_errors(meta) == []


def test_unknown_platform_still_rejected():
    """枚举封闭性：未知值仍被拒（不因扩容到 8 值而松动）。"""
    meta = dict(_BASE_META, platform="quantumos")
    errs = _schema_errors(meta)
    assert errs, "未知平台值必须被 schema 拒绝"


def test_empty_array_still_rejected():
    """空数组仍被拒（minItems=1 不变）。"""
    meta = dict(_BASE_META, platform=[])
    errs = _schema_errors(meta)
    assert errs, "空 platform 数组必须被 schema 拒绝"


# --------------------------------------------------------------- 语义层：check_platform


@pytest.mark.parametrize("value", list(PLATFORMS))
def test_check_platform_accepts_all_eight(value):
    """check_platform 对 8 值全放行（与 is_known_platform 同口径）。"""
    meta = {"platform": value}
    assert check_platform(meta) == []
    assert is_known_platform(value) is True


def test_check_platform_rejects_unknown():
    """check_platform 对未知值报错且可读。"""
    errs = check_platform({"platform": "quantumos"})
    assert errs, "未知平台值必须报错"
    assert any("quantumos" in e for e in errs)


def test_check_platform_array_form_all_known():
    """check_platform 数组形态：8 值混排全放行。"""
    meta = {"platform": ["desktop", "windows", "wsl", "android"]}
    assert check_platform(meta) == []
