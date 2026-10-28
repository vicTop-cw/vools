"""omega_strong.py — Omega 强验证（语料驱动的三道关卡）。

对齐兄弟项目 FIST-Mbt 的 `engine/omega_strong.mbt` + `engine/omega_gate.mbt`。
Actus 原先的 Omega（`omega.py`）只做**执行后**的 Ω-gate（产出对 spec 断言）；
本模块补齐 FIST 在**执行前**与**执行外**的两道非 LLM 判据：

    执行前：语料创建者写语料 → 验证者审核 → 通过才放行执行（execute_gate）
    执行后：产出对已审核语料复验 → 通过才放行验收（verify_gate）
    外部判据：[gate:required] 任务须有一条**新鲜且通过**的外部命令检查记录（check gate）

设计原则（三条，与 FIST 一致）：
  1) **默认关闭即现状**：未打 `[omega:required]` 标记的任务，全部放行，行为与既有完全一致。
  2) **语料驱动**：开启后以「已审核语料」为门禁判据，而非自写自测（杜绝自证恒绿）。
  3) **打回有上限、超限必升级**：每类打回最多 max_rounds（默认 3，硬上限 10），
     超限写 escalation + 暂停，转人工裁决（防死循环）。

语料账本落 `_meta/omega_strong/<task_id>.json`（原子写），并落 call_log（caller='omega_strong'）。
"""


import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .paths import meta_dir
from . import calllog
from . import omega as _omega
from .errors import ActionError, ensure_within

__all__ = ['omega_mark', 'gate_mark', 'omega_enabled', 'gate_enabled',
           'omega_max_rounds_default', 'omega_norm_max_rounds',
           'OmegaStrong', 'get_ledger', 'load_ledger', 'ledger_corrupt']

_TZ = timezone(timedelta(hours=8))

#: task_id 白名单：拒绝路径分隔符 / 控制字符 / `..` / 超长（防任意文件读写）。
_TASK_ID_RE = re.compile(r'^[^/\\\x00-\x1f]{1,128}$')
#: 账本/检查记录里允许的时间格式（ISO8601，允许 `Z` 与秒级）。
_LEDGER_LOCK_TIMEOUT = 5.0


def _validate_task_id(task_id: Any) -> str:
    """task_id → 规范化字符串；非法（含路径分隔符/.. 等）抛 param_invalid。"""
    text = '' if task_id is None else str(task_id)
    if (not text or not _TASK_ID_RE.match(text)
            or '..' in text or text in ('.', '..')):
        raise ActionError(
            'param_invalid',
            '非法 task_id: %r（不允许空、路径分隔符、控制字符或 ".."）' % (task_id,))
    return text


def _ledger_dir(meta_dir_arg: Optional[str] = None) -> str:
    return os.path.join(meta_dir_arg or _default_meta(), 'omega_strong')

# 标记（出现在任务/节点描述中即生效）
OMEGA_MARK = '[omega:required]'
GATE_MARK = '[gate:required]'

# 记录类型
T_SPEC = 'spec'          # 执行前语料
T_RESULT = 'result'      # 执行后成果复验
T_CHECK = 'check'        # 外部命令判据
T_ESC = 'escalation'     # 超限升级


def _now_iso() -> str:
    return datetime.now(_TZ).isoformat(timespec='seconds')


def omega_mark() -> str:
    return OMEGA_MARK


def gate_mark() -> str:
    return GATE_MARK


def _as_text(task: Any) -> str:
    """把任务/节点归一为可搜文本：dict 取 goal/description/action_id，否则 str()。"""
    if isinstance(task, dict):
        return ' '.join(str(task.get(k, '')) for k in
                        ('goal', 'description', 'action_id', 'id'))
    return str(task)


def omega_enabled(task: Any) -> bool:
    return OMEGA_MARK in _as_text(task)


def gate_enabled(task: Any) -> bool:
    return GATE_MARK in _as_text(task)


def omega_max_rounds_default() -> int:
    return 3


def omega_norm_max_rounds(v: int) -> int:
    if v is None or v <= 0:
        return omega_max_rounds_default()
    return min(10, v)


def _default_meta() -> str:
    # 路径真源：ACTUS_META_DIR > ACTUS_REPO_ROOT/_meta > __file__ 推导（paths.meta_dir()）
    return meta_dir()


def _ledger_path(task_id: str, meta_dir: Optional[str] = None) -> str:
    """账本文件路径（**防路径逃逸**）。

    审计修复（P1 任意文件读写）：改前 `task_id` 直接拼进文件名 ——
    `task_id='../../escaped'` 能把账本写到 `_meta/omega_strong/../../escaped.json`，
    绝对 `task_id` 更能无视 ACTUS_META_DIR 写到任意 `<abs>.json`（load 侧同样可读）。
    task_id 来自 CLI/MCP 入参，属于不可信输入。现在：白名单挡住分隔符/`..`，
    再用 `errors.ensure_within` 的 realpath 包含性检查兜底（与团队名/公钥路径同一把尺子）。
    """
    tid = _validate_task_id(task_id)
    base = _ledger_dir(meta_dir)
    try:
        return ensure_within(base, os.path.join(base, tid + '.json'),
                             what='omega 账本路径')
    except ValueError as exc:
        raise ActionError('param_invalid', '非法 omega 账本路径: %s' % exc)


def ledger_corrupt() -> bool:
    """上次 `load_ledger` 是否遇到损坏账本（诊断用；损坏的已备份为 `.corrupt-*`）。"""
    return bool(_load_ledger_state.get('corrupt'))


#: `load_ledger` 的损坏状态（进程内诊断；写侧据此拒绝覆盖）
_load_ledger_state: Dict[str, Any] = {'corrupt': False, 'path': None}


def load_ledger(task_id: str, meta_dir: Optional[str] = None,
                repair: bool = False) -> Dict[str, Any]:
    """读账本。缺失 → 空账本；损坏 → 返回带 corrupt 标记的空账本。

    `repair=False`（默认，第 14 轮审计修复）：**只读**，不把损坏账本改名备份
    （旧实现 `load_` 会在读路径 `os.replace` 改用户数据目录，只读 FS 直接失败）。
    写路径调用方（`_append`/`_update_status`）显式传 `repair=True` 保留备份语义。

    审计修复（P2 静默清空）：改前 `except Exception` 直接返回空账本 —— 损坏文件
    被当成"没有记录"，下一次 `_append` 落盘就把原历史（可能是 approved 语料/
    复验记录）覆盖掉。现在损坏时先把原文件改名留证，并让写路径 fail-closed。
    """
    tid = _validate_task_id(task_id)
    path = _ledger_path(tid, meta_dir)
    empty = {'task_id': tid, 'records': [], 'max_rounds': omega_max_rounds_default()}
    existing_backup = _find_corrupt_backup(path)
    if not os.path.isfile(path):
        if existing_backup:
            # 之前检测到损坏并改名备份过 → 状态**粘住**：写侧继续拒绝，直到人工处理
            broken = dict(empty)
            broken.update({'corrupt': True, 'corrupt_backup': existing_backup,
                           'corrupt_reason': '原账本损坏已备份，等待人工确认'
                                             '（删除 .corrupt-* 备份后才会允许重写）'})
            _load_ledger_state.update({'corrupt': True, 'path': path})
            return broken
        return empty
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError('账本顶层不是对象: %s' % type(data).__name__)
    except (OSError, ValueError) as exc:
        backup = None
        if repair:
            backup = '%s.corrupt-%d' % (path, int(time.time()))
            try:
                os.replace(path, backup)
            except OSError:
                backup = None
        _load_ledger_state.update({'corrupt': True, 'path': path})
        broken = dict(empty)
        broken.update({'corrupt': True, 'corrupt_backup': backup,
                       'corrupt_reason': '%s: %s%s' % (
                           type(exc).__name__, exc,
                           '' if repair else '（repair=False：未自动备份，只读返回）')})
        return broken
    data.setdefault('task_id', tid)
    data.setdefault('records', [])
    data.setdefault('max_rounds', omega_max_rounds_default())
    _load_ledger_state.update({'corrupt': False, 'path': path})
    return data


def _find_corrupt_backup(path: str) -> Optional[str]:
    """是否存在该账本的 `.corrupt-*` 备份（损坏状态的粘性标记）。"""
    directory = os.path.dirname(path)
    prefix = os.path.basename(path) + '.corrupt-'
    if not os.path.isdir(directory):
        return None
    backups = [os.path.join(directory, name) for name in os.listdir(directory)
               if name.startswith(prefix)]
    return sorted(backups)[-1] if backups else None


def _save_ledger(data: Dict[str, Any], meta_dir: Optional[str] = None) -> str:
    """写账本（原子替换）。**损坏状态禁止覆盖**：先把历史备份/修好再写。

    并发修复（第 10 轮实测）：改前 tmp 名固定为 `path + '.tmp'` —— 同一进程内
    多线程并发写时（即使有文件锁）Windows 上偶发 `os.replace` WinError 5
    （拒绝访问），20 线程压测 5 轮出现 1 次。现在：
      * 每次写入用**唯一**临时文件名（tempfile.mkstemp，同目录保证同盘）；
      * `os.replace` 对 Windows 瞬时占用做有限重试；
      * 失败时清理临时文件。
    """
    if data.get('corrupt'):
        raise ActionError(
            'internal',
            '账本已损坏（原文件已备份为 .corrupt-*），拒绝写入以免覆盖历史；'
            '请先人工检查/修复该账本')
    path = _ledger_path(data['task_id'], meta_dir)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.ledger-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        last_error = None
        for attempt in range(20):        # Windows 上目标被瞬时占用 → 短暂重试
            try:
                os.replace(tmp, path)
                return path
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.01 * (attempt + 1))
        raise last_error
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


#: 进程内按账本路径的线程锁（文件锁只保证跨进程；同进程多线程用 threading.Lock
#: 更可靠 —— 本轮 20 线程压测正是在同进程内撞上 os.replace 竞争）。
_PROCESS_LOCKS: Dict[str, Any] = {}
_PROCESS_LOCKS_GUARD = None


def _thread_lock_for(path: str):
    global _PROCESS_LOCKS_GUARD
    if _PROCESS_LOCKS_GUARD is None:
        _PROCESS_LOCKS_GUARD = threading.Lock()
    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(path)
        if lock is None:
            lock = threading.RLock()
            _PROCESS_LOCKS[path] = lock
    return lock


@contextmanager
def _ledger_lock(path: str):
    """账本读改写互斥锁（跨进程；Windows 用 msvcrt，POSIX 用 fcntl）。

    审计修复（P2 并发丢更新）：改前 `_append`/`_update_status` 是裸的
    read-modify-write —— 两个实例各自 load→append→save，后写者会把先写者的
    记录整个覆盖掉（实测 A 的记录消失）。这里用 `path + '.lock'` 上的排他锁
    串行化整段读改写。
    """
    lock_path = path + '.lock'
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    # 进程内线程锁优先（文件锁的跨进程语义在"同一进程多线程"下不可靠 ——
    # 本轮 20 线程压测撞到 os.replace 竞争，故双层加锁：线程锁 + 文件锁）。
    thread_lock = _thread_lock_for(path)
    if not thread_lock.acquire(timeout=_LEDGER_LOCK_TIMEOUT):
        raise ActionError('internal', 'omega 账本被本进程其它线程占用，获取锁超时: %s'
                          % path)
    handle = open(lock_path, 'a+b')
    acquired = False
    try:
        deadline = time.time() + _LEDGER_LOCK_TIMEOUT
        if os.name == 'nt':
            import msvcrt
            while not acquired:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                except OSError:
                    if time.time() >= deadline:
                        raise ActionError('internal', 'omega 账本被占用，获取锁超时: %s'
                                          % path)
                    time.sleep(0.05)
        else:
            import fcntl
            while not acquired:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError:
                    if time.time() >= deadline:
                        raise ActionError('internal', 'omega 账本被占用，获取锁超时: %s'
                                          % path)
                    time.sleep(0.05)
        yield
    finally:
        if acquired:
            try:
                if os.name == 'nt':
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()
        thread_lock.release()


def _deliverable_digest(deliverable: Any) -> Dict[str, Any]:
    """交付物指纹：类型 + 大小 + sha256（dict/list 先规范化 JSON）。

    审计修复（P2 复验不可追溯）：`result_verify` 改前只判 `deliverable is not None`，
    且交付物**不进记录** —— 空 `{}` 也能"通过"，事后无法证明验的是哪份产物。
    这里给记录留下可核对的指纹（不存原文，避免把密钥/大对象写进账本）。
    """
    import hashlib
    if isinstance(deliverable, (dict, list)):
        payload = json.dumps(deliverable, ensure_ascii=False, sort_keys=True,
                             default=str).encode('utf-8')
        kind = 'dict' if isinstance(deliverable, dict) else 'list'
    elif isinstance(deliverable, bytes):
        payload = deliverable
        kind = 'bytes'
    else:
        payload = str(deliverable).encode('utf-8')
        kind = type(deliverable).__name__
    return {'type': kind, 'size': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest()}


def _parse_iso(value: Any) -> Optional[datetime]:
    """ISO8601 字符串 → datetime（带时区则保留；解析失败返回 None）。"""
    if not value:
        return None
    text = str(value).strip().replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _log(tool: str, ok: bool, params: dict, result: dict,
         runtime_ms: int, ns: str) -> None:
    try:
        calllog.write_call_log(tool, params=params, result=result, ok=ok,
                               runtime_ms=runtime_ms, caller='omega_strong',
                               ns=ns)
    except Exception:  # noqa: BLE001
        pass


class OmegaStrong:
    """单任务的 Omega 强验证控制器（语料驱动）。"""

    def __init__(self, task_id: str, meta_dir: Optional[str] = None,
                 max_rounds: int = 0):
        self.task_id = task_id
        self.meta_dir = meta_dir
        self.max_rounds = omega_norm_max_rounds(max_rounds)

    # ── 账本原语 ──
    def _load(self, repair: bool = False) -> Dict[str, Any]:
        return load_ledger(self.task_id, self.meta_dir, repair=repair)

    def _save(self, data: Dict[str, Any]) -> str:
        return _save_ledger(data, self.meta_dir)

    def records(self, spec_type: Optional[str] = None) -> List[Dict[str, Any]]:
        recs = self._load()['records']
        if spec_type is None:
            return list(recs)
        return [r for r in recs if r.get('spec_type') == spec_type]

    def _count(self, spec_type: str, status: Optional[str] = None) -> int:
        recs = self.records(spec_type)
        if status is None:
            return len(recs)
        return sum(1 for r in recs if r.get('status') == status)

    def latest(self, spec_type: str) -> Optional[Dict[str, Any]]:
        recs = self.records(spec_type)
        if not recs:
            return None
        # created_at 优先，其次 id 字典序（跨后端确定性）
        return sorted(recs, key=lambda r: (r.get('created_at', ''),
                                           r.get('id', '')))[-1]

    def _append(self, rec: Dict[str, Any]) -> None:
        # 读改写整段加锁：防并发丢更新（两个进程各自 load→append→save 会互相覆盖）
        with _ledger_lock(_ledger_path(self.task_id, self.meta_dir)):
            data = self._load(repair=True)      # 写路径保留损坏备份语义
            data['max_rounds'] = self.max_rounds
            # 同 id 覆盖（upsert 语义）
            data['records'] = [r for r in data['records']
                               if r.get('id') != rec['id']] + [rec]
            self._save(data)

    def _update_status(self, rec_id: str, status: str,
                       content: Optional[str] = None) -> None:
        with _ledger_lock(_ledger_path(self.task_id, self.meta_dir)):
            data = self._load(repair=True)      # 写路径保留损坏备份语义
            for r in data['records']:
                if r.get('id') == rec_id:
                    r['status'] = status
                    r['updated_at'] = _now_iso()
                    if content is not None:
                        r['content'] = content
            self._save(data)

    # ── 第一环：语料创建（执行前） ──
    def spec_create(self, author: str, content: Any,
                    spec: Optional[dict] = None) -> Dict[str, Any]:
        """语料创建者写语料。content 为文本或 JSON spec。

        若给出 spec（dict），用 `omega.validate_spec` 做结构校验（不通过即拒绝）。
        """
        t0 = time.perf_counter()
        if not str(author).strip():
            raise ActionError('param_invalid', '语料作者不可为空')
        if spec is not None:
            ok, errs = _omega.validate_spec(spec)
            if not ok:
                raise ActionError('param_invalid',
                                  f'语料 spec 结构非法: {errs}', {'errors': errs})
        if isinstance(content, (dict, list)):
            payload = json.dumps(content, ensure_ascii=False)
        else:
            payload = str(content or '')
        if not payload.strip():
            raise ActionError('param_invalid', '语料内容不可为空')

        cur = self.latest(T_SPEC)
        if cur and cur.get('status') == 'pending':
            raise ActionError('internal',
                              f'已存在待审核语料 [{cur["id"]}]，请先审核')
        if cur and cur.get('status') == 'approved':
            raise ActionError('internal',
                              f'语料 [{cur["id"]}] 已通过审核，无需重复创建')

        rejected = self._count(T_SPEC, 'rejected')
        if rejected >= self.max_rounds:
            return self._escalate(T_SPEC, rejected, '语料连续打回达上限')

        rnd = self._count(T_SPEC) + 1
        sid = f'spec:{self.task_id}:r{rnd}'
        rec = {'id': sid, 'task_id': self.task_id, 'spec_type': T_SPEC,
               'content': payload, 'spec': spec, 'status': 'pending',
               'author': author, 'created_at': _now_iso(),
               'updated_at': _now_iso()}
        self._append(rec)
        out = {'ok': True, 'stage': T_SPEC, 'spec_id': sid,
               'task_id': self.task_id, 'round': rnd, 'status': 'pending',
               'author': author, 'max_rounds': self.max_rounds,
               'rounds_rejected': rejected, 'next_action': 'omega_spec_review',
               'escalated': False}
        _log('omega.spec_create', True, {'task_id': self.task_id},
             {'spec_id': sid, 'status': 'pending'},
             int((time.perf_counter() - t0) * 1000), self.task_id)
        return out

    # ── 第二环：语料审核（可打回） ──
    def spec_review(self, reviewer: str, verdict: str,
                    reason: str = '') -> Dict[str, Any]:
        t0 = time.perf_counter()
        if not str(reviewer).strip():
            raise ActionError('param_invalid', '审核者不可为空')
        cur = self.latest(T_SPEC)
        if cur is None:
            raise ActionError('internal', '尚无语料，请先创建语料')
        if cur.get('status') != 'pending':
            raise ActionError('internal',
                              f'语料 [{cur["id"]}] 当前状态为 [{cur["status"]}]，'
                              f'不是待审核状态')
        if cur.get('author') and cur['author'] == reviewer:
            raise ActionError('internal',
                              f'验证者不可审核自己创建的语料（author = reviewer '
                              f'= {reviewer}）')
        approve = str(verdict).lower() in ('approve', 'approved', 'pass', 'ok')
        if approve:
            self._update_status(cur['id'], 'approved')
            out = {'ok': True, 'stage': T_SPEC, 'verdict': 'approved',
                   'spec_id': cur['id'], 'task_id': self.task_id,
                   'reviewer': reviewer, 'reason': reason,
                   'next_action': 'execute', 'escalated': False}
            _log('omega.spec_review', True, {'task_id': self.task_id},
                 {'spec_id': cur['id'], 'verdict': 'approved'},
                 int((time.perf_counter() - t0) * 1000), self.task_id)
            return out
        rejected = self._count(T_SPEC, 'rejected') + 1
        if rejected > self.max_rounds:
            return self._escalate(T_SPEC, rejected, reason)
        self._update_status(cur['id'], 'rejected')
        _note_lesson(self.task_id, 'omega.spec_rejected',
                     reason or '语料被打回（未附原因）')
        out = {'ok': True, 'stage': T_SPEC, 'verdict': 'rejected',
               'spec_id': cur['id'], 'task_id': self.task_id,
               'reviewer': reviewer, 'reason': reason,
               'rounds_rejected': rejected, 'max_rounds': self.max_rounds,
               'next_action': 'omega_spec_create', 'escalated': False}
        _log('omega.spec_review', False, {'task_id': self.task_id},
             {'spec_id': cur['id'], 'verdict': 'rejected'},
             int((time.perf_counter() - t0) * 1000), self.task_id)
        return out

    # ── 第三环：成果复验（可打回） ──
    def result_verify(self, reviewer: str, verdict: str, reason: str = '',
                      deliverable: Any = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        if not str(reviewer).strip():
            raise ActionError('param_invalid', '复验者不可为空')
        spec = self.latest(T_SPEC)
        if spec is None:
            raise ActionError('internal', '强验证任务尚无执行前语料，不可复验成果')
        if spec.get('status') != 'approved':
            raise ActionError('internal',
                              f'执行前语料 [{spec["id"]}] 未通过审核'
                              f'（[{spec["status"]}]），不可进入成果复验')
        if deliverable is None:
            raise ActionError('internal', '尚无交付物，无可复验成果')

        rnd = self._count(T_RESULT) + 1
        rid = f'result:{self.task_id}:r{rnd}'
        passed = str(verdict).lower() in ('pass', 'approved', 'approve', 'ok')
        # 交付物指纹（审计修复 P2）：改前 deliverable 只判 `not None`，且**不进记录** ——
        # 空 dict 也能"复验通过"，事后无法证明验的是哪个交付物。现在记录类型/大小/sha256。
        deliverable_digest = _deliverable_digest(deliverable)
        # 若语料带 spec 且 deliverable 为 dict → 顺带跑一次 Ω-gate，作为客观佐证
        gate = None
        if passed and isinstance(deliverable, dict) and spec.get('spec'):
            try:
                gate = _omega.run_gate(spec['spec'], deliverable)
            except Exception:  # noqa: BLE001
                gate = None
        rec = {'id': rid, 'task_id': self.task_id, 'spec_type': T_RESULT,
               'content': json.dumps({'reviewer': reviewer, 'verdict': verdict,
                                      'reason': reason,
                                      'deliverable': deliverable_digest,
                                      'gate': gate}, ensure_ascii=False),
               'status': 'approved' if passed else 'rejected',
               'author': reviewer, 'created_at': _now_iso(),
               'updated_at': _now_iso()}
        if passed:
            self._append(rec)
            out = {'ok': True, 'stage': T_RESULT, 'result_id': rid,
                   'task_id': self.task_id, 'round': rnd,
                   'status': 'approved', 'reviewer': reviewer, 'reason': reason,
                   'deliverable': deliverable_digest,
                   'gate': gate, 'next_action': 'verify', 'escalated': False}
            _log('omega.result_verify', True, {'task_id': self.task_id},
                 {'result_id': rid, 'status': 'approved'},
                 int((time.perf_counter() - t0) * 1000), self.task_id)
            return out
        rejected = self._count(T_RESULT, 'rejected') + 1
        if rejected > self.max_rounds:
            return self._escalate(T_RESULT, rejected, reason)
        self._append(rec)
        _note_lesson(self.task_id, 'omega.result_rejected',
                     reason or '成果复验未达标（未附原因）')
        out = {'ok': True, 'stage': T_RESULT, 'verdict': 'rejected',
               'result_id': rid, 'task_id': self.task_id, 'reviewer': reviewer,
               'reason': reason, 'rounds_rejected': rejected,
               'max_rounds': self.max_rounds,
               'next_action': 'execute', 'escalated': False}
        _log('omega.result_verify', False, {'task_id': self.task_id},
             {'result_id': rid, 'status': 'rejected'},
             int((time.perf_counter() - t0) * 1000), self.task_id)
        return out

    # ── 外部命令判据（[gate:required]） ──
    def record_check(self, check: dict) -> Dict[str, Any]:
        """**写账本**：记录一次外部命令检查结果（`check_` 前缀易误认为只读，
        第 14 轮改名 `record_check`；旧名 `check_record` 保留为 deprecated 别名）。

        审计修复（P2 假通过）：改前门禁状态由调用方传入的 `check['ok']` 直接决定 ——
        实测 `check_record({'ok': True})` 就能记成 `passed` 并让 `check_gate` 放行，
        记录里连 `cmd`/`exit_code` 都没有（"不跑命令即过门禁"）。现在：
          * 必须提供非空 `cmd` 与整数 `exit_code`（否则 param_invalid）；
          * 门禁状态**只由 `exit_code == 0` 推导**，`ok`/`status` 一律忽略。
        """
        t0 = time.perf_counter()
        if not isinstance(check, dict):
            raise ActionError('param_invalid', 'check 必须是对象（含 cmd / exit_code）')
        cmd = check.get('cmd')
        if not isinstance(cmd, str) or not cmd.strip():
            raise ActionError('param_invalid',
                              "check 缺少非空 cmd（门禁判据必须是一次真实命令）")
        exit_code = check.get('exit_code')
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise ActionError('param_invalid',
                              'check 缺少整数 exit_code（门禁状态只由 exit_code 推导）')
        eff = 'passed' if exit_code == 0 else 'failed'
        record_payload = {k: v for k, v in check.items()
                          if k not in ('ok', 'status')}
        record_payload['exit_code'] = exit_code
        rnd = self._count(T_CHECK) + 1
        cid = f'check:{self.task_id}:r{rnd}'
        self._append({'id': cid, 'task_id': self.task_id, 'spec_type': T_CHECK,
                      'content': json.dumps(record_payload, ensure_ascii=False,
                                            default=str),
                      'status': eff, 'author': 'run_check',
                      'created_at': _now_iso(), 'updated_at': _now_iso()})
        _log('omega.check_record', eff == 'passed', {'task_id': self.task_id},
             {'check_id': cid, 'status': eff, 'exit_code': exit_code},
             int((time.perf_counter() - t0) * 1000), self.task_id)
        return {'ok': True, 'check_id': cid, 'task_id': self.task_id,
                'round': rnd, 'status': eff, 'exit_code': exit_code, 'cmd': cmd}

    def check_record(self, check: dict) -> Dict[str, Any]:
        """Deprecated 别名（第 14 轮）：语义是**写账本**，请用 `record_check`。"""
        return self.record_check(check)

    # ── 门禁 ──
    def execute_gate(self, task: Any = None) -> Tuple[bool, str]:
        """执行前门禁：[omega:required] 任务须有已通过语料。未标记直接放行。"""
        if task is not None and not omega_enabled(task):
            return True, 'disabled'
        cur = self.latest(T_SPEC)
        if cur is None:
            return False, 'omega_execute_gate: 尚未创建语料'
        if cur.get('status') != 'approved':
            return False, (f'omega_execute_gate: 语料 [{cur["id"]}] 状态为 '
                           f'[{cur["status"]}]，未通过审核前禁止执行')
        return True, 'approved'

    def verify_gate(self, task: Any = None) -> Tuple[bool, str]:
        """验收前门禁：[omega:required] 任务须有已通过的成果复验。未标记放行。"""
        if task is not None and not omega_enabled(task):
            return True, 'disabled'
        cur = self.latest(T_RESULT)
        if cur is None:
            return False, 'omega_verify_gate: 尚未做成果复验'
        if cur.get('status') != 'approved':
            return False, (f'omega_verify_gate: 成果复验 [{cur["id"]}] 状态为 '
                           f'[{cur["status"]}]，未通过前禁止验收')
        return True, 'approved'

    def check_gate(self, task: Any = None,
                   task_updated_at: Optional[str] = None) -> Tuple[bool, str]:
        """外部判据门禁：[gate:required] 任务须有**新鲜且通过**的 check 记录。"""
        if task is not None and not gate_enabled(task):
            return True, 'disabled'
        cur = self.latest(T_CHECK)
        if cur is None:
            return False, ('gate: 任务带 [gate:required]，但尚无外部检查记录，'
                           '请先执行 run_check')
        if cur.get('status') != 'passed':
            return False, (f'gate: 最新外部检查 [{cur["id"]}] 状态为 '
                           f'[{cur["status"]}]，未通过前禁止验收')
        if task_updated_at:
            # 审计修复（P3）：改前直接按字符串比 `created_at < task_updated_at`，
            # 两边格式/时区不一致（`Z` vs `+08:00`、带/不带秒）就会误判"过期/新鲜"。
            # 现在优先解析成 datetime 比较；解析失败才退回字符串比较。
            created_raw = cur.get('created_at', '')
            created_dt = _parse_iso(created_raw)
            updated_dt = _parse_iso(task_updated_at)
            stale = None
            if created_dt is not None and updated_dt is not None:
                try:
                    stale = created_dt < updated_dt
                except TypeError:      # 一边带 tz 一边不带 → 退化为字符串比较
                    stale = str(created_raw) < str(task_updated_at)
            else:
                stale = str(created_raw) < str(task_updated_at)
            if stale:
                return False, (f'gate: 检查记录 [{cur["id"]}]（{created_raw}）'
                               f'早于任务最后更新（{task_updated_at}），代码可能已变更，'
                               f'请重新执行 run_check')
        return True, 'fresh_passed'

    # ── 超限升级 ──
    def _escalate(self, stage: str, rounds: int, reason: str) -> Dict[str, Any]:
        esc_id = f'escalation:{self.task_id}:{stage}:r{rounds}'
        self._append({'id': esc_id, 'task_id': self.task_id,
                      'spec_type': T_ESC,
                      'content': json.dumps({'stage': stage, 'rounds': rounds,
                                             'max_rounds': self.max_rounds,
                                             'needs_human_review': True,
                                             'reason': reason},
                                            ensure_ascii=False),
                      'status': 'escalated', 'author': 'system',
                      'created_at': _now_iso(), 'updated_at': _now_iso()})
        _note_lesson(self.task_id, 'omega.escalated',
                     reason or '打回超限升级人工（未附原因）')
        _log('omega.escalate', False, {'task_id': self.task_id, 'stage': stage},
             {'escalation_id': esc_id, 'needs_human_review': True}, 0,
             self.task_id)
        return {'ok': True, 'stage': stage, 'verdict': 'escalated',
                'escalation_id': esc_id, 'task_id': self.task_id,
                'rounds_rejected': rounds, 'max_rounds': self.max_rounds,
                'reason': reason, 'needs_human_review': True,
                'task_paused': True, 'next_action': 'human_review',
                'escalated': True}

    # ── 状态 ──
    def status(self) -> Dict[str, Any]:
        spec = self.latest(T_SPEC)
        result = self.latest(T_RESULT)
        check = self.latest(T_CHECK)
        return {
            'ok': True, 'task_id': self.task_id,
            'max_rounds': self.max_rounds,
            'spec_rounds': self._count(T_SPEC),
            'spec_rejected': self._count(T_SPEC, 'rejected'),
            'result_rejected': self._count(T_RESULT, 'rejected'),
            'spec_status': spec['status'] if spec else 'none',
            'result_status': result['status'] if result else 'none',
            'check_status': check['status'] if check else 'none',
            'escalated': self._count(T_ESC, 'escalated') > 0,
            'records': self.records(),
        }


# ── 便捷入口 ──

def get_ledger(task_id: str, meta_dir: Optional[str] = None,
               max_rounds: int = 0) -> OmegaStrong:
    return OmegaStrong(task_id, meta_dir=meta_dir, max_rounds=max_rounds)


def _note_lesson(task_id: str, kind: str, reason: str) -> None:
    """失败回流：把打回/升级沉淀为教训（谐调 bugreport，best-effort）。"""
    try:
        meta = _default_meta()
        d = os.path.join(meta, 'omega_strong')
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, 'lessons.jsonl')
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'ts': _now_iso(), 'task_id': task_id,
                                'kind': kind, 'reason': reason},
                               ensure_ascii=False) + '\n')
    except Exception:  # noqa: BLE001
        pass
