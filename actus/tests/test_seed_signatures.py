# -*- coding: utf-8 -*-
"""种子动作签名验证回归。

ACTUS_REFACTOR_PLAN 阶段 5 的出口条件是「全量 verify 0 error」。
种子动作随包发布，必须自带签名，否则任何用户跑 `actus verify` 都会失败。

本用例把这条基线钉住：所有种子动作必须能通过签名验证。
"""
import glob
import os

from vools.actus.trust_model import SignatureVerifier

#: 种子动作目录（随包发布的 4 个动作）
SEED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "vools", "actus", "actions", "basics")


def _seed_files():
    return sorted(glob.glob(os.path.join(SEED_DIR, "*.actus.schema.md")))


def test_seed_actions_exist():
    """种子动作目录里应有动作文件（否则下面的签名用例无从谈起）。"""
    files = _seed_files()
    assert files, "种子动作目录为空: %s" % SEED_DIR


def test_seed_actions_verify_cleanly():
    """全部种子动作必须通过签名验证（阶段 5 出口条件）。"""
    files = _seed_files()
    assert files, "种子动作目录为空: %s" % SEED_DIR
    verifier = SignatureVerifier()
    failures = []
    for path in files:
        result = verifier.verify_file(path)
        if result.get("status") != "ok":
            failures.append((os.path.basename(path), result.get("message")))
    assert not failures, "种子动作签名验证失败: %s" % failures


def test_seed_signatures_are_tamper_evident():
    """签名必须能检出内容被篡改（否则签名形同虚设）。"""
    files = _seed_files()
    assert files, "种子动作目录为空: %s" % SEED_DIR
    verifier = SignatureVerifier()
    path = files[0]
    # 先确认原文件能通过
    assert verifier.verify_file(path).get("status") == "ok"
    # 改一个字节后必须失败（改完再还原，避免污染仓库）
    with open(path, "r", encoding="utf-8") as fh:
        original = fh.read()
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(original + "\n# tampered-for-test\n")
        assert verifier.verify_file(path).get("status") != "ok", \
            "签名未能检出内容篡改"
    finally:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(original)
    assert verifier.verify_file(path).get("status") == "ok", "还原后签名验证应恢复通过"
