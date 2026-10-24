"""vools.rhop.daemon - 常驻 daemon（双方共用，side 参数区分行为）

双方各跑一个常驻 daemon，通过 side 参数区分行为：
    - REQUESTER: 提交任务，等结果
    - EXECUTOR:  领任务，执行，回结果

核心循环（每 N 秒）：
    1. pull_remote: 从传输层拉取对端新信封，写入本地 mirror DB
    2. process_inbox: 处理本地 inbox/ 里的信封
    3. push_local: 推送本地变化给对端
    4. cleanup: 清理过期任务

Q2 默认决策：payload 里写 cmd 字段直接执行，也支持注册 handler。
Q3 默认决策：PENDING 可取消，推送后尽力而为。
"""

import json
import os
import shutil
import signal
import subprocess
import time
from typing import Callable, Optional

from .core import Side, TaskStatus
from .envelope import Envelope
from .mirror import MirrorDB, StaleVersionError


# ---------------------------------------------------------------------------
# 时间戳辅助（Py3.6 兼容，镜像 _now_iso）
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# 默认执行器：按 payload['cmd'] 执行 shell 命令
# ---------------------------------------------------------------------------

def _default_execute(payload: dict, timeout_sec: int = 3600):
    """默认执行器：根据 payload['cmd'] 执行 shell 命令。"""
    cmd = payload.get("cmd")
    if not cmd:
        raise ValueError("payload 缺少 cmd 字段，无法执行")
    if isinstance(cmd, list):
        cmd = " ".join(str(c) for c in cmd)
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout_sec
    )
    if result.returncode != 0:
        raise RuntimeError(
            "cmd exited %d: %s" % (result.returncode, result.stderr[:500])
        )
    return {"stdout": result.stdout, "returncode": result.returncode}


# ---------------------------------------------------------------------------
# RelayDaemon
# ---------------------------------------------------------------------------

class RelayDaemon:
    """常驻 daemon：双方各跑一个，通过 side 参数区分行为。"""

    def __init__(self, config: dict):
        self.config = config
        self.side = Side(config.get("side", "requester"))
        self.data_dir = config.get("data_dir", "./rhop-data")
        self.poll_interval = int(config.get("poll_interval", 10))
        self.timeout_sec = int(config.get("timeout_sec", 3600))
        self._running = False

        # 镜像数据库
        db_path = os.path.join(self.data_dir, "mirror.db")
        self.mirror = MirrorDB(db_path)

        # 传输层（延迟创建，按需选用）
        self._transport_mode = config.get("transport", "auto")
        self._shared_path = config.get("shared_path")
        self._online_channels = config.get("online_channels", [])

        # 自定义执行器 handler（payload -> result）
        self._executor_handler = config.get("executor_handler")

        # 签名器
        signer_cfg = config.get("signer", {})
        from .signer import FileHashSigner, NPUSigner
        if signer_cfg.get("mode") == "npu":
            self._signer = NPUSigner(marker=signer_cfg.get("npu_marker", "NPU_MARKER"))
        else:
            self._signer = FileHashSigner()

    # ---- 生命周期 ----

    def start(self):
        """启动 daemon（阻塞）。"""
        self._running = True
        self._ensure_dirs()
        self._log("daemon started, side=%s, transport=%s" % (
            self.side.value, self._transport_mode))
        while self._running:
            try:
                self._run_once()
            except Exception as e:
                self._log("error in run_once: %s" % e)
            time.sleep(self.poll_interval)

    def stop(self, signum=None, frame=None):
        """优雅停止。"""
        self._log("daemon stopping...")
        self._running = False
        self.mirror.close()

    def _run_once(self):
        """单次迭代：拉取 → 处理 → 推送 → 同步。"""
        # 1. 拉取对端新信封
        self._pull_remote()

        # 2. 处理本地 inbox/ 里的信封
        self._process_inbox()

        # 3. 推送本地变化给对端
        self._push_local()

        # 4. 清理过期任务
        self._cleanup()

    # ---- 拉取对端 ----

    def _pull_remote(self):
        """从传输层拉取对端的新信封。"""
        other = self.side.other
        remote_dir = "inbox/%s" % other.value
        inbox = os.path.join(self.data_dir, "inbox")
        pulled = 0

        # 遍历传输层可用通道
        for transport in self._iter_transports():
            try:
                files = transport.listdir(remote_dir) if hasattr(transport, '.listdir') else []
                for fname in files:
                    if not fname.endswith(".rhop"):
                        continue
                    fpath = os.path.join(remote_dir, fname)
                    content = transport.read_text(fpath) if hasattr(transport, 'read_text') else None
                    if content is None:
                        continue
                    env = Envelope.from_rhop_bytes(content.encode("utf-8"))
                    try:
                        self.mirror.upsert_task(env)
                        self._log("pulled task %s from %s" % (env.task_id, other.value))
                        pulled += 1
                    except StaleVersionError:
                        self._log("skipped stale task %s" % env.task_id)
                    self.mirror.log_sync("pull", type(transport).__name__, env.task_id, True)
            except Exception as e:
                self._log("pull error: %s" % e)
        return pulled

    # ---- 处理本地 inbox ----

    def _process_inbox(self):
        """处理本地 inbox/ 里的信封。"""
        inbox = os.path.join(self.data_dir, "inbox")
        if not os.path.isdir(inbox):
            return
        for fpath in sorted(os.listdir(inbox)):
            if not fpath.endswith(".rhop"):
                continue
            full_path = os.path.join(inbox, fpath)
            try:
                with open(full_path, "rb") as fh:
                    raw = fh.read()
                env = Envelope.from_rhop_bytes(raw)
            except Exception as e:
                self._log("read envelope failed %s: %s" % (fpath, e))
                self._move_envelope(fpath, "failed")
                continue
            if self.side == Side.REQUESTER:
                self._process_as_requester(env, fpath)
            else:
                self._process_as_executor(env, fpath)

    def _process_as_requester(self, env: Envelope, fname: str):
        """需求端处理：暂不需要额外处理（daemon 只做同步）。"""
        inbox = os.path.join(self.data_dir, "inbox")
        src = os.path.join(inbox, fname)
        if os.path.exists(src):
            self._move_envelope(fname, "outbox")

    def _process_as_executor(self, env: Envelope, fname: str):
        """任务端处理：领任务 → 执行 → 写结果。"""
        if env.status != TaskStatus.PENDING:
            self._move_envelope(fname, "outbox")
            return
        task_id = env.task_id
        # 1. 标记 CLAIMED
        try:
            self.mirror.update_status(task_id, TaskStatus.CLAIMED)
        except ValueError as e:
            self._log("claim failed %s: %s" % (task_id, e))
            return
        # 2. 标记 RUNNING
        self.mirror.update_status(task_id, TaskStatus.RUNNING)
        # 3. 执行任务
        try:
            if self._executor_handler is not None:
                result = self._executor_handler(env.payload)
            else:
                result = _default_execute(env.payload, self.timeout_sec)
            # 签名
            sig = self._signer.sign(task_id, result)
            # 4. 写结果
            self.mirror.update_status(task_id, TaskStatus.DONE, result=result, signature=sig)
            self._log("task %s done" % task_id)
        except Exception as e:
            self.mirror.update_status(task_id, TaskStatus.FAILED, error=str(e))
            self._log("task %s failed: %s" % (task_id, e))
        # 5. 移动信封到 outbox/
        self._move_envelope(fname, "outbox")

    # ---- 推送本地变化 ----

    def _push_local(self):
        """推送本地变化给对端。"""
        outbox = os.path.join(self.data_dir, "outbox")
        if not os.path.isdir(outbox):
            return
        other = self.side.other
        remote_dir = "outbox/%s" % other.value
        for fname in sorted(os.listdir(outbox)):
            if not fname.endswith(".rhop"):
                continue
            src = os.path.join(outbox, fname)
            with open(src, "rb") as fh:
                raw = fh.read()
            for transport in self._iter_transports():
                try:
                    if hasattr(transport, 'write_text'):
                        transport.write_text(os.path.join(remote_dir, fname), raw.decode("utf-8"))
                    self._log("pushed %s to %s" % (fname, other.value))
                    break
                except Exception as e:
                    self._log("push error: %s" % e)

    # ---- 清理 ----

    def _cleanup(self):
        """清理已完成/已失败任务的本地信封（保留 outbox 记录）。"""
        pass  # 保留所有信封用于审计；可按需添加 TTL 清理

    # ---- 目录与文件辅助 ----

    def _ensure_dirs(self):
        for d in ("inbox", "outbox", "processing", "failed", "tmp"):
            os.makedirs(os.path.join(self.data_dir, d), exist_ok=True)

    def _move_envelope(self, fname: str, dest: str):
        inbox = os.path.join(self.data_dir, "inbox")
        dst_dir = os.path.join(self.data_dir, dest)
        src = os.path.join(inbox, fname)
        if os.path.exists(src):
            dst = os.path.join(dst_dir, fname)
            shutil.move(src, dst)

    def _iter_transports(self):
        """按优先级迭代传输通道（简化版：shared_path > online_channels）。"""
        if self._shared_path and hasattr(self._shared_path, 'available'):
            if self._shared_path.available():
                yield self._shared_path
        for ch in self._online_channels:
            try:
                if ch.available():
                    yield ch
            except Exception:
                pass

    def _log(self, msg: str):
        import sys
        sys.stderr.write("[%s] [%s] %s\n" % (_now_iso(), self.side.value, msg))
        sys.stderr.flush()


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    """CLI 入口：rhop-daemon --config <path>"""
    import argparse
    parser = argparse.ArgumentParser(description="vools-rhop relay daemon")
    parser.add_argument("--config", required=True, help="配置文件路径（JSON）")
    parser.add_argument("--data-dir", required=False, help="数据目录（覆盖配置）")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    if args.data_dir:
        config["data_dir"] = args.data_dir

    daemon = RelayDaemon(config)
    signal.signal(signal.SIGINT, daemon.stop)
    signal.signal(signal.SIGTERM, daemon.stop)
    daemon.start()


if __name__ == "__main__":
    main()
