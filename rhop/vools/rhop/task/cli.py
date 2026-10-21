"""vools.rhop.task.cli - 任务队列命令行（``python -m vools.rhop.task``）

子命令（双方共用同一套；行为随配置方向自动切换）：

    submit            提交任务（A 侧）：--file tasks.json 或 --task 单条
    serve             B 侧常驻消费（心跳 + 领取 + 执行 + 回写）
    once              B 侧只跑一轮（cron / 调试）
    status            看任务状态（本地库模式会先拉一次同步）
    watch             A 侧盯到全部完成（并判定 B 心跳是否还活着）
    check-heartbeat   看 B 心跳：alive/stale/closed/missing
    close             往心跳文件写 closed（远端停机指令）
    cancel            取消任务
    requeue           把单个任务重置回 PENDING
    retry-failed      把 FAILED 全部重置回 PENDING
    sync              本地库模式下强制推/拉一次
    config            校验并打印已解析配置（敏感值打码）

退出码：0 成功；1 业务失败（如 B 已死）；2 参数/配置错误。
"""

from __future__ import absolute_import

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from .config import TaskConfig
from .daemon import TaskDaemon, build_queue
from .errors import RhopTaskError
from .heartbeat import (
    STATE_ALIVE,
    STATE_CLOSED,
    STATE_MISSING,
    STATE_STALE,
)

#: check-heartbeat 的退出码约定（便于脚本判断）
EXIT_HEARTBEAT = {
    STATE_ALIVE: 0,
    STATE_CLOSED: 0,       # 主动停机：不是故障
    STATE_STALE: 1,        # 心跳不动 → 服务挂了
    STATE_MISSING: 2,      # 从未启动 / 文件被删
    "unknown": 1,
}


def _common_options() -> argparse.ArgumentParser:
    """全局选项：同时挂到根解析器与各子命令上，`--config`/`--json` 前后位置都能给。

    用 ``default=argparse.SUPPRESS`` 是刻意的：父解析器和子解析器都定义同名选项时，
    子解析器的"默认值"会覆盖父解析器已解析出的值；SUPPRESS 让未出现的选项根本不写
    namespace，从而保留父解析器解析到的结果。
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS,
                        help="配置文件路径（JSON）")
    common.add_argument("--strict-secrets", action="store_true",
                        default=argparse.SUPPRESS,
                        help="配置里出现明文敏感信息时直接报错（CI/生产卡口）")
    common.add_argument("--no-warn-plaintext", action="store_true",
                        default=argparse.SUPPRESS,
                        help="不输出明文告警（默认会打警告并给出生成密文的命令）")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="以 JSON 输出（机器可读；stdout 保持纯 JSON）")
    return common


def _build_parser() -> argparse.ArgumentParser:
    common = _common_options()
    parser = argparse.ArgumentParser(
        prog="python -m vools.rhop.task",
        description="rhop 通用任务队列：A 提交加密 JSON 指令，B 解密执行（依赖由 SQLite 管理）",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command")

    def _sub(name: str, help_text: str) -> argparse.ArgumentParser:
        """建子命令解析器（继承全局选项）。"""
        return sub.add_parser(name, parents=[common], help=help_text)

    p_submit = _sub("submit", "提交任务")
    p_submit.add_argument("--file", help="任务 JSON 文件（数组或 {\"tasks\": [...]}）")
    p_submit.add_argument("--task", action="append", default=[],
                          help="单条任务名（可重复）")
    p_submit.add_argument("--type", default=None, help="task_type（默认 CLI）")
    p_submit.add_argument("--cmd", default=None, help="给单条任务配 cli.cmd")
    p_submit.add_argument("--lang", default=None, help="给单条任务配 cli.lang")
    p_submit.add_argument("--dep", default=None, help="逗号分隔的依赖任务名（配合 --task）")
    p_submit.add_argument("--priority", type=int, default=None)
    p_submit.add_argument("--wait", action="store_true", help="提交后等待完成（盯 B 心跳）")
    p_submit.add_argument("--timeout", type=float, default=None, help="--wait 的总超时秒")
    p_submit.add_argument("--poll", type=float, default=None, help="轮询间隔秒")

    p_serve = sub.add_parser("serve", help="B 侧常驻消费")
    p_serve.add_argument("--once", action="store_true", help="只跑一轮")
    p_serve.add_argument("--max-iterations", type=int, default=None)
    p_serve.add_argument("--no-closed-on-exit", action="store_true",
                         help="退出时不把心跳写成 closed")

    p_once = sub.add_parser("once", help="B 侧只跑一轮（等同 serve --once）")
    p_once.add_argument("--no-closed-on-exit", action="store_true")

    p_status = sub.add_parser("status", help="查看任务状态")
    p_status.add_argument("--state", default=None, help="按状态过滤（PENDING/RUNNING/...）")
    p_status.add_argument("--limit", type=int, default=200)
    p_status.add_argument("--show-payload", action="store_true", help="回显解密后的载荷")
    p_status.add_argument("--watch", action="store_true", help="持续刷新直到全部终结")
    p_status.add_argument("--interval", type=float, default=2.0)

    p_watch = sub.add_parser("watch", help="A 侧盯完成（含 B 心跳判活）")
    p_watch.add_argument("--timeout", type=float, default=None)
    p_watch.add_argument("--poll", type=float, default=None)
    p_watch.add_argument("--dead-grace", type=int, default=3)

    p_hb = sub.add_parser("check-heartbeat", help="查看 B 心跳状态")
    p_hb.add_argument("--max-age", type=float, default=None, help="自定义判活秒数")

    sub.add_parser("close", help="往心跳文件写 closed（远端停机指令）")

    p_cancel = sub.add_parser("cancel", help="取消任务")
    p_cancel.add_argument("--task", required=True)

    p_requeue = sub.add_parser("requeue", help="重置单个任务回 PENDING")
    p_requeue.add_argument("--task", required=True)

    sub.add_parser("retry-failed", help="把所有 FAILED 重置回 PENDING")

    p_sync = sub.add_parser("sync", help="本地库模式：强制推/拉同步包")
    p_sync.add_argument("--direction", choices=["push", "pull", "both"], default="both")

    p_conf = sub.add_parser("config", help="校验并打印已解析配置")
    p_conf.add_argument("--check-store", action="store_true", help="实际打开存储（校验路径/权限）")
    return parser


# ---------------------------------------------------------------------------
# 输出辅助
# ---------------------------------------------------------------------------

def _emit(args, payload: Any, text: Optional[str] = None) -> None:
    """统一输出：--json 走 JSON，否则打文本。"""
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif text:
        print(text)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _status_table(rows: List[Dict[str, Any]]) -> str:
    """把状态列表渲染成等宽表格。"""
    if not rows:
        return "(无任务)"
    header = ("TASK", "STATE", "PRI", "RETRY", "WORKER", "ERR")
    lines = ["%-22s %-14s %4s %7s %-14s %s" % header]
    lines.append("-" * 92)
    for row in rows:
        err = (row.get("last_err") or "").replace("\n", " ")
        lines.append("%-22s %-14s %4s %7s %-14s %s" % (
            str(row.get("task_name"))[:22],
            str(row.get("state")),
            row.get("priority", 0),
            "%s/%s" % (row.get("retry_count", 0), row.get("max_retries", 0)),
            str(row.get("worker_id") or "-")[:14],
            err[:44],
        ))
    counts = {}
    for row in rows:
        counts[row.get("state")] = counts.get(row.get("state"), 0) + 1
    lines.append("-" * 92)
    lines.append("合计: " + ", ".join("%s=%s" % (k, v) for k, v in sorted(counts.items())))
    return "\n".join(lines)


def _load_tasks_file(path: str) -> List[Any]:
    """读任务文件：支持数组或 {"tasks": [...]}。"""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("tasks") or data.get("items") or []
    if not isinstance(data, list):
        raise RhopTaskError("任务文件必须是数组，或 {\"tasks\": [...]}")
    return data


def _single_tasks(args) -> List[Any]:
    """由 --task/--cmd/--lang/--dep 组装单条或多条任务。"""
    deps = [d.strip() for d in str(args.dep or "").split(",") if d.strip()]
    out = []
    for name in args.task or []:
        item = {"task_name": name}  # type: Dict[str, Any]
        if args.type:
            item["task_type"] = args.type
        cli = {}
        if args.cmd:
            cli["cmd"] = args.cmd
        if args.lang:
            cli["lang"] = args.lang
        if cli:
            item["cli"] = cli
        if deps:
            item["deps"] = deps
        if args.priority is not None:
            item["priority"] = args.priority
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# 子命令实现
# ---------------------------------------------------------------------------

def _cmd_submit(args, config: TaskConfig) -> int:
    tasks = []
    if args.file:
        tasks.extend(_load_tasks_file(args.file))
    tasks.extend(_single_tasks(args))
    if not tasks:
        sys.stderr.write("[rhop-task] submit 需要 --file 或 --task\n")
        return 2
    daemon = TaskDaemon(config)
    try:
        defaults = {}
        if args.type:
            defaults["task_type"] = args.type
        if args.priority is not None:
            defaults["priority"] = args.priority
        result = daemon.run_sender(tasks, wait=args.wait, timeout=args.timeout,
                                   poll=args.poll, **defaults)
    finally:
        daemon.close(write_closed=False)
    submitted = result.get("submit") or {}
    text = "已提交 %s 条（跳过已存在 %s 条），共 %s 条" % (
        submitted.get("submitted"), submitted.get("skipped"), submitted.get("total"))
    if args.wait:
        text += "\n等待结果: %s" % result.get("reason")
        rows = result.get("status") or []
        text += "\n" + _status_table(rows)
    _emit(args, result, text)
    if args.wait and result.get("reason") in ("executor-dead", "timeout"):
        return 1
    return 0


def _cmd_serve(args, config: TaskConfig) -> int:
    once = bool(getattr(args, "once", False)) or args.command == "once"
    daemon = TaskDaemon(config)
    try:
        result = daemon.start(once=once, max_iterations=getattr(args, "max_iterations", None),
                              install_signals=True)
    finally:
        if once:
            daemon.close(write_closed=not getattr(args, "no_closed_on_exit", False))
    _emit(args, result, "执行结束: %s" % json.dumps(
        {k: v for k, v in result.items() if k in ("action", "task_name", "state",
                                                  "iterations", "completed", "failed",
                                                  "retried", "reason", "counts")},
        ensure_ascii=False))
    return 0


def _collect_status(args, config: TaskConfig, queue) -> List[Dict[str, Any]]:
    queue.pull_sync()  # 本地库模式先拉；共享库模式是 no-op
    return queue.status(state=args.state, limit=args.limit,
                        include_payload=getattr(args, "show_payload", False))


def _cmd_status(args, config: TaskConfig) -> int:
    queue = build_queue(config)
    try:
        rows = _collect_status(args, config, queue)
        if not args.watch:
            _emit(args, rows, _status_table(rows))
            return 0
        seen = None
        while True:
            rows = _collect_status(args, config, queue)
            snapshot = json.dumps([(r["task_name"], r["state"]) for r in rows],
                                  ensure_ascii=False)
            if snapshot != seen:
                print(_status_table(rows))
                seen = snapshot
            if queue.is_all_done():
                print("全部任务已终结")
                return 0
            import time
            time.sleep(max(float(args.interval), 0.01))
    finally:
        queue.close()


def _cmd_watch(args, config: TaskConfig) -> int:
    daemon = TaskDaemon(config)
    try:
        result = daemon.run_sender(wait=True, timeout=args.timeout, poll=args.poll,
                                   dead_grace=args.dead_grace)
    finally:
        daemon.close(write_closed=False)
    _emit(args, result, "等待结果: %s\n%s" % (result.get("reason"),
                                              _status_table(result.get("status") or [])))
    return 1 if result.get("reason") in ("executor-dead", "timeout") else 0


def _cmd_check_heartbeat(args, config: TaskConfig) -> int:
    heartbeat = config.build_heartbeat()
    if not heartbeat.enabled:
        sys.stderr.write("[rhop-task] 未配置 shared path，无法读取心跳\n")
        return 2
    info = heartbeat.read()
    if args.max_age is not None:
        alive = heartbeat.is_alive(max_age=args.max_age)
        info["state"] = STATE_ALIVE if alive else STATE_STALE
    text = "心跳文件 %s: state=%s ts=%s age=%ss%s" % (
        heartbeat.filename, info.get("state"), info.get("ts"), info.get("age_sec"),
        (" error=%s" % info["error"]) if info.get("error") else "")
    _emit(args, info, text)
    return EXIT_HEARTBEAT.get(info.get("state"), 1)


def _cmd_close(args, config: TaskConfig) -> int:
    heartbeat = config.build_heartbeat()
    if not heartbeat.enabled:
        sys.stderr.write("[rhop-task] 未配置 shared path，无法写停机指令\n")
        return 2
    result = heartbeat.write_closed()
    _emit(args, result, "已写入停机指令: %s = %s" % (heartbeat.filename,
                                                    heartbeat.closed_token))
    return 0


def _cmd_cancel(args, config: TaskConfig) -> int:
    queue = build_queue(config)
    try:
        queue.pull_sync()
        result = queue.cancel(args.task)
    finally:
        queue.close()
    _emit(args, result, "取消 %s: state=%s%s" % (
        result["task_name"], result["state"],
        "（RUNNING 中，已打取消标记，等它收尾）" if result.get("pending") else ""))
    return 0


def _cmd_requeue(args, config: TaskConfig) -> int:
    queue = build_queue(config)
    try:
        ok = queue.requeue(args.task)
    finally:
        queue.close()
    _emit(args, {"task_name": args.task, "requeued": ok},
          "已重置 %s 回 PENDING" % args.task if ok else "重置失败: %s" % args.task)
    return 0 if ok else 1


def _cmd_retry_failed(args, config: TaskConfig) -> int:
    queue = build_queue(config)
    try:
        count = queue.retry_failed()
    finally:
        queue.close()
    _emit(args, {"reset": count}, "已把 %s 条 FAILED 任务重置回 PENDING" % count)
    return 0


def _cmd_sync(args, config: TaskConfig) -> int:
    queue = build_queue(config)
    try:
        if queue.syncer is None:
            sys.stderr.write("[rhop-task] 当前 store.kind 不是 sqlite-local，无需同步\n")
            return 2
        out = {}
        if args.direction in ("push", "both"):
            out["push"] = queue._sync("push")
        if args.direction in ("pull", "both"):
            out["pull"] = queue.pull_sync()
    finally:
        queue.close()
    _emit(args, out, json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_config(args, config: TaskConfig) -> int:
    payload = {
        "describe": config.describe(),
        "resolved_masked": config.to_dict(mask=True),
        "plaintext_findings": config.plaintext_findings(),
    }
    if args.check_store:
        queue = build_queue(config)
        try:
            payload["store"] = queue.store.describe()
            payload["store_counts"] = queue.store.count_by_state()
        finally:
            queue.close()

    plaintext = config.plaintext_findings()
    notes = []
    if plaintext:
        notes.append("⚠ 有 %d 处敏感字段使用明文，请按上面的命令生成密文后回填。" % len(plaintext))
    if args.check_store:
        notes.append("存储校验通过: %s" % json.dumps(payload.get("store"), ensure_ascii=False))

    # stdout 始终是纯 JSON（便于管道/脚本 json.loads），提示统一走 stderr
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if notes:
        sys.stderr.write("\n".join(notes) + "\n")
    return 0


_COMMANDS = {
    "submit": _cmd_submit,
    "serve": _cmd_serve,
    "once": _cmd_serve,
    "status": _cmd_status,
    "watch": _cmd_watch,
    "check-heartbeat": _cmd_check_heartbeat,
    "close": _cmd_close,
    "cancel": _cmd_cancel,
    "requeue": _cmd_requeue,
    "retry-failed": _cmd_retry_failed,
    "sync": _cmd_sync,
    "config": _cmd_config,
}


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口，返回退出码。"""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    if not os.path.isfile(args.config):
        sys.stderr.write("[rhop-task] 配置文件不存在: %s\n" % args.config)
        return 2
    try:
        config = TaskConfig.from_file(args.config,
                                      strict_secrets=args.strict_secrets,
                                      warn_plaintext=not args.no_warn_plaintext)
    except RhopTaskError as exc:
        sys.stderr.write("[rhop-task] 配置错误: %s\n" % exc)
        return 2
    except (OSError, ValueError) as exc:
        sys.stderr.write("[rhop-task] 配置读取失败: %s\n" % exc)
        return 2

    handler = _COMMANDS.get(args.command)
    if handler is None:  # pragma: no cover - argparse 已限制取值
        parser.print_help()
        return 2
    try:
        return int(handler(args, config))
    except RhopTaskError as exc:
        sys.stderr.write("[rhop-task] 失败: %s\n" % exc)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())