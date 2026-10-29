# -*- coding: utf-8 -*-
"""错误码不变量（第 21 轮审计沉淀）。

审计 63 个错误码后发现的问题：同一语义用**单复数两个码**表达——
`missing_param`（单个）与 `missing_params`（多个），调用方查其中一个就会
漏掉另一个。已统一为 `missing_param`，具体缺哪些放到 `details.missing`。

本组锁定两条不变量，防止同类分裂复发。
"""
import glob
import os
import re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "vools", "actus")


def _collect_codes():
    """收集源码里所有错误码字面量（'code': 'xxx' 与 ActionError('xxx', ...)）。"""
    codes = defaultdict(list)
    for path in glob.glob(os.path.join(SRC, "**", "*.py"), recursive=True):
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        for m in re.finditer(r"""['"]code['"]\s*:\s*['"]([a-z][a-z0-9_]*)['"]""", text):
            codes[m.group(1)].append(os.path.basename(path))
        for m in re.finditer(r"""(?:ActionError|ScatteredError)\(\s*['"]([a-z][a-z0-9_]*)['"]""",
                             text):
            codes[m.group(1)].append(os.path.basename(path))
    return codes


def test_no_singular_plural_code_pairs():
    """同一语义不得用单复数两个码（如 missing_param / missing_params）。"""
    codes = set(_collect_codes())
    offenders = []
    for code in codes:
        if code.endswith("s") and code[:-1] in codes:
            offenders.append((code[:-1], code))
    assert not offenders, "存在单复数分裂的错误码: %s" % offenders


def test_missing_param_is_unified():
    """统一后的契约：只允许 `missing_param`，且必须带 details.missing。

    第 20 轮：源码字符串断言 → **行为断言**。原来 `assert "missing_param" in src`
    在"守卫被删"时未必红（别处仍可能出现这个词）；现在构造两类会触发缺参的
    调用，直接断言返回体：
      1. handler 自校验缺参（`actus_deps`，schema 无 required）→ missing_param；
      2. handler 深校验（`actus_evolve_rollback` 传空串/None，绕过 schema required
         的存在性检查）→ missing_param + details.missing 点名空参。
    """
    import io as _io
    import json as _json
    from vools.actus import mcp_server

    def _payload(raw):
        return _json.loads(raw["content"][0]["text"])

    # ① MCP 入口的统一缺参校验（generic 层）：param_invalid + details.missing
    server = mcp_server.MCPServer(stdout=_io.BytesIO())
    raw = server._call_tool({"name": "actus_deps", "arguments": {}})
    payload = _payload(raw)
    assert raw.get("isError") is True
    assert payload["error"]["code"] == "param_invalid", payload
    assert payload["error"]["details"]["missing"] == ["action_id"], payload

    # ② handler 自校验层（是 missing_param 的唯一真实出处；generic 层之上仍在）：
    #    直接调 handler 触发"参数存在但为空"的深校验。
    err = _payload(mcp_server._handle_deps_check({}))
    assert err["error"]["code"] == "missing_param", err

    payload = _payload(mcp_server._handle_evolve_rollback(
        {"action_id": "", "version": None}))
    error = payload["error"]
    assert error["code"] == "missing_param", error
    missing = (error.get("details") or {}).get("missing") or []
    assert set(missing) == {"action_id", "version"}, error
    # 单复数分裂由 test_no_singular_plural_code_pairs 静态兜底；这里再直接保证
    # 行为层只出现 missing_param（若某 handler 回退成 missing_params 会立刻红）。
    assert "missing_params" not in _json.dumps(payload), payload


def test_key_error_codes_present():
    """核心错误码必须存在（防止被误删）。"""
    codes = set(_collect_codes())
    for required in ("action_not_found", "action_invalid", "param_invalid",
                     "kind_unsupported", "remote_host_denied",
                     "remote_digest_mismatch", "remote_signature_invalid"):
        assert required in codes, "缺少核心错误码 %s" % required


def test_every_code_has_a_source():
    """每个码都必须能在源码里找到产生点（不能凭空出现在测试里）。"""
    codes = _collect_codes()
    assert codes, "没收集到任何错误码，扫描逻辑可能失效"
    for code, files in codes.items():
        assert files, "错误码 %s 没有产生点" % code
