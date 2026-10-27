"""probe/compilers.py — 编译器探测。

复用 vools.sys.compile_cmd 和 vools.task.core.cli_exec。

并行化（本轮）
--------------
改前：11 个编译器串行遍历，每个都「shutil.which（本机 89 个 PATH 目录）→
起子进程取版本」，串行累加实测 1.4~3.9s（负载高时接近 4s），与 system_tools
并列 probe 池里的长尾。

改后：与 system_tools 同款两件事 ——
  1. **PATH 索引预筛**（`system_tools._build_path_index` / `_lookup_in_path_index`，
     单一真源）：PATH 只 listdir 一遍，判据仍交回 `shutil.which`；
  2. **11 条并发**（共享 `system_tools._inner_slot()` 内层并发闸门，避免和
     system_tools / runtimes 叠乘出上百个并发起进程）。
items 仍按 COMPILER_TABLE 原顺序输出，单条失败/超预算都被标记，不静默。

失败不再静默（上一轮加固，保留）
--------------------------------
改前：找到编译器后取版本那段是 `except Exception: pass`，然后返回空的 version。
任何抖动（超时、进程起不来、并发下资源竞争、输出编码炸掉）都会让版本号**悄悄
变成空串**，报告里没有任何信号 —— 实测并行化之后出现过 `cl` 版本为空
（8 次里 1 次），与「这台机器没装编译器」在数据上分不出来。

改后：失败必须留痕，且区分得开 ——
  * subprocess.TimeoutExpired 单独处理 → error_kind="timeout"；
  * 进程起不来 / 子进程自身错误（OSError、SubprocessError）→ "spawn_error"；
  * 跑起来了但没有任何输出 → "empty_output"（附退出码）；
  * 输出里找不到版本号形态 → "no_version_pattern"（不把 usage 文本当版本）；
  * 其它未知异常 → "unexpected"（不再吞掉，附异常类型）。
  人读的原因进 `error`，机读的结构化诊断进 `extra`（键名带 `version_` 前缀）。

契约不变（向后兼容）：
  * `ProbeItem` / `Prober` 一个字段都没改，`ProbeItem.extra` 是既有字段（默认 {}）；
  * 「工具不存在」依旧是 available=False + error="not found"；
  * 「工具在、版本取不到」记 available=True（path 有效、工具确实在）+
    version="" + error/extra 说明原因 —— `available` 语义没变，只是原本被丢掉的
    原因现在留下来了；
  * `_detect_compiler` 的既有返回键（name/available/path/version/error）不变，
    新增的 error_kind / version_extra 是可选键。

版本探测本身复用 `system_tools._get_version_detail`（单一真源）：解码回退链
（utf-8 → locale → replace）、版本号形态定位（stdout 首行 → stdout 后行 →
stderr → no_version_pattern）、异常分类都与 system_tools 完全一致。
"""


__all__ = [
    "CompilersProber",
]

import concurrent.futures
import time

from .base import Prober, ProbeItem
from .system_tools import (
    _build_path_index,
    _get_version_detail,
    _inner_slot,
    _lookup_in_path_index,
    _wait_for,
)

# 编译器检测表：(name, cmd, version_args)
COMPILER_TABLE = [
    ("gcc", "gcc", ["--version"]),
    ("g++", "g++", ["--version"]),
    ("clang", "clang", ["--version"]),
    ("cl", "cl", ["??"]),  # MSVC cl.exe
    ("rustc", "rustc", ["--version"]),
    ("cargo", "cargo", ["--version"]),
    ("nim", "nim", ["--version"]),
    ("zig", "zig", ["version"]),
    ("go", "go", ["version"]),
    ("javac", "javac", ["-version"]),
    ("java", "java", ["-version"]),
]

# 并发度/上限：11 条任务一次全放出去（远小于单个探测器的 16 线程档位，
# 真正的上限由共享的内层并发闸门兜住）；预算只做病态兜底。
_DEFAULT_MAX_WORKERS = 11
_DEFAULT_TOTAL_BUDGET = 15.0


def _detect_compiler(cmd, version_args, timeout=5, path_index=None):
    """检测单个编译器。

    path_index 为空时与改前逐字一致（走 shutil.which）；传入索引时先用
    「PATH 前缀预筛」缩小 which 的搜索范围（判据仍是 which 本体）。

    返回 dict：既有键 name/available/path/version/error 语义不变；
    新增可选键 error_kind（timeout/spawn_error/empty_output/no_version_pattern/
    unexpected/None）与 version_extra（结构化诊断，失败/降级时非空）。
    """
    if path_index is None:
        import shutil
        path = shutil.which(cmd)
    else:
        path = _lookup_in_path_index(cmd, path_index)
    if not path:
        return {
            "name": cmd,
            "available": False,
            "error": "not found",
            "error_kind": None,
            "version_extra": {},
        }

    version, error, extra = _get_version_detail(path, version_args, timeout)
    return {
        "name": cmd,
        "available": True,
        "path": path,
        "version": version,
        "error": error,
        "error_kind": extra.get("version_error_kind") if error else None,
        "version_extra": extra if extra else {},
    }


def _detect_one(entry, path_index, timeout):
    """工作单元：一条编译器的完整探测（占一个内层并发槽位）。"""
    name, cmd, version_args = entry
    with _inner_slot():
        try:
            return entry, _detect_compiler(cmd, version_args, timeout, path_index)
        except Exception as exc:        # 串行版这里会抛穿整个探测器
            return entry, {
                "name": cmd,
                "available": False,
                "error": "compiler probe crashed (%s): %s" % (
                    type(exc).__name__, exc),
                "error_kind": None,
                "version_extra": {},
            }


class CompilersProber(Prober):
    """编译器探测器（表内编译器并发探测，结果按 COMPILER_TABLE 原顺序保序）。

    新增可选旋钮（都有默认值，probe() 侧 `CompilersProber()` 调用不变）：
      * max_workers: 并发度，默认 11（= 表长度，一次全放开）；
      * total_budget: 整批墙钟上限秒数，默认 15.0（病态兜底；<=0 表示不设上限）。
    `last_stats`（只读诊断，不进报告）记录本次并发/预算的落地情况。
    """

    def __init__(self, timeout=5, max_workers=None, total_budget=None):
        Prober.__init__(self, timeout=timeout)
        self.max_workers = (_DEFAULT_MAX_WORKERS if max_workers is None
                            else int(max_workers))
        self.total_budget = (_DEFAULT_TOTAL_BUDGET if total_budget is None
                             else float(total_budget))
        self.last_stats = {}

    def probe(self):
        started = time.monotonic()
        budget = self.total_budget
        deadline = None if budget <= 0 else started + budget
        entries = list(COMPILER_TABLE)
        total = len(entries)
        stats = {"entries": total, "workers": 0, "budget_s": budget,
                 "path_index_ms": 0.0, "found": 0, "missing": 0,
                 "version_ok": 0, "version_failed": 0, "expired": 0}
        if total == 0:
            self.last_stats = stats
            return []

        index_started = time.monotonic()
        path_index = _build_path_index()
        stats["path_index_ms"] = round((time.monotonic() - index_started) * 1000.0, 1)

        workers = max(1, min(self.max_workers, total))
        stats["workers"] = workers
        budget_note = ("%.1fs total probe budget exhausted" % budget
                       if budget > 0 else "total probe budget exhausted")

        results = [None] * total
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="probe-compilers")
        try:
            jobs = {}
            for index, entry in enumerate(entries):
                jobs[executor.submit(_detect_one, entry, path_index,
                                     self.timeout)] = index
            done, failed, expired = _wait_for(jobs, deadline)

            # _wait_for 的 results/failures 都是「按 key（这里是下标）索引」的 dict
            for index, value in done.items():
                results[index] = value
            for index, exc in failed.items():
                results[index] = (entries[index], {
                    "name": entries[index][0],
                    "available": False,
                    "error": "compiler probe failed (%s): %s" % (
                        type(exc).__name__, exc),
                    "error_kind": None,
                    "version_extra": {},
                })
            for index in expired:
                results[index] = (entries[index], {
                    "name": entries[index][0],
                    "available": False,
                    "error": "not probed: " + budget_note,
                    "error_kind": None,
                    "version_extra": {},
                })
        finally:
            # 与 system_tools 同理：不 wait，否则一个卡死编译器会把预算拖失效
            executor.shutdown(wait=False)

        items = []
        for index, entry in enumerate(entries):
            pair = results[index]
            if pair is None:            # 防御：绝不返回空洞
                info = {"name": entry[0], "available": False,
                        "error": "probe produced no result",
                        "version_extra": {}}
            else:
                info = pair[1]
            if info.get("available"):
                stats["found"] += 1
                if info.get("error"):
                    stats["version_failed"] += 1
                else:
                    stats["version_ok"] += 1
            elif info.get("error") == "not found":
                stats["missing"] += 1
            else:
                stats["expired"] += 1
            items.append(ProbeItem(
                name=info.get("name") or entry[0],
                category="compilers",
                available=info.get("available", False),
                path=info.get("path"),
                version=info.get("version"),
                error=info.get("error"),
                extra=info.get("version_extra") or {},
            ))

        stats["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 1)
        self.last_stats = stats
        return items
