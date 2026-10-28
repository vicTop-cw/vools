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
from .paths import meta_dir

__all__ = [
    'CallLogStore', 'get_store', 'write_call_log', 'recent_call_logs',
    'instrument', 'log_path', 'reset_store',
    'write_action_metric', 'aggregate_metrics', 'popular_actions',
    'trending_actions', 'metrics_path',
]

_TZ = timezone(timedelta(hours=8))

_DDL = (
    "CREATE TABLE IF NOT EXISTS call_log ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, seq INTEGER, ts TEXT, tool TEXT, "
    "caller TEXT, ns TEXT, params_json TEXT, result_json TEXT, ok INTEGER, "
    "runtime_ms INTEGER)"
)

# action_metrics 表（docs/03 §5.1 使用量指标）：
# 每次动作执行一行（action_id/ts/caller/ok/runtime_ms），
# aggregate_metrics 聚合出 popular/trending——Quicker 的杀手指标
# （"7日日均用量 + 总使用量"区分「安装了」vs「真正在用」）。
_METRICS_DDL = (
    "CREATE TABLE IF NOT EXISTS action_metrics ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, action_id TEXT, ts TEXT, "
    "caller TEXT, ok INTEGER, runtime_ms INTEGER)"
)

# 进程内单调序号（多实例并发时由 DB 侧 max(seq) 校正）
_seq_lock = threading.Lock()
_seq_counter = 0
_MEM_LIMIT = 500
_DEFAULT_MAX_ROWS = 20000


def _now_iso() -> str:
    return datetime.now(_TZ).isoformat(timespec='seconds')


def _default_meta() -> str:
    """指标/call_log 的默认落盘目录。

    优先级（docs/03 §4.1）：
      1. ACTUS_METRICS_DIR：显式指标目录（生产部署用；安装态 site-packages/_meta
         可能只读，共享安装下统计会静默丢失——这个环境变量就是逃生门）；
      2. ACTUS_REPO_ROOT/_meta：仓库态；
      3. 模块上三级/_meta：安装态兜底（best-effort 写失败不抛）。
    """
    metrics_dir = os.environ.get('ACTUS_METRICS_DIR')
    if metrics_dir:
        return metrics_dir
    # 方案 A（专用逃生门优先于通用）：
    #   ACTUS_METRICS_DIR > ACTUS_META_DIR > ACTUS_REPO_ROOT/_meta > __file__ 推导
    # 后三级由 paths.meta_dir() 一处解析。
    return meta_dir()


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


# ═══════════════════════════════════════════════════════════════
# 使用量指标（docs/03 §5.1）：执行计数 → 聚合 → popular/trending
# ═══════════════════════════════════════════════════════════════
# 与 call_log 同库（_meta/call_log.db），独立表 action_metrics。
# 复用短连接 + best-effort 模式：写指标失败不影响执行，绝不影响原返回值。

def metrics_path(meta_dir: Optional[str] = None) -> str:
    """指标数据库路径（缺省与 call_log 同库）。"""
    return log_path(meta_dir)


def _metrics_connect(meta_dir: Optional[str] = None):
    """action_metrics 表的短连接（用完即关，复用 call_log 连接模式）。"""
    path = metrics_path(meta_dir)
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False, timeout=5)
    db.execute(_METRICS_DDL)
    return db


def write_action_metric(action_id: str, ok: bool = True,
                        runtime_ms: int = 0, caller: str = '',
                        meta_dir: Optional[str] = None) -> bool:
    """追加一行动作执行指标。best-effort：失败返回 False，不抛出。

    执行计数（非安装计数）——Quicker 经验：只有执行计数才能区分
    「安装了」vs「真正在用」（docs/03 §5.1）。
    """
    if not action_id:
        return False
    try:
        db = _metrics_connect(meta_dir)
        try:
            db.execute(
                "INSERT INTO action_metrics (action_id, ts, caller, ok, runtime_ms) "
                "VALUES (?, ?, ?, ?, ?)",
                (action_id, _now_iso(), caller or '', 1 if ok else 0,
                 int(runtime_ms)))
            db.commit()
        finally:
            db.close()
        return True
    except Exception:
        return False


def _metrics_exclusions(exclude_callers: List[str]):
    """自指排除 SQL 片段：剔除 caller 命中名单的行（无名单 → 不过滤）。

    V-08（寻虫 2026-10-22）：quality_scale 自身执行时也会经 executor 落
    一条 metrics（caller='executor'），当它给自己算质量时把这条当真实使用
    就虚报 exec_count。调用方传质量计算的调用者名单（quality/mcp 通道）
    剔除之。
    """
    if not exclude_callers:
        return '', []
    placeholders = ', '.join('?' for _ in exclude_callers)
    return f'AND caller NOT IN ({placeholders})', list(exclude_callers)


def aggregate_metrics(action_id: str, meta_dir: Optional[str] = None,
                      exclude_callers: List[str] = None) -> dict:
    """聚合单动作执行指标（docs/03 §5.1）。

    exclude_callers: 从聚合里剔除的 caller 名单（自指排除接线）。

    V-22（寻虫 2026-10-22，candidate）：ts 窗口比较是字典序字符串比较，
    正确性完全依赖"所有写入方都用 _now_iso()（+08:00、timespec=seconds
    定长 iso）"。当前仓内无混写方（全部经 _now_iso），字典序=时间序。
    若未来混入 +00:00 或其它偏移的行，同日时间戳会失真（跨偏移即错）。
    彻底修复需改存 epoch 秒或统一 UTC Z 格式（影响数据兼容性），
    留待数据迁移窗口。

    Returns:
        {total, last_7d, last_30d, success_rate, avg_runtime_ms, unique_callers}
        无记录时全部为 0（不伪造数据）。
    """
    out = {
        'total': 0, 'last_7d': 0, 'last_30d': 0,
        'success_rate': 0.0, 'avg_runtime_ms': 0, 'unique_callers': 0,
    }
    excl_clause, excl_params = _metrics_exclusions(exclude_callers)
    try:
        db = _metrics_connect(meta_dir)
        try:
            now = datetime.now(_TZ)
            d7 = (now - timedelta(days=7)).isoformat(timespec='seconds')
            d30 = (now - timedelta(days=30)).isoformat(timespec='seconds')

            row = db.execute(
                f"SELECT COUNT(*), AVG(ok), AVG(runtime_ms), "
                f"COUNT(DISTINCT caller) FROM action_metrics "
                f"WHERE action_id = ? {excl_clause}",
                (action_id, *excl_params)).fetchone()
            if row and row[0]:
                total = int(row[0])
                out['total'] = total
                out['success_rate'] = round(float(row[1] or 0), 4)
                out['avg_runtime_ms'] = int(row[2] or 0)
                out['unique_callers'] = int(row[3] or 0)

            for key, cutoff in (('last_7d', d7), ('last_30d', d30)):
                r = db.execute(
                    f"SELECT COUNT(*) FROM action_metrics "
                    f"WHERE action_id = ? AND ts >= ? {excl_clause}",
                    (action_id, cutoff, *excl_params)).fetchone()
                out[key] = int(r[0]) if r and r[0] else 0
        finally:
            db.close()
    except Exception:
        pass  # best-effort：查询失败返回零值，不抛出
    return out


def popular_actions(limit: int = 10, period_days: int = 30,
                    meta_dir: Optional[str] = None,
                    exclude_callers: List[str] = None) -> List[dict]:
    """按执行计数 top-N（docs/03 §5.1 popular）。

    Returns:
        [{action_id, count, success_rate}] 按计数降序。
    """
    limit = max(1, int(limit or 10))
    out: List[dict] = []
    excl_clause, excl_params = _metrics_exclusions(exclude_callers)
    try:
        db = _metrics_connect(meta_dir)
        try:
            cutoff = (datetime.now(_TZ) - timedelta(days=period_days)).isoformat(
                timespec='seconds')
            rows = db.execute(
                f"SELECT action_id, COUNT(*) AS c, AVG(ok) AS sr "
                f"FROM action_metrics WHERE ts >= ? {excl_clause} "
                f"GROUP BY action_id ORDER BY c DESC LIMIT ?",
                (cutoff, *excl_params, limit)).fetchall()
            for (aid, c, sr) in rows:
                out.append({'action_id': aid, 'count': int(c),
                            'success_rate': round(float(sr or 0), 4)})
        finally:
            db.close()
    except Exception:
        pass
    return out


def trending_actions(limit: int = 10, meta_dir: Optional[str] = None,
                     exclude_callers: List[str] = None) -> List[dict]:
    """按 7 日相对 30 日增长率排序（docs/03 §5.1 trending）。

    增长率 = (last_7d / 7) / (last_30d / 30)，近 7 日占比越高越"热"。

    V-21（寻虫 2026-10-22）：原实现每命中一个 action_id 就调
    aggregate_metrics 一次（N+1：短连接×4 SQL×动作数）。改为单条
    GROUP BY + CASE WHEN 窗口（1 条 SQL、一次连接）。
    """
    limit = max(1, int(limit or 10))
    excl_clause, excl_params = _metrics_exclusions(exclude_callers)
    try:
        db = _metrics_connect(meta_dir)
        try:
            now = datetime.now(_TZ)
            d30 = (now - timedelta(days=30)).isoformat(timespec='seconds')
            d7 = (now - timedelta(days=7)).isoformat(timespec='seconds')

            # 一次聚合取齐 30d 计数与 7d 计数（CASE WHEN 窗口，同一条 SQL）
            rows = db.execute(
                f"SELECT action_id, COUNT(*) AS c30, "
                f"SUM(CASE WHEN ts >= ? THEN 1 ELSE 0 END) AS c7 "
                f"FROM action_metrics WHERE ts >= ? {excl_clause} "
                f"GROUP BY action_id",
                (d7, d30, *excl_params)).fetchall()
        finally:
            db.close()
        scored: List[dict] = []
        for (aid, c30, c7) in rows:
            c30 = int(c30 or 0)
            c7 = int(c7 or 0)
            daily30 = c30 / 30.0
            daily7 = c7 / 7.0
            growth = (daily7 / daily30) if daily30 > 0 else (2.0 if daily7 > 0 else 0.0)
            scored.append({'action_id': aid, 'count_30d': c30, 'count_7d': c7,
                           'growth': round(growth, 3)})
        scored.sort(key=lambda r: (-r['growth'], -r['count_7d']))
        return scored[:limit]
    except Exception:
        return []
