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
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .paths import meta_dir
from . import calllog
from . import omega as _omega
from .errors import ActionError

__all__ = ['omega_mark', 'gate_mark', 'omega_enabled', 'gate_enabled',
           'omega_max_rounds_default', 'omega_norm_max_rounds',
           'OmegaStrong', 'get_ledger', 'load_ledger']

_TZ = timezone(timedelta(hours=8))

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
    return os.path.join(meta_dir or _default_meta(), 'omega_strong',
                        f'{task_id}.json')


def load_ledger(task_id: str, meta_dir: Optional[str] = None) -> Dict[str, Any]:
    path = _ledger_path(task_id, meta_dir)
    if not os.path.isfile(path):
        return {'task_id': task_id, 'records': [], 'max_rounds':
                omega_max_rounds_default()}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return {'task_id': task_id, 'records': [], 'max_rounds':
                omega_max_rounds_default()}
    data.setdefault('task_id', task_id)
    data.setdefault('records', [])
    data.setdefault('max_rounds', omega_max_rounds_default())
    return data


def _save_ledger(data: Dict[str, Any], meta_dir: Optional[str] = None) -> str:
    path = _ledger_path(data['task_id'], meta_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


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
    def _load(self) -> Dict[str, Any]:
        return load_ledger(self.task_id, self.meta_dir)

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
        data = self._load()
        data['max_rounds'] = self.max_rounds
        # 同 id 覆盖（upsert 语义）
        data['records'] = [r for r in data['records']
                           if r.get('id') != rec['id']] + [rec]
        self._save(data)

    def _update_status(self, rec_id: str, status: str,
                       content: Optional[str] = None) -> None:
        data = self._load()
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
                                      'gate': gate}, ensure_ascii=False),
               'status': 'approved' if passed else 'rejected',
               'author': reviewer, 'created_at': _now_iso(),
               'updated_at': _now_iso()}
        if passed:
            self._append(rec)
            out = {'ok': True, 'stage': T_RESULT, 'result_id': rid,
                   'task_id': self.task_id, 'round': rnd,
                   'status': 'approved', 'reviewer': reviewer, 'reason': reason,
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
    def check_record(self, check: dict) -> Dict[str, Any]:
        """记录一次外部命令检查结果。门禁状态一律由 check['ok']（exit_code==0）
        推导（fail-closed），不信任调用方传入的 status，防止伪造通过。"""
        t0 = time.perf_counter()
        eff = 'passed' if bool(check.get('ok')) else 'failed'
        rnd = self._count(T_CHECK) + 1
        cid = f'check:{self.task_id}:r{rnd}'
        self._append({'id': cid, 'task_id': self.task_id, 'spec_type': T_CHECK,
                      'content': json.dumps(check, ensure_ascii=False),
                      'status': eff, 'author': 'run_check',
                      'created_at': _now_iso(), 'updated_at': _now_iso()})
        _log('omega.check_record', eff == 'passed', {'task_id': self.task_id},
             {'check_id': cid, 'status': eff},
             int((time.perf_counter() - t0) * 1000), self.task_id)
        return {'ok': True, 'check_id': cid, 'task_id': self.task_id,
                'round': rnd, 'status': eff}

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
        if task_updated_at and cur.get('created_at', '') < task_updated_at:
            return False, (f'gate: 检查记录 [{cur["id"]}]（{cur["created_at"]}）'
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
