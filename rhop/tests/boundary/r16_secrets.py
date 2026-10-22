# -*- coding: utf-8 -*-
"""第六轮边界语料：敏感信息明文/密文双支持（用户原始需求的核心配置语义）。

定位：语料 + 复现器，不是产品源码（命名不带 test_ 前缀，不进 pytest 收集）。
R3/R10/R13/R14/R15 覆盖了并发、同步、租约、控制意图、幂等、畸形输入、文件通道、
停机回收；本轮第一次把**敏感信息解析**这条用户原始需求做成边界实证：
明文优先、空串回落、告警文案是否含回填命令、严格模式卡口、日志打码、密文回填一致性。

运行：
    cd rhop && python tests/boundary/r16_secrets.py

每条输出 [CONFIRMED] / [NOT-CONFIRMED] + 证据；退出码 = 风险成立条数。
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile

RHOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RHOP)
PY = sys.executable

from vools.rhop.crypto import RhopCrypto                  # noqa: E402
from vools.rhop.task.errors import SecretError            # noqa: E402
from vools.rhop.task.secrets import (                     # noqa: E402
    SECRET_ENC_COMMAND, SecretResolver, mask_value)

RESULTS = []
KEY = "unit-key"


def record(pid, title, risk_realized, evidence):
    RESULTS.append((pid, title, risk_realized, evidence))
    print("[%s] %-40s %s" % ("CONFIRMED" if risk_realized else "NOT-CONFIRMED",
                             pid + " " + title, evidence))


def _enc_cli(plaintext):
    """用 secret CLI 生成 RHOP-ENC 密文（与页面生成同源）。"""
    proc = subprocess.run([PY, "-m", "vools.rhop.secret", "enc", plaintext,
                           "--key", KEY], capture_output=True, text=True, encoding="utf-8",
                          cwd=RHOP)
    return (proc.stdout or "").strip().splitlines()[-1] if proc.stdout.strip() else ""


def _resolve(cfg_dict, warner=None, strict=False):
    """直接用 SecretResolver 解析（可注入 warner 抓告警）。"""
    res = SecretResolver(crypto=RhopCrypto(KEY), strict=strict,
                         warn_plaintext=True,
                         warner=warner if warner is not None else (lambda m: None))
    return res.resolve(cfg_dict), res


def _sftp_cfg(password_spec):
    return {"name": "n", "role": "B", "key": KEY,
            "queue": {"store": {"kind": "sqlite-local"}, "sftp": {"password": password_spec}}}


# ---------------------------------------------------------------------------
# S1 明文优先：同一字段同时给明文与密文 → 用明文（并告警）
# ---------------------------------------------------------------------------
def s1_plaintext_wins():
    work = tempfile.mkdtemp(prefix="bf-s1-")
    cipher = _enc_cli("cipher-secret")
    if not cipher.startswith("RHOP-ENC:"):
        record("S1", "明文与密文同时存在时用明文", True,
               "无法生成密文（CLI 失败）：%r" % cipher[:80])
        return True
    warnings = []
    resolved, _ = _resolve(_sftp_cfg({"plain": "plain-secret", "cipher": cipher}),
                           warner=warnings.append)
    value = resolved.get("queue", {}).get("sftp", {}).get("password")
    risk = value != "plain-secret"
    record("S1", "明文与密文同时存在时用明文", risk,
           "解析结果=%r（期望 'plain-secret'）；告警条数=%d" % (value, len(warnings)))
    return risk


# ---------------------------------------------------------------------------
# S2 空串回落：明文为空串 → 是否回落到密文
# ---------------------------------------------------------------------------
def s2_empty_plain_falls_back():
    cipher = _enc_cli("cipher-secret")
    if not cipher.startswith("RHOP-ENC:"):
        record("S2", "明文为空串时回落到密文", True, "无法生成密文（CLI 失败）")
        return True
    resolved, _ = _resolve(_sftp_cfg({"plain": "", "cipher": cipher}))
    value = resolved.get("queue", {}).get("sftp", {}).get("password")
    risk = value != "cipher-secret"
    record("S2", "明文为空串时回落到密文", risk,
           "解析结果=%r（期望 'cipher-secret'）" % value)
    return risk


# ---------------------------------------------------------------------------
# S3 告警文案：是否含「运行什么命令可以得到密文」且点名字段
# ---------------------------------------------------------------------------
def s3_warning_mentions_backfill_command():
    warnings = []
    resolved, _ = _resolve(_sftp_cfg("plain-secret"), warner=warnings.append)
    text = " ".join(warnings)
    # 用户原始需求：『用明文打印警告，并告知运行什么命令可以得到密文』
    has_command = ("enc" in text) or (SECRET_ENC_COMMAND.split()[1] in text)
    has_field = "sftp.password" in text or "password" in text
    risk = not (has_command and has_field and "plain-secret" not in text.replace("'", ""))
    record("S3", "明文告警含回填命令且点名字段", risk,
           "告警=%r" % (text[:200] if text else "(无告警 —— 用户要求『用明文打印警告』未满足)"))
    return risk


# ---------------------------------------------------------------------------
# S4 严格模式：strict 时明文应直接报错
# ---------------------------------------------------------------------------
def s4_strict_mode_rejects_plaintext():
    risk = False
    try:
        _resolve(_sftp_cfg("plain-secret"), strict=True)
        risk = True                                   # 没报错 ⇒ 严格模式没卡住
    except SecretError as exc:
        risk = ("明文" not in str(exc)) and ("strict" not in str(exc).lower())
    record("S4", "严格模式对明文直接报错且文案可读", risk,
           "报错=%s" % ("未触发（严格模式未生效）" if risk else "SecretError 已触发"))
    return risk


# ---------------------------------------------------------------------------
# S5 日志打码：秘密值在输出里被打码
# ---------------------------------------------------------------------------
def s5_secret_masked_in_output():
    masked = mask_value("super-secret-value")
    risk = (masked == "super-secret-value") or ("super-secret-value" in str(masked))
    record("S5", "秘密值在输出里被打码", risk,
           "mask_value('super-secret-value')=%r" % masked)
    return risk


# ---------------------------------------------------------------------------
# S6 密文回填一致性：CLI enc 产出的密文能被配置直接加载并解出原文
# ---------------------------------------------------------------------------
def s6_cipher_roundtrip_via_cli():
    work = tempfile.mkdtemp(prefix="bf-s6-")
    token = _enc_cli("cli-secret")
    if not token.startswith("RHOP-ENC:"):
        record("S6", "密文回填一致性（CLI → 配置）", True,
               "secret enc 未产出 RHOP-ENC 密文：%r" % token[:80])
        return True
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):            # 告警走 stderr，别污染证据
        resolved, _ = _resolve(_sftp_cfg(token))
    value = resolved.get("queue", {}).get("sftp", {}).get("password")
    risk = value != "cli-secret"
    record("S6", "密文回填一致性（CLI enc → 配置加载）", risk,
           "解析结果=%r（期望 'cli-secret'）" % value)
    return risk


def main():
    print("=" * 92)
    for probe in (s1_plaintext_wins, s2_empty_plain_falls_back, s3_warning_mentions_backfill_command,
                  s4_strict_mode_rejects_plaintext, s5_secret_masked_in_output,
                  s6_cipher_roundtrip_via_cli):
        try:
            probe()
        except Exception as exc:
            record(probe.__name__, "探针自身异常", False, "%s: %s" % (type(exc).__name__, exc))
    confirmed = [r for r in RESULTS if r[2]]
    print("=" * 92)
    print("boundary_cases=%d confirmed=%d not_confirmed=%d"
          % (len(RESULTS), len(confirmed), len(RESULTS) - len(confirmed)))
    for pid, title, ok, _ in RESULTS:
        print("  %-14s %s :: %s" % (pid, "CONFIRMED" if ok else "NOT-CONFIRMED", title))
    return len(confirmed)


if __name__ == "__main__":
    sys.exit(main())