"""calllog.py — 工具调用日志（call_log）。

参考 FIST-Mbt 的 call_log 能力（src/store/store_sqlite.mbt、src/server/server.mbt
的 instrumented_tool/_log_call），在 Actus 侧以最小可用形态落地：

- 每次 MCP/CLI 工具调用固化为一行记录：
  seq / ts / tool / caller / ns / params_json / result_json / ok / runtime_ms
- 存储：SQLite（``_meta/call_log.db``），失败静默降级为内存环形缓冲，绝不影响原调用。
- 读写入口：``write_call_log`` / ``recent_call_logs`` / ``instrument``。
- 用途：复盘「是哪次调用 + 入参 + 结果产生了 bug」，并为 bug 账本
  （``bugreport.py``）提供 ``ref_call_id`` 证据链。

设计原则（与 FIST 一致）：
1. best-effort：写库失败只吞掉，不改变原返回值。
2. 只读不改：日志追加，不修改业务数据。
3. 上限：内存缓冲 500 条；SQLite 上限由 ``max_rows`` 控制（默认 20000，超出裁剪最旧）。
"""


import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional

__all__ = [
    'CallLogStore', 'get_store', 'write_call_log', 'recent_call_logs',
    'instrument', 'log_path', 'reset_store',
]

_TZ = timezone(timedelta(hours=8))

_DDL = (
    "CREATE TABLE IF NOT EXISTS call_log ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, seq INTEGER, ts TEXT, tool TEXT, "
    "caller TEXT, ns TEXT, params_json TEXT, result_json TEXT, ok INTEGER, "
    "runtime_ms INTEGER)"
)

# 进程内单调序号（多实例并发时由 DB 侧 max(seq) 校正）
_seq_lock = threading.Lock()
_seq_counter = 0
_MEM_LIMIT = 500
_DEFAULT_MAX_ROWS = 20000


def _now_iso() -> str:
    return datetime.now(_TZ).isoformat(timespec='seconds')


def _default_meta() -> str:
    root = os.environ.get('ACTUS_REPO_ROOT')
    if root:
        return os.path.join(root, '_meta')
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), '_meta')


def log_path(meta_dir: Optional[str] = None) -> str:
    """call_log 数据库路径（缺省 ``<ACTUS_REPO_ROOT>/_meta/call_log.db``）。"""
    meta = meta_dir or _default_meta()
    return os.path.join(meta, 'call_log.db')


def _next_seq() -> int:
    global _seq_counter
    with _seq_lock:
        _seq_counter += 1
        return _seq_counter


class CallLogStore:
    """call_log 读写器。SQLite 优先，异常时降级为内存环形缓冲。"""

    def __init__(self, meta_dir: Optional[str] = None,
                 max_rows: int = _DEFAULT_MAX_ROWS):
        self.meta_dir = meta_dir
        self.max_rows = max_rows
        self.path = log_path(meta_dir)
        self._mem: List[dict] = []
        self._lock = threading.Lock()
        # 不常驻连接：每次操作短连接后立即关闭，避免占用文件句柄
        # （Windows 下常驻连接会阻塞 pytest tmp_path 清理，且长期占用日志文件）。
        self._use_sql = self._probe()

    # ── 连接（短连接：用完即关）──
    def _connect(self):
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        db = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
        db.execute(_DDL)
        row = db.execute("SELECT COALESCE(MAX(seq), 0) FROM call_log").fetchone()
        if row and row[0]:
            global _seq_counter
            with _seq_lock:
                if row[0] > _seq_counter:
                    _seq_counter = int(row[0])
        return db

    def _probe(self) -> bool:
        """探测 SQLite 是否可用（建库建表后立即释放句柄）。"""
        try:
            db = self._connect()
            db.commit()
            db.close()
            return True
        except Exception:
            return False

    @property
    def available(self) -> bool:
        return self._use_sql

    # ── 写 ──
    def write(self, tool: str, params: Any = None, result: Any = None,
              ok: bool = True, runtime_ms: int = 0, caller: str = 'mcp',
              ns: str = '', seq: Optional[int] = None) -> bool:
        """追加一条调用日志。best-effort：任何失败返回 False，不抛出。"""
        seq = _next_seq() if seq is None else seq
        ts = _now_iso()
        try:
            params_json = json.dumps(params, ensure_ascii=False, default=str)
        except Exception:
            params_json = str(params)
        try:
            result_json = json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            result_json = str(result)
        # 单条过大时裁剪，避免日志库被撑爆
        if len(params_json) > 8000:
            params_json = params_json[:8000] + '…<truncated>'
        if len(result_json) > 8000:
            result_json = result_json[:8000] + '…<truncated>'

        rec = {
            'seq': seq, 'ts': ts, 'tool': tool, 'caller': caller, 'ns': ns,
            'params': params_json, 'result': result_json,
            'ok': bool(ok), 'runtime_ms': int(runtime_ms),
        }

        if self._use_sql:
            try:
                with self._lock:
                    db = self._connect()
                    try:
                        db.execute(
                            "INSERT INTO call_log (seq, ts, tool, caller, ns, "
                            "params_json, result_json, ok, runtime_ms) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (seq, ts, tool, caller, ns, params_json, result_json,
                             1 if ok else 0, int(runtime_ms)))
                        # 超上限裁剪最旧记录
                        if self.max_rows and seq % 500 == 0:
                            db.execute(
                                "DELETE FROM call_log WHERE id <= "
                                "(SELECT MAX(id) - ? FROM call_log)",
                                (self.max_rows,))
                        db.commit()
                    finally:
                        db.close()
                return True
            except Exception:
                pass  # 落库失败 → 继续走内存兜底

        with self._lock:
            self._mem.append(rec)
            if len(self._mem) > _MEM_LIMIT:
                del self._mem[:len(self._mem) - _MEM_LIMIT]
        return False

    # ── 读 ──
    def recent(self, limit: int = 50) -> List[dict]:
        """最近 limit 条记录（新的在前）。"""
        limit = max(1, int(limit or 50))
        if self._use_sql:
            try:
                with self._lock:
                    db = self._connect()
                    try:
                        rows = db.execute(
                            "SELECT seq, ts, tool, caller, ns, params_json, "
                            "result_json, ok, runtime_ms FROM call_log "
                            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
                    finally:
                        db.close()
                out = []
                for (seq, ts, tool, caller, ns, pj, rj, ok, rt) in rows:
                    out.append({
                        'seq': seq, 'ts': ts, 'tool': tool, 'caller': caller,
                        'ns': ns, 'params': pj, 'result': rj,
                        'ok': bool(ok), 'runtime_ms': rt,
                    })
                if out:
                    return out
            except Exception:
                pass
        with self._lock:
            return list(reversed(self._mem[-limit:]))

    def count(self) -> int:
        if self._use_sql:
            try:
                with self._lock:
                    db = self._connect()
                    try:
                        return int(db.execute(
                            "SELECT COUNT(*) FROM call_log").fetchone()[0])
                    finally:
                        db.close()
            except Exception:
                pass
        return len(self._mem)

    def close(self) -> None:
        """兼容旧接口；短连接模式下无常驻资源可释放。"""
        return None


# ── 单例 ──
_store: Optional[CallLogStore] = None
_store_key = None
_store_lock = threading.Lock()


def get_store(meta_dir: Optional[str] = None) -> CallLogStore:
    global _store, _store_key
    key = meta_dir or _default_meta()
    with _store_lock:
        if _store is None or _store_key != key:
            _store = CallLogStore(meta_dir)
            _store_key = key
        return _store


def reset_store() -> None:
    """测试用：丢弃并关闭当前单例。"""
    global _store, _store_key
    with _store_lock:
        if _store is not None:
            _store.close()
        _store = None
        _store_key = None


def write_call_log(tool: str, params: Any = None, result: Any = None,
                   ok: bool = True, runtime_ms: int = 0,
                   caller: str = 'mcp', ns: str = '') -> bool:
    return get_store().write(tool, params=params, result=result, ok=ok,
                             runtime_ms=runtime_ms, caller=caller, ns=ns)


def recent_call_logs(limit: int = 50) -> List[dict]:
    return get_store().recent(limit=limit)


def instrument(tool: str, caller: str = 'mcp', ns: str = ''):
    """上下文管理器：度量耗时并记录一次调用日志（best-effort）。

    用法::

        with instrument('actus_list', caller='mcp') as ctx:
            ...                     # 业务逻辑
            ctx.result = payload
            ctx.ok = True
    """
    return _InstrumentCtx(tool, caller, ns)


class _InstrumentCtx:
    def __init__(self, tool: str, caller: str, ns: str):
        self.tool = tool
        self.caller = caller
        self.ns = ns
        self.params: Any = None
        self.result: Any = None
        self.ok = True
        self._t0 = 0.0

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        runtime_ms = int((time.perf_counter() - self._t0) * 1000)
        if exc_type is not None:
            self.ok = False
            if self.result is None:
                self.result = f'{exc_type.__name__}: {exc}'
        try:
            write_call_log(self.tool, params=self.params, result=self.result,
                           ok=self.ok, runtime_ms=runtime_ms,
                           caller=self.caller, ns=self.ns)
        except Exception:
            pass  # best-effort：绝不因日志失败影响业务
        return False  # 不吞异常
