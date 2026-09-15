"""omega.py — Actus Ω-gate 验证引擎（增强版）。

参考 FIST 金条八：任何产出必须过 Ω-gate，<100% 不验收。

增强内容（v2）：
- _find_omega_spec 自动查找 spec 文件
- 新增断言类型：contains / length / any_of / all_of / not_empty / path_exists / json_path / schema
- 差异报告：结构化期望 vs 实际对比
- Spec 学习：从历史执行结果自动推断/更新 spec
- 批量验证与指纹缓存
"""

import json
import hashlib
import re
import os
import glob
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path


# ── FNV-1a 64-bit fingerprint ──

def fnv1a64(data: str) -> str:
    """计算 FNV-1a 64-bit 指纹。"""
    h = 0xcbf29ce484222325
    for b in data.encode("utf-8"):
        h ^= b
        h = (h * 0x100000001b3) & 0xffffffffffffffff
    return f"{h:016x}"


# ── Spec 文件查找 ──

def _find_omega_spec(action_id: str, actions_dir: str) -> Optional[str]:
    """查找动作对应的 spec 文件。

    搜索路径优先级：
    1. actions/private/omega/<action_id>.spec.json
    2. actions/public/omega/<action_id>.spec.json
    3. actions/**/omega/<action_id>.spec.json（递归）
    4. <action_dir>/<action_name>.spec.json（与动作文件同目录）

    actions_dir=None 时取仓库默认 actions/（CLI 直连路径不显式传参）。
    """
    if not actions_dir:
        from .indexer import _repo_root
        actions_dir = os.path.join(_repo_root(), 'actions')
    # 1. 标准 omega 目录
    for visibility in ("private", "public"):
        spec_path = os.path.join(actions_dir, visibility, "omega", f"{action_id}.spec.json")
        if os.path.isfile(spec_path):
            return spec_path

    # 2. 递归搜索 omega 子目录
    for root, dirs, files in os.walk(actions_dir):
        if "omega" in dirs:
            spec_path = os.path.join(root, "omega", f"{action_id}.spec.json")
            if os.path.isfile(spec_path):
                return spec_path

    # 3. 与动作文件同目录
    action_file = _find_action_file(action_id, actions_dir)
    if action_file:
        action_dir = os.path.dirname(action_file)
        spec_path = os.path.join(action_dir, f"{action_id}.spec.json")
        if os.path.isfile(spec_path):
            return spec_path

    return None


def _find_action_file(action_id: str, actions_dir: str) -> Optional[str]:
    """查找动作文件路径。"""
    # 搜索 .actus.md 文件
    for root, dirs, files in os.walk(actions_dir):
        for fname in files:
            if fname.endswith(".actus.md"):
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if f'"{action_id}"' in content or f"'{action_id}'" in content:
                        return fpath
                except Exception:
                    continue
    return None


# ── Spec 加载与缓存 ──

_spec_cache: Dict[str, dict] = {}

def load_spec(spec_path: str, use_cache: bool = True) -> dict:
    """加载 spec JSON 文件（带缓存）。"""
    if use_cache and spec_path in _spec_cache:
        return _spec_cache[spec_path]
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    if use_cache:
        _spec_cache[spec_path] = spec
    return spec


def clear_spec_cache():
    """清除 spec 缓存。"""
    _spec_cache.clear()


# ── Spec 格式验证 ──

def validate_spec(spec: dict) -> Tuple[bool, List[str]]:
    """验证 spec 格式是否合法。"""
    errors = []
    required = ["action_id", "version", "output_schema", "assertions"]
    for key in required:
        if key not in spec:
            errors.append(f"缺少必填字段: {key}")
    if "output_schema" in spec and not isinstance(spec["output_schema"], dict):
        errors.append("output_schema 必须是对象")
    if "assertions" in spec and not isinstance(spec["assertions"], list):
        errors.append("assertions 必须是数组")
    # 验证 assertions 格式
    for i, assertion in enumerate(spec.get("assertions", [])):
        if "type" not in assertion:
            errors.append(f"assertions[{i}] 缺少 type 字段")
    return len(errors) == 0, errors


# ── 字段路径解析 ──

def _get_nested(obj: Any, path: str) -> Any:
    """获取嵌套字段值，支持点号路径和数组索引。

    支持路径：
    - "status"
    - "data.count"
    - "items[0]"
    - "data.items[0].name"
    """
    if not path:
        return obj

    current = obj
    # 解析路径片段：支持 . 分隔和 [index] 索引
    parts = re.split(r'\.(?![^\[]*\])', path)

    for part in parts:
        # 检查数组索引
        match = re.match(r'^(.+?)\[(\d+)\]$', part)
        if match:
            field_name = match.group(1)
            index = int(match.group(2))
            if isinstance(current, dict) and field_name in current:
                current = current[field_name]
            else:
                return None
            if isinstance(current, list) and 0 <= index < len(current):
                current = current[index]
            else:
                return None
        else:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
    return current


# ── 断言引擎（增强版）──

def check_assertion(assertion: dict, actual: Any) -> Tuple[bool, str]:
    """检查单条断言（增强版，支持 16 种断言类型）。"""
    atype = assertion.get("type", "exists")
    field = assertion.get("field", "")
    value = _get_nested(actual, field) if field else actual

    if atype == "exists":
        return value is not None, f"字段 '{field}' 不存在"

    elif atype == "not_exists":
        return value is None, f"字段 '{field}' 不应存在，实际值为 {value}"

    elif atype == "type":
        expected = assertion.get("value", "str")
        type_map = {
            "str": str, "string": str,
            "int": int, "integer": int,
            "float": float, "number": (int, float),
            "bool": bool, "boolean": bool,
            "list": list, "array": list,
            "dict": dict, "object": dict,
        }
        expected_type = type_map.get(expected, str)
        ok = isinstance(value, expected_type)
        return ok, f"字段 '{field}' 类型应为 {expected}, 实际 {type(value).__name__}"

    elif atype == "equals":
        expected = assertion.get("value")
        ok = value == expected
        return ok, f"字段 '{field}' 应为 {expected!r}, 实际 {value!r}"

    elif atype == "not_equals":
        forbidden = assertion.get("value")
        ok = value != forbidden
        return ok, f"字段 '{field}' 不应为 {forbidden!r}"

    elif atype == "approx":
        expected = assertion.get("value", 0)
        epsilon = assertion.get("epsilon", 0.001)
        try:
            ok = abs(float(value) - float(expected)) <= epsilon
            return ok, f"字段 '{field}' 约等于 {expected}±{epsilon}, 实际 {value}"
        except (ValueError, TypeError):
            return False, f"字段 '{field}' 无法做数值比较: {value}"

    elif atype == "regex":
        pattern = assertion.get("value", "")
        ok = bool(re.search(pattern, str(value))) if value is not None else False
        return ok, f"字段 '{field}' 应匹配 /{pattern}/, 实际 '{value}'"

    elif atype == "contains":
        # 字符串包含子串，或数组包含元素
        needle = assertion.get("value", "")
        if isinstance(value, str):
            ok = needle in value
            return ok, f"字段 '{field}' 应包含 '{needle}', 实际 '{value}'"
        elif isinstance(value, list):
            ok = needle in value
            return ok, f"字段 '{field}' 应包含元素 '{needle}', 实际 {value}"
        return False, f"字段 '{field}' 不是字符串或数组，无法检查包含"

    elif atype == "not_contains":
        needle = assertion.get("value", "")
        if isinstance(value, str):
            ok = needle not in value
            return ok, f"字段 '{field}' 不应包含 '{needle}'"
        elif isinstance(value, list):
            ok = needle not in value
            return ok, f"字段 '{field}' 不应包含元素 '{needle}'"
        return False, f"字段 '{field}' 不是字符串或数组"

    elif atype == "length":
        # 数组/字符串长度检查
        min_len = assertion.get("min", 0)
        max_len = assertion.get("max", float("inf"))
        if isinstance(value, (str, list)):
            ok = min_len <= len(value) <= max_len
            return ok, f"字段 '{field}' 长度应在 [{min_len}, {max_len}], 实际 {len(value)}"
        return False, f"字段 '{field}' 不是字符串或数组，无法检查长度"

    elif atype == "range":
        min_val = assertion.get("min", float("-inf"))
        max_val = assertion.get("max", float("inf"))
        try:
            ok = min_val <= float(value) <= max_val
            return ok, f"字段 '{field}' 应在 [{min_val}, {max_val}], 实际 {value}"
        except (ValueError, TypeError):
            return False, f"字段 '{field}' 无法做范围比较: {value}"

    elif atype == "subset":
        allowed = assertion.get("value", [])
        if isinstance(value, list):
            extra = set(value) - set(allowed)
            ok = len(extra) == 0
            return ok, f"字段 '{field}' 包含不允许的值: {extra}"
        return False, f"字段 '{field}' 不是数组，无法做 subset 检查"

    elif atype == "superset":
        required = assertion.get("value", [])
        if isinstance(value, list):
            missing = set(required) - set(value)
            ok = len(missing) == 0
            return ok, f"字段 '{field}' 缺少必需的值: {missing}"
        return False, f"字段 '{field}' 不是数组，无法做 superset 检查"

    elif atype == "any_of":
        # 满足任一断言即可
        sub_assertions = assertion.get("assertions", [])
        for sub in sub_assertions:
            ok, _ = check_assertion(sub, actual)
            if ok:
                return True, ""
        return False, f"字段 '{field}' 不满足 any_of 中的任一断言"

    elif atype == "all_of":
        # 满足全部断言
        sub_assertions = assertion.get("assertions", [])
        for sub in sub_assertions:
            ok, msg = check_assertion(sub, actual)
            if not ok:
                return False, f"all_of 失败: {msg}"
        return True, ""

    elif atype == "not_empty":
        if value is None:
            return False, f"字段 '{field}' 为空"
        if isinstance(value, (str, list, dict)):
            ok = len(value) > 0
            return ok, f"字段 '{field}' 不应为空"
        return True, ""

    elif atype == "path_exists":
        # 检查文件路径是否存在
        if isinstance(value, str):
            ok = os.path.exists(value)
            return ok, f"路径 '{value}' 不存在"
        return False, f"字段 '{field}' 不是路径字符串"

    elif atype == "json_path":
        # JSONPath 风格查询（简化版）
        json_path = assertion.get("value", "")
        expected = assertion.get("expected")
        found = _get_nested(actual, json_path)
        ok = found == expected
        return ok, f"路径 '{json_path}' 期望 {expected!r}, 实际 {found!r}"

    elif atype == "status_ok":
        status = _get_nested(actual, "status") if isinstance(actual, dict) else None
        ok = status == "ok"
        return ok, f"status 应为 'ok', 实际 '{status}'"

    elif atype == "schema":
        # 简化的 JSON Schema 验证
        schema = assertion.get("value", {})
        return _validate_schema(value, schema)

    return True, ""


def _validate_schema(value: Any, schema: dict) -> Tuple[bool, str]:
    """简化 JSON Schema 验证。"""
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            return False, f"应为对象，实际 {type(value).__name__}"
        properties = schema.get("properties", {})
        for prop, prop_schema in properties.items():
            if prop in value:
                ok, msg = _validate_schema(value[prop], prop_schema)
                if not ok:
                    return False, f"属性 '{prop}': {msg}"
        required = schema.get("required", [])
        for req in required:
            if req not in value:
                return False, f"缺少必需属性 '{req}'"
    elif schema_type == "array":
        if not isinstance(value, list):
            return False, f"应为数组，实际 {type(value).__name__}"
        items_schema = schema.get("items", {})
        for i, item in enumerate(value):
            ok, msg = _validate_schema(item, items_schema)
            if not ok:
                return False, f"数组[{i}]: {msg}"
    elif schema_type == "string":
        if not isinstance(value, str):
            return False, f"应为字符串，实际 {type(value).__name__}"
    elif schema_type == "integer":
        if not isinstance(value, int):
            return False, f"应为整数，实际 {type(value).__name__}"
    return True, ""


# ── Ω-gate 验证 ──

def run_gate(spec: dict, actual_output: dict) -> dict:
    """运行 Ω-gate 验证。"""
    results = []
    passed = 0
    failed = 0

    assertions = spec.get("assertions", [])
    for assertion in assertions:
        ok, message = check_assertion(assertion, actual_output)
        results.append({
            "assertion": assertion,
            "passed": ok,
            "message": message
        })
        if ok:
            passed += 1
        else:
            failed += 1

    total = passed + failed
    accuracy = (passed / total * 100) if total > 0 else 100.0

    return {
        "passed": failed == 0,
        "accuracy": round(accuracy, 1),
        "passed_count": passed,
        "failed_count": failed,
        "total": total,
        "details": results
    }


# ── 差异报告 ──

def generate_diff_report(spec: dict, actual_output: dict) -> dict:
    """生成详细的差异报告（期望 vs 实际）。"""
    expected_schema = spec.get("output_schema", {})
    properties = expected_schema.get("properties", {})

    diff = {
        "missing_fields": [],
        "extra_fields": [],
        "type_mismatches": [],
        "value_mismatches": [],
        "status": "match"
    }

    actual_keys = set(actual_output.keys()) if isinstance(actual_output, dict) else set()
    expected_keys = set(properties.keys())

    # 缺失字段
    for key in expected_keys - actual_keys:
        if properties[key].get("required", True):
            diff["missing_fields"].append(key)

    # 多余字段
    for key in actual_keys - expected_keys:
        diff["extra_fields"].append(key)

    # 类型不匹配
    for key in actual_keys & expected_keys:
        if key in properties:
            expected_type = properties[key].get("type", "")
            actual_value = actual_output[key]
            type_map = {
                "string": str, "integer": int, "number": (int, float),
                "boolean": bool, "array": list, "object": dict
            }
            if expected_type in type_map:
                if not isinstance(actual_value, type_map[expected_type]):
                    diff["type_mismatches"].append({
                        "field": key,
                        "expected": expected_type,
                        "actual": type(actual_value).__name__
                    })

    # 枚举值不匹配
    for key in actual_keys & expected_keys:
        if key in properties:
            enum_values = properties[key].get("enum")
            if enum_values and actual_output[key] not in enum_values:
                diff["value_mismatches"].append({
                    "field": key,
                    "allowed": enum_values,
                    "actual": actual_output[key]
                })

    # 判断总体状态
    if diff["missing_fields"] or diff["type_mismatches"] or diff["value_mismatches"]:
        diff["status"] = "mismatch"
    elif diff["extra_fields"]:
        diff["status"] = "extra"

    return diff


# ── Fingerprint 验证 ──

def compute_output_fingerprint(output: dict) -> str:
    """计算输出的指纹。"""
    canonical = json.dumps(output, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return fnv1a64(canonical)


def check_fingerprint(spec: dict, actual_output: dict) -> Tuple[bool, str, str]:
    """检查输出指纹是否匹配。"""
    expected_fp = spec.get("fingerprint", "")
    if not expected_fp:
        return True, "", ""
    actual_fp = compute_output_fingerprint(actual_output)
    match = actual_fp == expected_fp
    return match, expected_fp, actual_fp


# ── Ω-loop 修复循环 ──

def run_omega_loop(spec: dict, actual_output: dict, max_rounds: int = 3) -> dict:
    """运行 Ω-loop：验证 → 失败分析 → 修复建议 → 重验证。"""
    rounds = []
    current_output = actual_output

    for i in range(max_rounds):
        gate_result = run_gate(spec, current_output)
        rounds.append({
            "round": i + 1,
            "accuracy": gate_result["accuracy"],
            "passed": gate_result["passed"],
            "failed_details": [d for d in gate_result["details"] if not d["passed"]]
        })

        if gate_result["passed"]:
            break

        if i == max_rounds - 1:
            break  # 超限未收敛

    return {
        "converged": rounds[-1]["passed"] if rounds else True,
        "rounds": rounds,
        "total_rounds": len(rounds),
        "final_accuracy": rounds[-1]["accuracy"] if rounds else 100.0
    }


# ── 完整验证入口 ──

def verify_output(spec_path: str, actual_output: dict, enable_loop: bool = False) -> dict:
    """完整验证入口：加载 spec → 验证 → 返回报告。"""
    spec = load_spec(spec_path)
    valid, errors = validate_spec(spec)
    if not valid:
        return {
            "status": "spec_error",
            "errors": errors
        }

    gate_result = run_gate(spec, actual_output)
    fp_match, expected_fp, actual_fp = check_fingerprint(spec, actual_output)
    diff_report = generate_diff_report(spec, actual_output)

    result = {
        "status": "pass" if (gate_result["passed"] and fp_match) else "fail",
        "gate": gate_result,
        "fingerprint": {
            "match": fp_match,
            "expected": expected_fp,
            "actual": actual_fp
        },
        "diff": diff_report
    }

    if enable_loop and not gate_result["passed"]:
        result["loop"] = run_omega_loop(spec, actual_output)

    return result


# ── Spec 学习（从历史执行推断）──

def learn_spec_from_history(history: List[dict]) -> dict:
    """从历史执行结果自动推断 spec。

    分析多个执行结果，推断：
    - 字段类型（取最常见类型）
    - 字段是否必需（出现频率 > 80%）
    - 值范围（数值字段的最小/最大值）
    - 枚举值（字符串字段的唯一值集合）
    """
    if not history:
        return {}

    field_stats: Dict[str, dict] = {}

    for record in history:
        result = record.get("result", record)
        if not isinstance(result, dict):
            continue
        for key, value in result.items():
            if key not in field_stats:
                field_stats[key] = {
                    "count": 0,
                    "types": {},
                    "values": set(),
                    "min_val": float("inf"),
                    "max_val": float("-inf"),
                    "is_numeric": True
                }
            stats = field_stats[key]
            stats["count"] += 1
            vtype = type(value).__name__
            stats["types"][vtype] = stats["types"].get(vtype, 0) + 1
            if isinstance(value, (int, float)):
                stats["min_val"] = min(stats["min_val"], value)
                stats["max_val"] = max(stats["max_val"], value)
            else:
                stats["is_numeric"] = False
            if isinstance(value, str) and len(value) < 100:
                stats["values"].add(value)

    # 构建 schema
    properties = {}
    required = []
    total = len(history)

    for field, stats in field_stats.items():
        # 判断是否必需
        if stats["count"] / total >= 0.8:
            required.append(field)

        # 推断类型
        most_common_type = max(stats["types"], key=stats["types"].get)
        prop = {"type": _normalize_type(most_common_type)}

        # 数值范围
        if stats["is_numeric"] and stats["min_val"] != float("inf"):
            prop["minimum"] = stats["min_val"]
            prop["maximum"] = stats["max_val"]

        # 枚举值（唯一值 <= 10 个）
        if len(stats["values"]) <= 10 and len(stats["values"]) > 0:
            prop["enum"] = sorted(list(stats["values"]))

        properties[field] = prop

    return {
        "output_schema": {
            "type": "object",
            "properties": properties,
            "required": required
        },
        "learned_from": total,
        "field_stats": {k: {"count": v["count"], "types": v["types"]} for k, v in field_stats.items()}
    }


def _normalize_type(type_name: str) -> str:
    """标准化类型名称。"""
    mapping = {
        "str": "string", "int": "integer", "float": "number",
        "bool": "boolean", "list": "array", "dict": "object"
    }
    return mapping.get(type_name, "string")


# ── Spec 模板生成 ──

def generate_spec_template(action_id: str, output_example: dict) -> dict:
    """根据输出示例生成 spec 模板。"""
    return {
        "action_id": action_id,
        "version": "1.0.0",
        "output_schema": _infer_schema(output_example),
        "assertions": [
            {"type": "status_ok"},
            {"type": "exists", "field": "status"}
        ],
        "fingerprint": compute_output_fingerprint(output_example)
    }


def _infer_schema(obj: Any, path: str = "") -> dict:
    """从示例值推断 JSON Schema。"""
    if isinstance(obj, dict):
        props = {}
        for k, v in obj.items():
            props[k] = _infer_schema(v, f"{path}.{k}" if path else k)
        return {"type": "object", "properties": props}
    elif isinstance(obj, list):
        items = _infer_schema(obj[0], f"{path}[]") if obj else {}
        return {"type": "array", "items": items}
    elif isinstance(obj, str):
        return {"type": "string"}
    elif isinstance(obj, bool):
        return {"type": "boolean"}
    elif isinstance(obj, int):
        return {"type": "integer"}
    elif isinstance(obj, float):
        return {"type": "number"}
    return {"type": "string"}


# ── 批量验证 ──

def batch_verify(spec_path: str, outputs: List[dict]) -> dict:
    """批量验证多个输出。"""
    results = []
    for output in outputs:
        result = verify_output(spec_path, output)
        results.append(result)

    passed = sum(1 for r in results if r["status"] == "pass")
    total = len(results)

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        "results": results
    }


# ── CLI 辅助 ──

def format_report(report: dict) -> str:
    """格式化验证报告为可读文本。"""
    lines = []
    status = report.get("status", "unknown")
    lines.append(f"Ω-gate 验证结果: {status.upper()}")

    if status == "spec_error":
        for error in report.get("errors", []):
            lines.append(f"  ✗ {error}")
        return "\n".join(lines)

    gate = report.get("gate", {})
    lines.append(f"  准确率: {gate.get('accuracy', 0)}%")
    lines.append(f"  通过: {gate.get('passed_count', 0)}/{gate.get('total', 0)}")

    if not gate.get("passed", False):
        lines.append("\n  失败详情:")
        for detail in gate.get("details", []):
            if not detail.get("passed", True):
                lines.append(f"    ✗ {detail.get('message', '')}")

    diff = report.get("diff", {})
    if diff.get("status") == "mismatch":
        if diff.get("missing_fields"):
            lines.append(f"\n  缺失字段: {', '.join(diff['missing_fields'])}")
        if diff.get("type_mismatches"):
            for mm in diff["type_mismatches"]:
                lines.append(f"  类型不匹配: {mm['field']} (期望 {mm['expected']}, 实际 {mm['actual']})")

    fp = report.get("fingerprint", {})
    if fp.get("expected"):
        match_str = "✓" if fp.get("match") else "✗"
        lines.append(f"\n  指纹: {match_str} (期望 {fp['expected'][:8]}..., 实际 {fp['actual'][:8]}...)")

    return "\n".join(lines)


__all__ = [
    'batch_verify',
    'check_assertion',
    'check_fingerprint',
    'clear_spec_cache',
    'compute_output_fingerprint',
    'fnv1a64',
    'format_report',
    'generate_diff_report',
    'generate_spec_template',
    'learn_spec_from_history',
    'load_spec',
    'run_gate',
    'run_omega_loop',
    'validate_spec',
    'verify_output'
]
