"""vools.rhop.task.heartbeat - B 端心跳（xxxx.heartbeat）

协议（约定俗成的运维语义，简单到可以直接用记事本看）：

* **B 运行中**：每 ``interval_sec``（默认 5 秒）把当前 UTC 时间戳写进
  ``<shared>/<name>.heartbeat``（原子写：临时文件 + rename）；
* **文件一直不动** → A 判定 B 的服务挂了（``stale``，默认超过 3 个周期即 15 秒）；
* **文件内容为 ``closed``** → 这是停机指令：B 停止领取新任务、收尾当前任务后退出；
* **B 优雅停机**时也会把该文件写成 ``closed``，A 一眼看出"是主动关的，不是崩的"。

两个角色：
    Heartbeat      读写 + 四态判定（alive / stale / closed / missing），可直接单测；
    HeartbeatPump  后台线程（B 端用）：**独立于任务执行**按时写盘，
                   长任务跑 10 分钟也不会让 A 误判成"挂了"。

设计取舍：心跳文件内容就是"一行时间戳或 closed"，不塞 JSON —— 用户口径是
"写时间戳 / 填 closed"，保持人可读、可手工编辑（运维直接写 closed 就能停服务）。

时间戳精度：用微秒级 ISO（``TIMESTAMP_FORMAT``）。用秒精度会让 A 读到的 age 多出最多约 1s 的
截断误差——写入发生在 .900、读取紧随其后时读到 age≈0.9s 而真实只有 5ms，小阈值配置下会把活着的
B 判成"挂了"（BUG-282）。除本文档所述的判死阈值下限校验外，精度本身必须精确。
"""

from __future__ import absolute_import

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from .errors import HeartbeatError
from .models import parse_iso, utcnow, utcnow_iso

log = logging.getLogger("vools.rhop.task.heartbeat")

#: 读取结果的状态取值
STATE_ALIVE = "alive"
STATE_STALE = "stale"
STATE_CLOSED = "closed"
STATE_MISSING = "missing"
STATE_UNKNOWN = "unknown"

#: 心跳时间戳格式。**必须带小数秒**：秒精度会让 A 读到的 age 多出最多约 1s 的截断误差
#: （写入发生在 .900、读取紧随其后时读到 age≈0.9s，真实只有 5ms），小阈值配置下会把活着的 B
#: 判成死了（BUG-282）。微秒级精度下该误差为 0，config 层再配一道校验兜底。
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class Heartbeat(object):
    """心跳文件读写 + 状态判定。

    Args:
        shared:          shared path（写端视图写、读端视图读）；None 表示无介质
        filename:        心跳文件名（如 ``rhop-link.heartbeat``）
        interval_sec:    写间隔（默认 5 秒）
        stale_after_sec: 判死阈值（默认 15 秒 = 3 个周期）
        closed_token:    停机哨兵文本（默认 ``closed``）
        worker_id:       worker 标识（缺省不写进文件，仅诊断用）
        include_worker:  True 时文件内容为 ``"<ts> <worker_id>"``（默认只写时间戳）
        now_fn:          取当前时间（测试注入用），返回 tz-aware datetime
    """

    def __init__(self, shared: Any, filename: str, interval_sec: float = 5.0,
                 stale_after_sec: float = 15.0, closed_token: str = "closed",
                 worker_id: Optional[str] = None, include_worker: bool = False,
                 now_fn: Optional[Callable[[], Any]] = None):
        self.shared = shared
        self.filename = str(filename or "rhop.heartbeat")
        self.interval_sec = float(interval_sec or 5.0)
        self.stale_after_sec = float(stale_after_sec or 15.0)
        self.closed_token = str(closed_token or "closed")
        self.worker_id = worker_id
        self.include_worker = bool(include_worker)
        self._now_fn = now_fn or (lambda: utcnow())
        self._last_write_monotonic = 0.0

    # ------------------------------------------------------------------
    # 基础读写
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """是否具备可用的共享介质（无介质时读写会抛 HeartbeatError）。"""
        return self.shared is not None

    def _require_shared(self) -> Any:
        if self.shared is None:
            raise HeartbeatError(
                "未配置 shared path，无法读写心跳文件 %s："
                "请在配置里补 shared.write（或 shared.read）指向双方共同可达的介质。" % self.filename)
        return self.shared

    def read_raw(self) -> Optional[str]:
        """读原始内容；文件不存在返回 None。"""
        shared = self._require_shared()
        try:
            return shared.read_text(self.filename)
        except FileNotFoundError:
            return None
        except Exception as exc:  # 介质不可达等
            raise HeartbeatError("读取心跳文件 %s 失败: %s" % (self.filename, exc))

    def _write_raw(self, content: str) -> str:
        shared = self._require_shared()
        try:
            return shared.write_text(self.filename, content)
        except Exception as exc:
            raise HeartbeatError("写心跳文件 %s 失败: %s" % (self.filename, exc))

    def exists(self) -> bool:
        """心跳文件是否存在。"""
        shared = self._require_shared()
        try:
            return bool(shared.exists(self.filename))
        except Exception:
            return False

    def remove(self) -> bool:
        """删除心跳文件（清理/重置用）。"""
        shared = self._require_shared()
        try:
            return bool(shared.remove(self.filename))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 写端（B）
    # ------------------------------------------------------------------

    def current_content(self) -> Optional[str]:
        """当前内容（strip 后）；不存在返回 None。"""
        raw = self.read_raw()
        if raw is None:
            return None
        return raw.strip()

    def is_close_requested(self) -> bool:
        """是否已被要求停机（文件内容 == closed_token）。"""
        return self.current_content() == self.closed_token

    def tick(self, force: bool = False) -> Dict[str, Any]:
        """按节流间隔写一次时间戳；若发现 closed 指令则**不写**并返回 stop。

        Args:
            force: True 时忽略节流立即写（daemon 启动首次写、测试用）

        Returns:
            {"action": "written"|"stop", "ts":..., "content":..., "path":...}
        """
        content = self.current_content()
        if content == self.closed_token:
            return {"action": "stop", "reason": "closed", "ts": None,
                    "content": content, "path": self.filename}
        now_mono = time.monotonic()
        if not force and (now_mono - self._last_write_monotonic) < self.interval_sec:
            return {"action": "skipped", "ts": None, "content": content,
                    "path": self.filename}
        ts = self._now_fn().strftime(TIMESTAMP_FORMAT)
        text = "%s %s" % (ts, self.worker_id) if (self.include_worker and self.worker_id) else ts
        path = self._write_raw(text)
        self._last_write_monotonic = time.monotonic()
        return {"action": "written", "ts": ts, "content": text, "path": path}

    def write_closed(self) -> Dict[str, Any]:
        """写入停机哨兵（B 优雅退出 / 运维远程停机）。"""
        path = self._write_raw(self.closed_token)
        return {"action": "closed", "content": self.closed_token, "path": path}

    # ------------------------------------------------------------------
    # 读端（A）
    # ------------------------------------------------------------------

    def read(self) -> Dict[str, Any]:
        """读取心跳并判定状态。

        Returns:
            {
              "state":       "alive" | "stale" | "closed" | "missing" | "unknown",
              "ts":          ISO 文本或 None,
              "age_sec":     B 时间戳距今秒数（时钟偏差可能为负），
              "raw":         原始内容,
              "worker_id":   内容里带的 worker 标识（如有）,
              "error":       异常说明（state=unknown 时）,
            }
        """
        try:
            raw = self.read_raw()
        except HeartbeatError as exc:
            return {"state": STATE_UNKNOWN, "ts": None, "age_sec": None,
                    "raw": None, "worker_id": None, "error": str(exc)}
        if raw is None:
            return {"state": STATE_MISSING, "ts": None, "age_sec": None,
                    "raw": None, "worker_id": None, "error": None}

        text = raw.strip()
        if text == self.closed_token:
            return {"state": STATE_CLOSED, "ts": None, "age_sec": None,
                    "raw": text, "worker_id": None, "error": None}

        parts = text.split()
        stamp = parts[0] if parts else ""
        worker = parts[1] if len(parts) > 1 else None
        parsed = parse_iso(stamp)
        if parsed is None:
            return {"state": STATE_UNKNOWN, "ts": None, "age_sec": None,
                    "raw": text, "worker_id": worker,
                    "error": "心跳内容不是合法时间戳（也不是 closed）"}

        age = (self._now_fn() - parsed).total_seconds()
        state = STATE_ALIVE if age <= self.stale_after_sec else STATE_STALE
        return {"state": state, "ts": stamp, "age_sec": round(age, 3),
                "raw": text, "worker_id": worker, "error": None}

    def is_alive(self, max_age: Optional[float] = None) -> bool:
        """B 是否活着（默认按 stale_after_sec 判）。"""
        result = self.read()
        if max_age is None:
            return result["state"] == STATE_ALIVE
        age = result.get("age_sec")
        return age is not None and age <= float(max_age)

    def is_closed(self) -> bool:
        """B 是否已被停机（文件为 closed）。"""
        return self.read()["state"] == STATE_CLOSED

    def describe(self) -> Dict[str, Any]:
        """自描述（CLI 输出用）。"""
        return {
            "file": self.filename,
            "interval_sec": self.interval_sec,
            "stale_after_sec": self.stale_after_sec,
            "closed_token": self.closed_token,
            "worker_id": self.worker_id,
            "has_shared": self.shared is not None,
        }


class HeartbeatPump(object):
    """后台心跳线程：与任务执行解耦，长任务期间心跳照样跳。

    用法::

        pump = HeartbeatPump(heartbeat)      # heartbeat 为 Heartbeat
        pump.start()
        ... 主循环跑任务 ...
        pump.stop()                          # 退出前写 closed

    线程只做两件事：按时 ``tick()``；发现 ``closed`` 就置
    ``close_requested = True`` 并停止写盘（不再覆盖运维写下的 closed）。
    """

    def __init__(self, heartbeat: Heartbeat, on_close: Optional[Callable[[], None]] = None,
                 log_errors: bool = True):
        self.heartbeat = heartbeat
        self.on_close = on_close
        self.log_errors = log_errors
        self.close_requested = False
        self.last_result = None  # type: Optional[Dict[str, Any]]
        self._thread = None  # type: Optional[threading.Thread]
        self._stop_event = threading.Event()

    # ---- 生命周期 ----

    def start(self) -> "HeartbeatPump":
        """启动线程（幂等），并立即写一次心跳。"""
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop_event.clear()
        self._first_tick()
        self._thread = threading.Thread(target=self._loop, name="rhop-heartbeat",
                                        daemon=True)
        self._thread.start()
        return self

    def _first_tick(self) -> None:
        try:
            result = self.heartbeat.tick(force=True)
            self.last_result = result
            if result.get("action") == "stop":
                self.close_requested = True
                if self.on_close:
                    self.on_close()
        except Exception as exc:  # 介质暂时不可达不应让服务起不来
            if self.log_errors:
                log.warning("rhop heartbeat 首次写失败: %s", exc)

    def _loop(self) -> None:
        interval = max(float(self.heartbeat.interval_sec or 5.0), 0.05)
        while not self._stop_event.is_set():
            # 小步 sleep：停止指令能快速响应
            slept = 0.0
            step = min(interval, 0.25)
            while slept < interval and not self._stop_event.is_set():
                time.sleep(step)
                slept += step
            if self._stop_event.is_set():
                break
            try:
                result = self.heartbeat.tick(force=True)
                self.last_result = result
                if result.get("action") == "stop":
                    self.close_requested = True
                    if self.on_close:
                        try:
                            self.on_close()
                        except Exception as exc:
                            if self.log_errors:
                                log.warning("rhop heartbeat on_close 回调失败: %s", exc)
                    break
            except Exception as exc:
                if self.log_errors:
                    log.warning("rhop heartbeat 写失败（将重试）: %s", exc)

    def stop(self, write_closed: bool = True, timeout: float = 2.0) -> None:
        """停止线程；write_closed=True 时写停机哨兵。"""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None
        if write_closed:
            try:
                self.heartbeat.write_closed()
            except Exception as exc:
                if self.log_errors:
                    log.warning("rhop heartbeat 写 closed 失败: %s", exc)


__all__ = [
    "Heartbeat",
    "HeartbeatPump",
    "STATE_ALIVE",
    "STATE_STALE",
    "STATE_CLOSED",
    "STATE_MISSING",
    "STATE_UNKNOWN",
]