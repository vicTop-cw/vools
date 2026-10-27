"""probe/runtimes.py — 运行时探测。

复用 vools.actus.runtimes.RuntimeRegistry，不重复实现。

并行化 + 去重（本轮）
----------------------
改前：串行遍历 `registry._runtimes.items()`，每一条都做
「`is_available()`（内部 `shutil.which`，本机 89 个 PATH 目录）+ which + 起子进程取版本」。
关键是：**20 条里有 6 组重复** —— registry 把同一个运行时实例注册在
`name` 与它的每个 alias 下（python/py/python3 → 同一个 PythonRuntime；
shell/bash/sh/powershell/pwsh/cmd → 同一个 ShellRuntime；node/nodejs/js/javascript、
go/golang、rust/rs、ruby/rb 同理），**实际只有 7 个运行时**。
于是同一个运行时被重复探测 3~6 次，串行实测 5.4~6.8s，是 probe 池里的新地板。

改后：
  1. **按运行时实例去重**（`id(runtime)`）→ 只有 7 个任务，工作只做一遍；
  2. 7 个任务并发跑（ThreadPoolExecutor + 共享内层并发闸门
     `system_tools._inner_slot()`，不与 system_tools / compilers 叠乘起进程）；
  3. 每条的 `shutil.which` 走 PATH 索引预筛（`system_tools._lookup_in_path_index`，
     单一真源），版本号走 `system_tools._get_version_detail`（解码回退链 + 版本号
     形态定位 + 失败留痕）；
  4. items **仍按 registry 原顺序逐条输出 20 条**（条数/顺序/`extra["aliases"]` 不变），
     重复别名共享同一份探测结果。

契约不变：`ProbeItem`/`Prober` 不变；item 的 name/available/path/version/
`extra["aliases"]` 语义与改前一致；新增的是「版本取不到时」的 `error`/`extra`
信号（改前那里是 `except Exception: pass` 的静默空串）。
"""


__all__ = [
    "RuntimesProber",
]

import concurrent.futures
import os
import shutil
import time

from .base import Prober, ProbeItem
from .system_tools import (
    _build_path_index,
    _get_version_detail,
    _inner_slot,
    _lookup_in_path_index,
    _wait_for,
)

# 运行时名 → 用来找可执行文件的候选命令（与改前 cmd_map 逐字一致）
_CMD_MAP = {
    "python": ["python", "python3"],
    "shell": ["bash", "sh"],
    "node": ["node", "nodejs"],
    "go": ["go"],
    "rust": ["rustc", "cargo"],
    "ruby": ["ruby"],
    "php": ["php"],
}

# 版本参数：go 用 "version"，其余用 "--version"（与改前逐一对应）
_VERSION_ARGS = {"go": ["version"], "rust": ["--version"]}

# 7 个运行时，一次全放开；真正上限由共享内层闸门兜住。
_DEFAULT_MAX_WORKERS = 8
_DEFAULT_TOTAL_BUDGET = 15.0


def _find_runtime_path(runtime, path_index):
    """按 cmd_map 找运行时可执行文件（索引预筛；判据仍是 shutil.which）。"""
    commands = _CMD_MAP.get(runtime.name, [runtime.name])
    for command in commands:
        if path_index is None:
            path = shutil.which(command)
        elif os.path.dirname(command):
            path = shutil.which(command)
        else:
            path = _lookup_in_path_index(command, path_index)
        if path:
            return path
    return None


def _probe_one_runtime(runtime, path_index, timeout):
    """探测单个运行时实例（available / path / version），异常就地收口。"""
    result = {"available": False, "path": None, "version": "",
              "error": None, "extra": {}}
    with _inner_slot():
        try:
            available = runtime.is_available()
        except Exception as exc:      # 串行版这里会抛穿整个探测器
            result["error"] = "is_available failed (%s): %s" % (
                type(exc).__name__, exc)
            return result
        result["available"] = bool(available)
        if not available:
            return result

        try:
            path = _find_runtime_path(runtime, path_index)
            result["path"] = path
            if not path:
                # 改前这里静默留下 path=None/version=""；现在至少说清为什么
                result["error"] = ("runtime reports available but no executable "
                                   "was found on PATH")
                return result

            version, error, extra = _get_version_detail(
                path, _VERSION_ARGS.get(runtime.name, ["--version"]), timeout)
            result["version"] = version
            result["error"] = error
            result["extra"] = extra or {}
        except Exception as exc:
            result["error"] = "version probe failed (%s): %s" % (
                type(exc).__name__, exc)
    return result


class RuntimesProber(Prober):
    """运行时探测器（按实例去重后并发探测，items 按 registry 原顺序输出）。

    新增可选旋钮（都有默认值，probe() 侧 `RuntimesProber()` 调用不变）：
      * max_workers: 并发度，默认 8（> 去重后的运行时数）；
      * total_budget: 整批墙钟上限秒数，默认 15.0（病态兜底；<=0 表示不设上限）。
    `last_stats`（只读诊断，不进报告）记录本次去重/并发/预算的落地情况。
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
        stats = {"entries": 0, "unique_runtimes": 0, "workers": 0,
                 "path_index_ms": 0.0, "version_ok": 0, "version_failed": 0,
                 "not_available": 0, "expired": 0}

        try:
            from ..runtimes import RuntimeRegistry
            registry = RuntimeRegistry()
            entries = list(registry._runtimes.items())
        except Exception as exc:       # 与改前一致：整段降级成一条 error 条目
            stats["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 1)
            self.last_stats = stats
            return [ProbeItem(
                name="runtimes",
                category="runtimes",
                available=False,
                error=str(exc),
            )]

        stats["entries"] = len(entries)
        if not entries:
            stats["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 1)
            self.last_stats = stats
            return []

        # ── 去重：registry 把同一个实例注册在 name 与每个 alias 下 ──
        # 用 id() 分组，但同时持有对象引用，避免 id 复用导致的错配。
        groups = []                    # [(runtime, [entry_index, ...]), ...]
        index_by_id = {}
        for index, (key, runtime) in enumerate(entries):
            ident = id(runtime)
            if ident not in index_by_id:
                index_by_id[ident] = len(groups)
                groups.append((runtime, [index]))
            else:
                groups[index_by_id[ident]][1].append(index)
        stats["unique_runtimes"] = len(groups)

        budget = self.total_budget
        deadline = None if budget <= 0 else started + budget
        budget_note = ("%.1fs total probe budget exhausted" % budget
                       if budget > 0 else "total probe budget exhausted")

        index_started = time.monotonic()
        path_index = _build_path_index()
        stats["path_index_ms"] = round((time.monotonic() - index_started) * 1000.0, 1)

        workers = max(1, min(self.max_workers, len(groups)))
        stats["workers"] = workers

        results = {}
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="probe-runtimes")
        try:
            jobs = {}
            for position, (runtime, _entry_indexes) in enumerate(groups):
                jobs[executor.submit(_probe_one_runtime, runtime, path_index,
                                     self.timeout)] = position
            done, failed, expired = _wait_for(jobs, deadline)
            # _wait_for 的 results/failures 都是「按 key（这里是分组下标）索引」的 dict
            for position, value in done.items():
                results[position] = value
            for position, exc in failed.items():
                results[position] = {
                    "available": False, "path": None, "version": "",
                    "error": "runtime probe crashed (%s): %s" % (
                        type(exc).__name__, exc), "extra": {}}
            for position in expired:
                results[position] = {
                    "available": False, "path": None, "version": "",
                    "error": "not probed: " + budget_note, "extra": {}}
        finally:
            # 与 system_tools 同理：不 wait，否则卡死的运行时会拖垮预算
            executor.shutdown(wait=False)

        # ── 统计（按去重后的运行时算，不是按 20 条别名重复计）──
        for position, (runtime, _entry_indexes) in enumerate(groups):
            info = results.get(position) or {}
            if info.get("available"):
                if info.get("error"):
                    stats["version_failed"] += 1
                else:
                    stats["version_ok"] += 1
            else:
                stats["not_available"] += 1

        # ── 按 registry 原顺序逐条输出 20 条（重复别名共享同一份结果）──
        items = []
        for index, (key, runtime) in enumerate(entries):
            position = index_by_id[id(runtime)]
            info = results.get(position) or {
                "available": False, "path": None, "version": "",
                "error": "probe produced no result", "extra": {}}
            extra = {"aliases": runtime.aliases}
            if info.get("extra"):
                extra.update(info["extra"])
            items.append(ProbeItem(
                name=runtime.name,
                category="runtimes",
                available=info.get("available", False),
                path=info.get("path"),
                version=info.get("version") or "",
                error=info.get("error"),
                extra=extra,
            ))

        stats["items"] = len(items)
        stats["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 1)
        self.last_stats = stats
        return items
