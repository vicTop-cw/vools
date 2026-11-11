# -*- coding: utf-8 -*-
"""actus/tests/test_error_codes_coverage_r102.py — 错误码覆盖收口（统帅轮-09时）。

测什么 / 为什么
---------------
REFACTOR_COMPLETION §六.1 的「42 个错误码无测试引用（67%）」是 0.9.0 发布前
的审计快照；此后各轮补测大幅收敛。本轮用直调审计
（grep `ActionError('<code>'` 全仓 → 对照 tests/ 引用）实测：
  * 33 个直调码里 **30 个已有测试引用**；
  * 唯一零引用的是 `resource_not_found`（mcp_server 资源读取的两条触发路径）；
  * docs/08 §5 名单（ERROR_CODES）里的间接发出码
    （confirmation_timeout / language_unavailable / entry_no_output /
    block_failed）引用数 1-4 不等，全部非零。
本文件收口最后一块：`resource_not_found` 的两条真实触发路径 + ERROR_CODES
名单与 ActionError 的闭环契约 + 码形态 lint。

怎么测（不依赖外部资源）
------------------------
* MCPServer._read_resource 是纯内存方法（资源读取走 records/indexer，用
  tmp meta_dir + monkeypatch 隔离）；
* runs/<eid> 不存在路径：load_run_record 对不存在的 id 返回 None → 触发
  resource_not_found（读真实 records 模块，不 mock 内部——mock 边界放
  meta_dir 落点，契约路径保持真实）；
* 名单闭环：for code in ERROR_CODES → ActionError 可构造、to_payload 结构
  符合 docs/03 §7.2。

py3.8+ 口径（pyproject requires-python>=3.8，24ea2d53 升级）：只用标准库，% 格式化（保持文件间一致风格）。
"""

import json
import os
import re
import sys

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.errors import ERROR_CODES, ActionError  # noqa: E402


# ---------------------------------------------------------------------------
# 1. resource_not_found：唯一此前零测试引用的直调码（本轮收口）
# ---------------------------------------------------------------------------

def _server(tmp_path, monkeypatch):
    """构造 MCPServer 并把 meta 落点指到 tmp（隔离真实仓库 _meta）。"""
    from vools.actus.mcp_server import MCPServer
    monkeypatch.setenv("ACTUS_META_DIR", str(tmp_path))
    return MCPServer()


def test_resource_not_found_unknown_uri(tmp_path, monkeypatch):
    """未知 uri → ActionError(code='resource_not_found')。"""
    server = _server(tmp_path, monkeypatch)
    with pytest.raises(ActionError) as exc_info:
        server._read_resource({"uri": "actus://definitely-not-a-resource"})
    assert exc_info.value.code == "resource_not_found"
    assert "actus://definitely-not-a-resource" in exc_info.value.message


def test_resource_not_found_missing_run_record(tmp_path, monkeypatch):
    """actus://runs/<不存在的id> → ActionError(code='resource_not_found')。"""
    server = _server(tmp_path, monkeypatch)
    with pytest.raises(ActionError) as exc_info:
        server._read_resource({"uri": "actus://runs/no-such-exec-id-xyz"})
    assert exc_info.value.code == "resource_not_found"
    assert "no-such-exec-id-xyz" in exc_info.value.message


def test_resource_runs_existing_record_ok(tmp_path, monkeypatch):
    """对照路径：runs/<id> 记录存在 → 正常返回 JSON 内容（不抛错）。"""
    from vools.actus import records as rec
    server = _server(tmp_path, monkeypatch)
    rec.write_run_record(str(tmp_path), {
        "exec_id": "e2e-ok-1", "status": "ok", "action_id": "a.b",
    })
    result = server._read_resource({"uri": "actus://runs/e2e-ok-1"})
    text = result["contents"][0]["text"]
    payload = json.loads(text)
    assert payload["exec_id"] == "e2e-ok-1"


# ---------------------------------------------------------------------------
# 2. ERROR_CODES 名单闭环（docs/08 §5 名单 × ActionError 契约）
# ---------------------------------------------------------------------------

def test_error_codes_registry_all_constructible():
    """名单里每个码都能被 ActionError 构造且 code 原样保留。"""
    assert len(ERROR_CODES) >= 15, "docs/08 §5 名单不应缩水（当前 %d）" % len(ERROR_CODES)
    for code in ERROR_CODES:
        err = ActionError(code, "测试: %s" % code)
        assert err.code == code
        assert err.message == "测试: %s" % code
        assert err.details == {}


def test_error_codes_registry_payload_contract():
    """to_payload 符合 docs/03 §7.2：{code, message, details} 三键。"""
    err = ActionError("param_invalid", "参数坏", {"field": "deps"})
    payload = err.to_payload()
    assert set(payload.keys()) == {"code", "message", "details"}
    assert payload["code"] == "param_invalid"
    assert payload["details"] == {"field": "deps"}


def test_error_codes_registry_shape_lint():
    """码形态 lint：全仓名单码必须 ^[a-z][a-z0-9_]+$（防单复数分裂回潮）。"""
    for code in ERROR_CODES:
        assert re.match(r"^[a-z][a-z0-9_]+$", code), \
            "错误码形态非法: %r" % code


def test_executor_high_freq_codes_registered():
    """高频直调码必须已登记名单（防『码在代码里、名单没同步』回潮——
    errors.py 名单注释里 entry_no_output 的教训）。"""
    for code in ("action_not_found", "param_invalid", "trust_rejected",
                 "permission_denied", "timeout", "entry_no_output",
                 "block_failed", "action_exists"):
        assert code in ERROR_CODES, "高频码 %s 未登记 ERROR_CODES" % code


# ---------------------------------------------------------------------------
# 3. 直调码集合与名单的一致性（审计脚本口径的固化）
# ---------------------------------------------------------------------------

def test_all_direct_call_codes_known():
    """全仓 ActionError('...') 直调码 ∈ 名单 ∪ 已知扩展集。

    名单（ERROR_CODES）+ 远程动作四件套（remote_*，resolver 专用）+
    workflow/quality/author 专属码 + mcp 资源码。新码出现时先登记名单
    或扩展集，不许静默漂移。
    """
    src_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "vools", "actus")
    code_pat = re.compile(r"""ActionError\(\s*['"]([a-z][a-z0-9_]+)['"]""")
    direct_codes = set()
    for root, _dirs, files in os.walk(src_dir):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(root, fn), encoding="utf-8",
                      errors="replace") as f:
                for m in code_pat.finditer(f.read()):
                    direct_codes.add(m.group(1))

    known = set(ERROR_CODES) | {
        # remote_* 四件套 + 远程下载族（resolver 远程动作信任链专用，docs §六.3）
        "remote_host_denied", "remote_download_failed", "remote_too_large",
        "remote_digest_mismatch", "remote_signature_missing",
        "remote_signature_invalid",
        # 深链解析族（resolver）
        "action_ambiguous", "action_ref_cycle", "action_ref_depth_exceeded",
        "action_ref_failed",
        # workflow 族
        "dag_cycle", "dag_missing_dep", "workflow_invalid",
        "workflow_not_found", "workflow_source_missing",
        # 其他模块专属
        "invalid_ai_edit_result", "prompt_not_found",
        "vault_read_failed", "vault_secret_conflict", "ambiguous",
        "resource_not_found",
    }
    unknown = sorted(direct_codes - known)
    assert not unknown, "发现未登记的错误码（先登记再发码）: %s" % unknown
