# -*- coding: utf-8 -*-
"""硬编码密钥判定：字面量 vs 变量引用（security.py `scan_action` / validate `check_security`）。

要拦的失效：`sensitive_patterns` 本是为**脱敏**写的（`token = supersecret` 这类任意文本
都要命中），`scan_action` 却把同一批命中当成"源码里写死了密钥"的证据。
`trust` ∈ sandbox/community 时 `check_security` 把它升级为 `security:` 错误、
`executor._security_gate` 抛 `permission_denied` —— 于是"把调用方凭据转发给保险库"
这种**最该被鼓励**的写法（绝不落盘、绝不硬编码）反而动作不可校验、不可执行。
实测受害者：Actus 仓 `actions/vools/web_vault.actus.md`，23 处 `token=params.get("token")`。

出口条件：
- 转发引用 → `check_security` 无 `security:` 错误、执行门不拦，但 warnings 里**照样计数**
  （收窄不是关掉；同时断言原始 detector 确实看见了这些命中）。
- 字面量（带引号 / 含数字的不透明串 / sk- 形状）→ 仍然错误、仍然拦。
- 脱敏面（`scan_text_output` / `redact`）**一字未动**：那是另一条契约（r63 钉了
  `token = supersecret` 必须命中），不能被这次收窄带下去。

隔离：tmp 仓库 + `ACTUS_REPO_ROOT`/`ACTUS_META_DIR`/`HOME` 全指 tmp。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import validate as V  # noqa: E402
from vools.actus.errors import ActionError  # noqa: E402
from vools.actus.executor import _security_gate  # noqa: E402
from vools.actus.model import Action  # noqa: E402
from vools.actus.security import SecurityPolicy, SecurityScanner  # noqa: E402

#: 转发调用方凭据的写法（web_vault 里那 23 处的浓缩版）
FORWARDING = (
    "def main(params, vault):\n"
    "    res = vault.list_secrets(token=params.get(\"token\") or \"\",\n"
    "                             hardware_token=params.get(\"hotp\"),)\n"
    "    out = vault.delete_secret(name=params.get(\"name\"), token=token,)\n"
    "    print(res, out)\n"
)
#: 写死在源码里的密钥
QUOTED_LITERAL = 'token = "hunter2xyz42"\nprint(token)\n'
BLOB_LITERAL = "secret = a1b2c3d4e5f6g7h8\nprint(secret)\n"
SHAPE_LITERAL = 'k = "sk-' + "a" * 24 + '"\nprint(k)\n'


def _action(meta=None, code=FORWARDING):
    blocks = [{"index": 0, "language": "python", "tag": ["main"],
               "directives": {"tag": "main"}, "code": code}]
    return Action(meta=dict(meta or {"id": "s.a", "trust": "sandbox",
                                     "entry": "main"}),
                  path="/tmp/x.actus.md", sha256="", blocks=blocks,
                  body="```python #!run tag=main\n%s```\n" % code)


def _scanner():
    return SecurityScanner(SecurityPolicy())


# ===========================================================================
# 转发引用不再判红，但也没被静默丢掉
# ===========================================================================

def test_forwarded_credentials_are_not_hardcoded():
    """退步了会怎样：把调用方传进来的凭据转发下去被当成硬编码 —— 合规动作不可校验、
    不可执行，作者被逼着把 trust 抬到 audit 来绕开门（安全检查反而被架空）。

    断言：`check_security` 对 sandbox 动作返回空列表（无 `security:` 错误）。
    """
    assert V.check_security(_action()) == []


def test_forwarded_credentials_are_still_counted_in_warnings(tmp_path):
    """退步了会怎样：收窄顺手把命中丢掉 —— 那就没人知道这动作在转发明文凭据。

    断言：原始 detector 确实扫到 ≥3 处；分栏后 `sensitive_findings` 为空、
    warnings 里出现"变量引用"计数。
    """
    scanner = _scanner()
    scanner.audit = type("_Null", (), {"log": lambda *a, **k: None})()
    raw = scanner.detector.scan(FORWARDING)
    assert len(raw) >= 3, raw
    result = scanner.scan_action("s.a", {"trust": "sandbox"}, FORWARDING)
    assert result["sensitive_findings"] == []
    assert any("变量引用" in w for w in result["warnings"]), result["warnings"]


def test_execution_gate_does_not_block_forwarding():
    """打到第二个调用面：`_security_gate` 与 `check_security` 读同一个
    `sensitive_findings`，validate 修好了执行期还拦着 = 没修。

    断言：返回记录 dict（scanned=True），不抛 ActionError。
    """
    info = _security_gate(_action(), "s.a")
    assert info["scanned"] is True
    assert info["sensitive_findings"] == 0


# ===========================================================================
# 字面量仍然判红（收窄不等于放水）
# ===========================================================================

@pytest.mark.parametrize("code", [QUOTED_LITERAL, BLOB_LITERAL, SHAPE_LITERAL],
                         ids=["quoted", "digit-blob", "sk-shape"])
def test_literal_secrets_still_error(code):
    """退步了会怎样：为了放过引用把整条规则关掉 —— 真密钥写进动作源码不再判红。

    断言：三种字面量形状都仍产出 `security:` 错误，且执行门 permission_denied。
    """
    issues = V.check_security(_action(code=code))
    assert issues and all(i.startswith("security:") for i in issues), issues
    with pytest.raises(ActionError) as excinfo:
        _security_gate(_action(code=code), "s.a")
    assert excinfo.value.code == "permission_denied"


@pytest.mark.parametrize("code,expect_literal", [
    (FORWARDING, 0),
    (QUOTED_LITERAL, 1),
    (SHAPE_LITERAL, 1),
], ids=["ref", "quoted", "shape"])
def test_classification_is_per_hit_not_per_file(tmp_path, code, expect_literal):
    """退步了会怎样：整篇文本只要有一处引用就全放过（或反之）—— 混写时漏掉真密钥。

    断言：逐条命中分类，计数与期望逐字相等。
    """
    scanner = _scanner()
    scanner.audit = type("_Null", (), {"log": lambda *a, **k: None})()
    result = scanner.scan_action("s.a", {"trust": "sandbox"}, code)
    assert len(result["sensitive_findings"]) == expect_literal


# ===========================================================================
# 脱敏面不受影响（r63 契约的边界声明）
# ===========================================================================

def test_redaction_path_is_unchanged(tmp_path):
    """退步了会怎样：把 scan_action 的收窄顺手搬到脱敏上 —— 输出里的
    `token = supersecret` 不再被 redact，密钥原样落日志。

    断言：`scan_text_output` 对同一串仍 has_sensitive=True 且 `***REDACTED***` 在场。
    """
    scanner = _scanner()
    scanner.audit = type("_Null", (), {"log": lambda *a, **k: None})()
    r = scanner.scan_text_output("token = supersecret", "s.a")
    assert r["has_sensitive"] is True
    assert "***REDACTED***" in r["redacted"]
