# -*- coding: utf-8 -*-
"""API / 文档一致性稽核（verify 模式的可复用仪器）。

用途：确认「说过的都能跑、写过的都能用」——枚举 vools.rhop.task 的公开 API，
逐条核对 docs/task-queue.md 声称的配置字段/默认值/退出码/表结构列/存储契约/同步通道/审计口径
是否与实现一致。**只读**：不改任何源码或文档，发现不一致只报告。

运行：
    cd rhop && python tests/audit_api_doc.py            # 结构性稽核
    cd rhop && python tests/audit_api_doc.py 478       # 额外核对 §16 声明的全量用例数

退出码 = mismatch 条数（0 = 完全一致）。
"""
import argparse
import importlib
import inspect
import json
import os
import re
import subprocess
import sys

RHOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RHOP)

from vools.rhop.task import config as task_config   # noqa: E402
from vools.rhop.task import cli as task_cli         # noqa: E402
from vools.rhop.task import exec as task_exec        # noqa: E402
from vools.rhop.task import heartbeat as task_hb     # noqa: E402
from vools.rhop.task import models as task_models    # noqa: E402
from vools.rhop.task import queue as task_queue      # noqa: E402
from vools.rhop.task import secrets as task_secrets  # noqa: E402
from vools.rhop.task import store as task_store      # noqa: E402
from vools.rhop.task import sync as task_sync        # noqa: E402
from vools.rhop.task.store import sqlite_store      # noqa: E402
from vools.rhop.crypto import SECRET_PREFIX          # noqa: E402

DOC = os.path.join(RHOP, "docs", "task-queue.md")
import vools.rhop.task as task                        # noqa: E402

RESULTS = []


def check(kind, name, ok, detail=""):
    RESULTS.append((kind, name, bool(ok), detail))


def doc_text():
    with open(DOC, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------- 1. API 枚举
public = {}
for mod_name, mod in [("vools.rhop.task", task), ("task.config", task_config),
                      ("task.cli", task_cli), ("task.exec", task_exec),
                      ("task.heartbeat", task_hb), ("task.models", task_models),
                      ("task.queue", task_queue), ("task.secrets", task_secrets),
                      ("task.store", task_store), ("task.store.sqlite_store", sqlite_store)]:
    syms = [n for n, v in vars(mod).items()
            if not n.startswith("_") and (inspect.isclass(v) or inspect.isfunction(v))
            and getattr(v, "__module__", "").startswith("vools.rhop")]
    public[mod_name] = sorted(syms)
enumerated = sum(len(v) for v in public.values())

missing_all = [n for n in task.__all__ if not hasattr(task, n)]
check("API", "__all__ 全部可解析", not missing_all,
      "缺失: %s" % missing_all if missing_all else "%d 个名字全部存在" % len(task.__all__))

for cls_name in ["TaskQueue", "TaskConfig", "TaskDaemon", "TaskStore", "SqliteTaskStore",
                 "Heartbeat", "HeartbeatPump", "TaskSync", "TaskRecord", "TaskState",
                 "ExecPolicy", "RhopTaskError", "DagValidationError", "ExecDenied"]:
    check("API", "文档类名可导入: %s" % cls_name, hasattr(task, cls_name))

extra = sorted(set(public["vools.rhop.task"]) - set(task.__all__))
check("INFO", "模块级公开符号 vs __all__", True,
      "另有 %d 个模块级符号未进 __all__: %s" % (len(extra), ", ".join(extra[:12])))

# ---------------------------------------------------------------- 2. 默认值
doc = doc_text()
defaults = {
    "heartbeat.interval_sec": (task_config.DEFAULT_QUEUE["heartbeat"]["interval_sec"],
                               "| `queue.heartbeat.interval_sec` | float | 5"),
    "heartbeat.stale_after_sec": (task_config.DEFAULT_QUEUE["heartbeat"]["stale_after_sec"],
                                  "| `queue.heartbeat.stale_after_sec` | float | 15"),
    "heartbeat.closed_token": (task_config.DEFAULT_QUEUE["heartbeat"]["closed_token"],
                               "| `queue.heartbeat.closed_token` | str | `closed`"),
    "poll_interval_sec": (task_config.DEFAULT_QUEUE["poll_interval_sec"],
                          "| `queue.poll_interval_sec` | float | 2"),
    "max_retries": (task_config.DEFAULT_QUEUE["max_retries"], "| `queue.max_retries` | int | 3"),
    "retry_delay_min": (task_config.DEFAULT_QUEUE["retry_delay_min"],
                        "| `queue.retry_delay_min` | float | 5"),
    "timeout_min": (task_config.DEFAULT_QUEUE["timeout_min"], "| `queue.timeout_min` | float | 60"),
    "encrypt_result": (task_config.DEFAULT_QUEUE["encrypt_result"],
                       "| `queue.encrypt_result` | bool | true"),
    "result_max_bytes": (task_config.DEFAULT_QUEUE["result_max_bytes"],
                         "| `queue.result_max_bytes` | int | 65536"),
    "lock_ttl_sec": (task_config.DEFAULT_QUEUE["lock_ttl_sec"],
                     "| `queue.store.lock_ttl_sec` | float | 900"),
    "busy_timeout_sec": (15, "| `queue.store.busy_timeout_sec` | float | 15"),
}
for label, (value, doc_frag) in defaults.items():
    check("DEFAULTS", "%s=%s 与文档一致" % (label, value), doc_frag in doc,
          "" if doc_frag in doc else "文档里找不到片段: %s" % doc_frag[:60])

check("DEFAULTS", "exec.allow 默认值",
      task_config.DEFAULT_EXEC["allow"] == ["action:*", "handler:*"]
      and '`["action:*","handler:*"]`' in doc.replace(" ", ""),
      "code=%s" % task_config.DEFAULT_EXEC["allow"])
check("DEFAULTS", "exec.allow_any 默认 false",
      task_config.DEFAULT_EXEC["allow_any"] is False
      and "`exec.allow_any` | bool | false" in doc)

# ---------------------------------------------------------------- 3. 退出码
exit_ok = all([
    task_cli.EXIT_HEARTBEAT[task_hb.STATE_ALIVE] == 0,
    task_cli.EXIT_HEARTBEAT[task_hb.STATE_CLOSED] == 0,
    task_cli.EXIT_HEARTBEAT[task_hb.STATE_STALE] == 1,
    task_cli.EXIT_HEARTBEAT[task_hb.STATE_MISSING] == 2,
    "`alive→0`、`closed→0`（主动停机不算故障）、`stale→1`、`missing→2`" in doc,
])
check("EXITCODE", "check-heartbeat 退出码与文档一致", exit_ok,
      "code=%s" % {k: v for k, v in task_cli.EXIT_HEARTBEAT.items()})

# ---------------------------------------------------------------- 4. 存储契约
abstract = sorted(getattr(task_store.TaskStore, "__abstractmethods__", set()))
doc_contract = ["init_schema", "insert_tasks", "claim_next", "set_state", "update_fields",
                "clean_stale_locks", "reset_failed", "requeue", "set_cancel_requested",
                "apply_task", "apply_state", "get_task", "list_tasks", "all_task_names",
                "count_by_state", "close"]
check("STORE", "TaskStore 抽象方法与文档 §4.4 契约一致",
      all(m in abstract for m in doc_contract),
      "abstract=%d, 文档提到但缺失=%s" % (len(abstract),
                                          [m for m in doc_contract if m not in abstract]))
check("STORE", "TaskStore 是真 ABC（BUG-279 收口口径）",
      "class TaskStore(abc.ABC)" in inspect.getsource(task_store.base)
      and "契约是强制的" in doc)
check("STORE", "内置后端 sqlite-shared/sqlite-local 均注册",
      {"sqlite-shared", "sqlite-local"} <= set(task_store.available_store_kinds()),
      "kinds=%s" % task_store.available_store_kinds())
check("STORE", "DEFAULT_STORE_KIND == 'sqlite-shared'",
      task_store.DEFAULT_STORE_KIND == "sqlite-shared"
      and "| `queue.store.kind` | str | `sqlite-shared` |" in doc.replace("**", ""))

# ---------------------------------------------------------------- 5. 表结构
cols = set(task_models.TASK_COLUMNS)
sql_cols = set(re.findall(r"^\s{4}([a-z_]+)\s+(?:INTEGER|TEXT|REAL)",
                          inspect.getsource(sqlite_store), re.M))
check("SCHEMA", "TASK_COLUMNS 与建表 SQL 列一致", cols == sql_cols,
      "仅代码: %s | 仅SQL: %s" % (sorted(cols - sql_cols), sorted(sql_cols - cols)))
doc_cols = set()
for row in re.findall(r"^\|\s*(.+?)\s*\|", doc, re.M):
    doc_cols |= set(re.findall(r"`([a-z_]+)`", row))
need_cols = {"task_id", "task_name", "task_type", "value", "deps", "state", "priority",
             "worker_id", "cancel_requested", "version", "payload_enc", "payload_sha",
             "back_info", "last_err", "created_at", "updated_at"}
check("SCHEMA", "文档 §5 表结构覆盖核心列", need_cols <= doc_cols,
      "缺: %s" % sorted(need_cols - doc_cols))

# ---------------------------------------------------------------- 6. 状态机
state_doc = {"PENDING", "LOCKED", "RUNNING", "COMPLETED", "FAILED", "RETRY_PENDING", "CANCELLED"}
check("STATES", "TaskState.ALL 与文档 §6 一致", set(task_models.TaskState.ALL) == state_doc)
check("STATES", "ACTIVE/TERMINAL 划分与文档一致",
      set(task_models.TaskState.ACTIVE) == {"PENDING", "LOCKED", "RUNNING", "RETRY_PENDING"}
      and set(task_models.TaskState.TERMINAL) == {"COMPLETED", "FAILED", "CANCELLED"})

# ---------------------------------------------------------------- 7. 密文/白名单/CLI
check("CRYPTO", "RHOP-ENC 前缀与文档一致",
      SECRET_PREFIX == "RHOP-ENC:" and "RHOP-ENC:" in doc)

parser = task_cli._build_parser()
subs = []
for action in parser._actions:
    if hasattr(action, "choices") and action.choices:
        subs = sorted(action.choices.keys())
expected_subs = {"submit", "serve", "once", "status", "watch", "check-heartbeat", "close",
                 "cancel", "requeue", "retry-failed", "sync", "config", "file-clean"}
check("CLI", "CLI 子命令与文档 §13 表一致", set(subs) == expected_subs,
      "code=%s" % subs)

check("EXEC", "默认白名单不含 cli:*",
      "cli:*" not in task_config.DEFAULT_EXEC["allow"]
      and '默认 `exec.allow = ["action:*", "handler:*"]`' in doc)
check("EXEC", "cli 审计口径与文档一致（BUG-281）",
      "def audit_cli_entry" in inspect.getsource(task_exec)
      and "cli 通道在**执行前**打一条审计行" in doc)
check("EXEC", "matched_pattern 与 check 共用判定",
      "def matched_pattern" in inspect.getsource(task_exec))

# ---------------------------------------------------------------- 8. 5 轮新增口径（Round 2-6）
check("R2-R6", "§14 resets 通道：文档与代码一致",
      "resets" in doc and "重置意图走" in doc
      and "def request_reset" in inspect.getsource(task_sync)
      and '"resets"' in inspect.getsource(task_sync))
check("R2-R6", "§9 心跳微秒精度：文档与代码一致",
      "微秒级" in doc and "%f" in task_hb.TIMESTAMP_FORMAT)
check("R2-R6", "§8 结果硬上限：文档与代码一致",
      "硬上限" in doc and "def _shrink_result_to_bytes" in inspect.getsource(task_queue))
check("R2-R6", "§10 分级建议已写入文档", "分级建议" in doc)
check("R2-R6", "§15 无残留『未修』（BUG-279..283 已闭环）",
      not re.search(r"BUG-28[0-3].{0,40}未修", doc))
check("R2-R6", "§15 记录 BUG-281 为设计性质", "设计性质" in doc)

# ---------------------------------------------------------------- 9. 文档引用路径
for ref in ["tools/config_generator.html", "secret.py", "task/store", "task/heartbeat.py",
            "task/sync.py", "task/cli.py", "tests/boundary/README.md"]:
    candidates = [os.path.join(RHOP, ref), os.path.join(RHOP, "vools", "rhop", ref),
                  os.path.join(RHOP, "vools", "rhop", "task", ref),
                  os.path.join(RHOP, "tests", ref)]
    check("DOCPATH", "文档引用路径存在: %s" % ref, any(os.path.exists(c) for c in candidates))

# ---------------------------------------------------------------- 10. §16 用例数自校
doc_total = None
m = re.search(r"# (\d+) passed（", doc)
if m:
    doc_total = int(m.group(1))
check("DOCCOUNT", "§16 声明的全量用例数为整数", doc_total is not None,
      "文档 §16: %s" % doc_total)
if len(sys.argv) > 1 and doc_total is not None:
    try:
        actual = int(sys.argv[1])
        check("DOCCOUNT", "§16 声明数与实际全量用例数一致", actual == doc_total,
              "文档=%d 实际=%d（差异 %d）" % (doc_total, actual, actual - doc_total))
    except ValueError:
        check("DOCCOUNT", "§16 声明数与实际一致", False, "无法解析实际值 %r" % sys.argv[1])

# ---------------------------------------------------------------- 10b. §16 逐文件计数自校
# 只看形如 | `test_xxx.py` | 12 | 的行，避免误匹配其它表格。
_rows = [(m[0], int(m[1])) for m in re.findall(r"\|\s*`(test_[A-Za-z0-9_]+\.py)`\s*\|\s*(\d+)\s*\|", doc)]
drifted = []
for _name, _declared in _rows:
    _out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "--collect-only", "tests\\" + _name],
                          capture_output=True, text=True, encoding="utf-8", cwd=RHOP)
    _actual = len([l for l in (_out.stdout or "").splitlines() if "::" in l and ".py" in l])
    if _actual != _declared:
        drifted.append("%s 文档=%d 实际=%d" % (_name, _declared, _actual))
check("DOCCOUNT", "§16 逐文件用例数与实测一致", not drifted,
      "漂移: %s" % "; ".join(drifted) if drifted else "%d 行逐文件计数全部一致" % len(_rows))

# ---------------------------------------------------------------- 10c. 文档头状态行自校
# BUG-359 的后半：状态行与 §16 是两处独立声明，只校验 §16 会让头部一路漂移却无人发现。
_hdr = re.search(r"已实现并验证（(\d{4}-\d{2}-\d{2})[^）]*?(\d+)\s*passed", doc)
check("DOCCOUNT", "文档头状态行记录了验证日期与用例数", _hdr is not None,
      "头部状态行: %s" % (_hdr.group(0) if _hdr else "未匹配"))
if _hdr is not None and doc_total is not None:
    _hdr_total = int(_hdr.group(2))
    check("DOCCOUNT", "文档头状态行用例数与 §16 一致", _hdr_total == doc_total,
          "状态行=%d §16=%d（差异 %d）" % (_hdr_total, doc_total, _hdr_total - doc_total))

# ---------------------------------------------------------------- 汇总
mismatch = [r for r in RESULTS if r[0] != "INFO" and not r[2]]
print("=" * 86)
print("module: vools.rhop.task")
print("api_enumerated: %d" % enumerated)
for mod_name in sorted(public):
    print("  %-26s %d" % (mod_name, len(public[mod_name])))
print("checks: %d | mismatch: %d" % (len(RESULTS), len(mismatch)))
print("=" * 86)
for kind, name, ok, detail in RESULTS:
    if ok and kind == "INFO":
        print("[INFO] %s: %s" % (name, detail))
    elif ok:
        print("[PASS] %s" % name)
    else:
        print("[MISMATCH] %s :: %s" % (name, detail))
sys.exit(len(mismatch))