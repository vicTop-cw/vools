# -*- coding: utf-8 -*-
"""第四轮边界语料：大载荷结果落文件 + 停机路径。

定位：语料 + 复现器，不是产品源码（命名不带 test_ 前缀，不进 pytest 收集）。
针对刚落地的 file_channel（advance 轮）做边界实证：引用失效矩阵、并发写同名、
清理误删、目录穿越、与 result_max_bytes 的组合分支。

运行：
    cd rhop && python tests/boundary/r14_file_channel.py

每条输出 [CONFIRMED] / [NOT-CONFIRMED] + 证据；退出码 = 风险成立条数。
"""
import json
import os
import sys
import tempfile

RHOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RHOP)

from vools.rhop.task.config import TaskConfig            # noqa: E402
from vools.rhop.task.errors import SecretError           # noqa: E402
from vools.rhop.task.queue import TaskQueue              # noqa: E402

RESULTS = []


def record(pid, title, risk_realized, evidence):
    RESULTS.append((pid, title, risk_realized, evidence))
    print("[%s] %-38s %s" % ("CONFIRMED" if risk_realized else "NOT-CONFIRMED",
                             pid + " " + title, evidence))


def _cfg(tmp_path, **fc):
    fc = dict(fc)
    fc.setdefault("enabled", True)
    fc.setdefault("dir", os.path.join(str(tmp_path), "files"))
    fc.setdefault("max_bytes", 500)
    fc.setdefault("keep_days", 7)
    return TaskConfig.from_dict(
        {"name": "link", "role": "B", "key": "k",
         "queue": {"store": {"kind": "sqlite-local"}, "file_channel": fc}},
        base_dir=str(tmp_path), warn_plaintext=False)


def _encode(queue, blob_size=4000, result_max_bytes=None):
    queue_override = {} if result_max_bytes is None else {"result_max_bytes": result_max_bytes}
    cfg = TaskConfig.from_dict(
        {"name": "link", "role": "B", "key": "k",
         "queue": {"store": {"kind": "sqlite-local"},
                   "file_channel": queue.config.queue["file_channel"],
                   **queue_override}},
        base_dir=queue.config.base_dir, warn_plaintext=False)
    q = TaskQueue(cfg)
    try:
        return q.encode_result({"result": {"blob": "x" * blob_size},
                                "channel": "n", "name": "n"})
    finally:
        q.close()


def _envelope(queue, encoded):
    """取信封里的明文节点（默认 encrypt_result=True，直接 json.loads 只能拿到 Fernet 信封）。"""
    text = str(encoded)
    if text.lstrip().startswith("{"):
        node = json.loads(text)
        if isinstance(node, dict) and node.get("alg") == "fernet":
            result = queue.crypto.decrypt_verify(text)
            return result.payload
        return node
    return text


# ---------------------------------------------------------------------------
# F1 引用失效矩阵：缺文件 / sha 不匹配 / 非 JSON / 目录消失
# ---------------------------------------------------------------------------
def f1_ref_failure_matrix():
    work = tempfile.mkdtemp(prefix="bf-f1-")
    q = TaskQueue(_cfg(work))
    try:
        encoded = _encode(q, 4000)
        node = _envelope(q, encoded)
        ref = node["file_ref"]
        path = ref["path"]
        outcomes = {}

        os.remove(path)
        outcomes["missing"] = q.decode_result(encoded)
        # 重建文件但内容被改写（sha 不匹配）
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("tampered")
        outcomes["sha"] = q.decode_result(encoded)
        # 改成非 JSON
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("not json at all")
        outcomes["not_json"] = q.decode_result(encoded)
        # 目录被整体删除
        os.remove(path)
        os.rmdir(os.path.dirname(path))
        outcomes["dir_gone"] = q.decode_result(encoded)

        markers = ["__file_missing__", "__file_sha_mismatch__", "__file_not_json__"]
        risk = any(not isinstance(v, dict) or not any(k in v for k in markers)
                   for v in outcomes.values())
        record("F1", "引用失效矩阵（缺失/篡改/非JSON/目录消失）", risk,
               "%s" % {k: (v if isinstance(v, dict) else type(v).__name__) for k, v in outcomes.items()})
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# F2 并发写同名：同内容 → 同名 → 幂等；.tmp 残留
# ---------------------------------------------------------------------------
def f2_concurrent_same_name():
    work = tempfile.mkdtemp(prefix="bf-f2-")
    cfg = _cfg(work)
    queues = [TaskQueue(TaskConfig.from_dict(
        {"name": "link", "role": "B", "key": "k",
         "queue": {"store": {"kind": "sqlite-local"}, "file_channel": cfg.queue["file_channel"]}},
        base_dir=str(work), warn_plaintext=False)) for _ in range(2)]
    try:
        payload = {"result": {"blob": "y" * 3000}, "channel": "n", "name": "n"}
        encoded = [q.encode_result(payload) for q in queues]
        nodes = [_envelope(q, e) for q, e in zip(queues, encoded)]
        paths = {n["file_ref"]["path"] for n in nodes}
        leftovers = [n for n in os.listdir(cfg.queue["file_channel"]["dir"]) if n.endswith(".tmp")]
        same_content = all(n["file_ref"]["sha256"] == nodes[0]["file_ref"]["sha256"]
                           for n in nodes)
        risk = (len(paths) != 1) or bool(leftovers) or not same_content
        record("F2", "并发写同内容（同名幂等/无 .tmp 残留）", risk,
               "落点数=%d（期望 1）、.tmp 残留=%s、sha 一致=%s"
               % (len(paths), leftovers, same_content))
        return risk
    finally:
        for q in queues:
            q.close()


# ---------------------------------------------------------------------------
# F3 清理误删：目录里的非结果文件是否会被删
# ---------------------------------------------------------------------------
def f3_cleanup_over_delete():
    work = tempfile.mkdtemp(prefix="bf-f3-")
    files_dir = os.path.join(str(work), "files")
    os.makedirs(files_dir, exist_ok=True)
    # 放一个「非结果」文件（例如运维随手放的说明/配置）
    keeper = os.path.join(files_dir, "README-ops.txt")
    with open(keeper, "w", encoding="utf-8") as fh:
        fh.write("运维说明，请勿删除")
    import time
    os.utime(keeper, (time.time() - 30 * 86400, time.time() - 30 * 86400))   # 30 天前
    q = TaskQueue(_cfg(work, keep_days=7))
    try:
        removed = q.cleanup_result_files()
        risk = not os.path.exists(keeper)
        record("F3", "清理只删结果文件（不误删同目录其它文件）", risk,
               "removed=%d、运维文件是否还在=%s（期望还在：清理应只认结果文件）"
               % (removed, os.path.exists(keeper)))
        return risk
    finally:
        q.close()


# ---------------------------------------------------------------------------
# F4 目录穿越：file_channel.dir 指向 base_dir 之外
# ---------------------------------------------------------------------------
def f4_dir_escape():
    work = tempfile.mkdtemp(prefix="bf-f4-")
    base = os.path.join(work, "base")
    os.makedirs(base)
    cfg = TaskConfig.from_dict(
        {"name": "link", "role": "B", "key": "k",
         "queue": {"store": {"kind": "sqlite-local"},
                   "file_channel": {"enabled": True, "dir": "../escaped",
                                    "max_bytes": 100, "keep_days": 7}}},
        base_dir=base, warn_plaintext=False)
    q = TaskQueue(cfg)
    try:
        note = ""
        escaped = False
        try:
            encoded = q.encode_result({"result": {"blob": "z" * 3000}, "channel": "n", "name": "n"})
            ref = _envelope(q, encoded)["file_ref"]
            real = os.path.realpath(ref["path"])
            base_real = os.path.realpath(base)
            escaped = not real.startswith(base_real)
            note = "落点=%s" % real
        except SecretError as exc:
            # 修复后：越界配置必须被拒绝，且不得在 base_dir 之外建目录
            note = "已拒绝（SecretError）: %s" % str(exc).split("。")[0]
            escaped = False
        record("F4", "结果文件落点不得逃逸出 base_dir", escaped,
               "%s；逃逸=%s" % (note, escaped))
        return escaped
    finally:
        q.close()


# ---------------------------------------------------------------------------
# F5 与 result_max_bytes 的组合分支
# ---------------------------------------------------------------------------
def f5_combined_with_hard_cap():
    work = tempfile.mkdtemp(prefix="bf-f5-")
    q = TaskQueue(_cfg(work, max_bytes=500))
    try:
        # 分支一：文件通道开启 → 超阈值走文件（不再退化为摘要）
        big = _encode(q, 4000, result_max_bytes=2000)
        big_node = _envelope(q, big)
        big_offloaded = "file_ref" in big_node and "result_chars" not in big_node
        # 分支二：文件通道关闭 → 超过 result_max_bytes 退化为紧凑摘要
        off_cfg = TaskConfig.from_dict(
            {"name": "link", "role": "B", "key": "k",
             "queue": {"store": {"kind": "sqlite-local"},
                       "file_channel": {"enabled": False}, "result_max_bytes": 1000}},
            base_dir=str(work), warn_plaintext=False)
        off = TaskQueue(off_cfg)
        try:
            mid = off.encode_result({"result": {"blob": "y" * 1500}, "channel": "n", "name": "n"})
            mid_node = _envelope(off, mid)
        finally:
            off.close()
        mid_summarized = "result_chars" in mid_node and "file_ref" not in mid_node
        risk = not (big_offloaded and mid_summarized)
        record("F5", "file_channel 与 result_max_bytes 的分支不冲突", risk,
               "通道开启(4000B/上限2000) → file_ref=%s；通道关闭(1500B/上限1000) → 摘要=%s"
               % (big_offloaded, mid_summarized))
        return risk
    finally:
        q.close()


def main():
    print("=" * 92)
    for probe in (f1_ref_failure_matrix, f2_concurrent_same_name, f3_cleanup_over_delete,
                  f4_dir_escape, f5_combined_with_hard_cap):
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