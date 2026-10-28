# -*- coding: utf-8 -*-
"""种子动作签名验证回归。

ACTUS_REFACTOR_PLAN 阶段 5 的出口条件是「全量 verify 0 error」。
种子动作随包发布，必须自带签名，否则任何用户跑 `actus verify` 都会失败。

本用例把这条基线钉住：所有种子动作必须能通过签名验证。

测试卫生（第 15 轮，真实事故）：
旧版 `test_seed_signatures_are_tamper_evident` 直接改写**仓库真实**的
`calculator.actus.schema.md`，靠 try/finally 还原 —— 2026-10-28 20:35 有一次运行
被中断（写入后、finally 前没走完），脏文件留在仓库，下游看到莫名其妙的两条签名红。
现在**绝不写真实文件**：把「动作 + 签名」一起复制到 `tmp_path` 再篡改副本，
并用运行前后 sha256 行程开关证明真实文件零写入；即使进程在篡改后立刻被杀，
仓库也不会被污染。
"""
import glob
import hashlib
import os
import shutil

from vools.actus.trust_model import SignatureVerifier

#: 种子动作目录（随包发布的 4 个动作）
SEED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "vools", "actus", "actions", "basics")


def _seed_files():
    return sorted(glob.glob(os.path.join(SEED_DIR, "*.actus.schema.md")))


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _copy_action_and_signature(src, tmp_path):
    """把真实动作 + .sig **复制**到 tmp_path，返回 (副本路径, 副本签名路径)。

    只读复制：真实文件永远是 source，不会被打开写模式。
    """
    sig = src + ".sig"
    if not os.path.isfile(sig):
        raise AssertionError("种子动作缺签名（签名基线不成立）: %s" % sig)
    tmp_action = tmp_path / os.path.basename(src)
    tmp_sig = tmp_path / (os.path.basename(src) + ".sig")
    shutil.copy2(src, str(tmp_action))
    shutil.copy2(sig, str(tmp_sig))
    return tmp_action, tmp_sig


def test_seed_signatures_are_tamper_evident(tmp_path):
    """签名必须能检出内容被篡改（否则签名形同虚设）。

    退步了会怎样（测试卫生面）：改回「直接写仓库真实文件、finally 还原」的写法 ——
    一次超时/Ctrl-C/杀进程就会把 `# tampered-for-test` 留在仓库里（20:35 真实发生），
    下游全量出现两条莫名签名红。本用例只碰 tmp 副本，真实文件前后 sha256 必须一致。
    """
    files = _seed_files()
    assert files, "种子动作目录为空: %s" % SEED_DIR
    verifier = SignatureVerifier()
    src = files[0]
    real_before = _sha256_file(src)

    # 1) 复制到 tmp，先确认副本能通过
    tmp_action, tmp_sig = _copy_action_and_signature(src, tmp_path)
    assert verifier.verify_file(str(tmp_action), sig_path=str(tmp_sig)).get("status") == "ok"

    # 2) 篡改**副本**（即使此处被中断，真实仓库也没有任何脏写）
    with open(str(tmp_action), "a", encoding="utf-8") as handle:
        handle.write("\n# tampered-for-test\n")
    assert verifier.verify_file(str(tmp_action), sig_path=str(tmp_sig)).get("status") != "ok", \
        "签名未能检出内容篡改"

    # 3) 真实文件零写入行程开关（不需要 finally 还原，因为从来没写过它）
    assert _sha256_file(src) == real_before, \
        "篡改测试污染了仓库真实种子动作: %s" % src


def test_tamper_flow_never_touches_real_repo_even_if_interrupted(tmp_path):
    """中断模拟：篡改副本后**立即抛异常**（模拟进程被杀），真实仓库仍必须干净。

    这是对旧写法的直接反驳：旧写法在"篡改后、finally 前"被杀 → 仓库留下脏文件；
    新写法全程只操作 tmp 副本，没有"需要还原"的真实文件，因此中断也没有残留。
    断言：异常如期抛出 → 真实文件 sha256 不变 → 真实签名仍验证通过。
    """
    files = _seed_files()
    assert files, "种子动作目录为空: %s" % SEED_DIR
    verifier = SignatureVerifier()
    src = files[0]
    real_before = _sha256_file(src)

    def _tamper_then_be_killed():
        tmp_action, _tmp_sig = _copy_action_and_signature(src, tmp_path)
        with open(str(tmp_action), "a", encoding="utf-8") as handle:
            handle.write("\n# tampered-for-test\n")
        raise RuntimeError("模拟进程在篡改后、还原前被中断")

    interrupted = False
    try:
        _tamper_then_be_killed()
    except RuntimeError:
        interrupted = True
    assert interrupted, "中断模拟没有抛出异常"

    assert _sha256_file(src) == real_before, \
        "中断后真实种子动作被污染（旧写法才会这样）: %s" % src
    assert verifier.verify_file(src).get("status") == "ok", \
        "真实种子动作签名在中断模拟后不再通过（说明真实文件被写过）"
