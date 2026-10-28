"""selfdrive.py — 自驱式编程：递归拆解 → 执行 → Ω 强验证。

设计参照兄弟项目 FIST-Mbt 的自驱流水线（selfdrive_*）与 atgc 递归拆解
（task_plan_deep + omega_strong_verify），在 Actus 侧落地为最小可用控制器：

    目标 → 规划(拆解) → 逐节点执行 → Ω-gate 强验证
                          ├─ 通过 → done
                          └─ 失败且未到最大深度 → 递归拆解为子任务 → 重复

关键特性
--------
- **递归拆解**：`decompose(goal, depth)` 产出 DAG（parent/children），
  默认 max_depth=2；叶节点失败且 `depth < max_depth` 时由 `_expand_failed()`
  再拆一层后继续下一轮，`max_rounds` 即这条回炉链的轮次预算。
- **Ω 强验证**：每个叶子产出必须过 Ω-gate（`omega.verify_output`），
  强验证模式下缺 spec 视为失败（`omega_spec_missing`），杜绝"静默通过"。
- **call_log**：每个节点的执行/验证落一条调用日志（caller='selfdrive'），
  失败可 `report_bug` 关联。
- **可插拔 worker**：默认 worker 为确定性 echo（便于测试，不触碰引擎）；真实执行
  由 `selfdrive_worker.ActionWorker` 承担，公共入口已接通——CLI
  `actus selfdrive run <goal> --plan/--plan-file`，MCP `actus_selfdrive_run{plan}`；
  两处返回值都用 `worker.kind` 明示本次是 `echo` 还是 `action`。
- **持久化**：运行态写 `_meta/selfdrive/<run_id>.json`，支持断点查看（status）。

自驱语义：控制器不依赖人类逐步指令——给定目标后自主规划、执行、验证、在失败
处继续递归拆解，直到全树通过或达到深度/轮次上限。
"""


import json
import os
import re
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional

from .paths import meta_dir
from . import calllog
from . import omega as _omega
from . import omega_strong as _omega_strong

__all__ = ['Decomposer', 'SelfDrive', 'run', 'load_run', 'list_runs',
           'STRONG_ENV']

_TZ = timezone(timedelta(hours=8))
STRONG_ENV = 'ACTUS_OMEGA_STRONG'

# 递归拆解用的模板（可被调用方 cover）
_DEFAULT_TEMPLATE: List[str] = [
    '澄清「{goal}」的验收标准与输入输出',
    '实现「{goal}」的主体逻辑',
    '为「{goal}」补充测试/自检并过 Ω-gate',
]


def _now_iso() -> str:
    return datetime.now(_TZ).isoformat(timespec='seconds')


def _new_id(prefix: str = 'sd') -> str:
    return f'{prefix}-{uuid.uuid4().hex[:8]}'


def strong_enabled(config: Optional[dict] = None) -> bool:
    """Ω 强验证是否开启（显式 config 优先，其次环境变量）。"""
    if config is not None and 'omega_strong' in config:
        return bool(config['omega_strong'])
    return os.environ.get(STRONG_ENV, '').strip() in ('1', 'true', 'True', 'yes')


def _default_meta() -> str:
    # 路径真源：ACTUS_META_DIR > ACTUS_REPO_ROOT/_meta > __file__ 推导（paths.meta_dir()）
    return meta_dir()


# ── 拆解器 ──

class Decomposer:
    """把目标递归拆解为 DAG 节点。

    decompose(goal, depth) 返回节点列表（含 root）；子节点通过 `parent` 关联，
    深度为 0 的叶子才是可执行单元。
    """

    def __init__(self, max_depth: int = 2, template: Optional[List[str]] = None,
                 planner: Optional[Callable[[str, int], List[str]]] = None):
        # 入参校验：`max_depth='x'` 此前在 max() 处抛裸 TypeError；
        # `template='abc'` 会被 list() **逐字符展开**成 ['a','b','c']
        # （与 BUG-490/492 的 args='abc' 同族）。
        if isinstance(max_depth, bool) or not isinstance(max_depth, int):
            raise TypeError(
                f"max_depth 必须是整数，得到 {type(max_depth).__name__}: {max_depth!r}")
        if max_depth < 0:
            raise ValueError(f"max_depth 必须 ≥0，得到 {max_depth}")
        if template is not None:
            if isinstance(template, (str, bytes)):
                raise TypeError(
                    f"template 必须是字符串列表，不能是字符串（会被逐字符展开），"
                    f"得到 {template!r}")
            if not isinstance(template, (list, tuple)):
                raise TypeError(
                    f"template 必须是 list/tuple，得到 {type(template).__name__}")
            for t in template:
                if not isinstance(t, str):
                    raise TypeError(f"template 的元素必须是字符串，得到 {t!r}")
        self.max_depth = max_depth
        self.template = list(template) if template else list(_DEFAULT_TEMPLATE)
        self.planner = planner

    @staticmethod
    def _require_goal(goal) -> str:
        """goal 必须是非空字符串——否则会生成名为「None」的任务。"""
        if not isinstance(goal, str):
            raise TypeError(f"goal 必须是字符串，得到 {type(goal).__name__}: {goal!r}")
        if not goal.strip():
            raise ValueError("goal 不能为空字符串")
        return goal

    def template_children(self, goal: str, depth: int) -> List[str]:
        """按模板产出子目标（不受 planner 影响），仍受 max_depth 约束。"""
        goal = self._require_goal(goal)
        if depth >= self.max_depth:
            return []
        return [t.format(goal=goal) for t in self.template]

    def children_of(self, goal: str, depth: int) -> List[str]:
        """子目标生成：planner 优先，否则按模板展开；两者都到 max_depth 即止。"""
        goal = self._require_goal(goal)
        if depth >= self.max_depth:
            return []
        if self.planner:
            return self.planner(goal, depth) or []
        return self.template_children(goal, depth)

    def decompose(self, goal: str, run_id: str) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = []
        root = {
            'id': 'root', 'goal': goal, 'depth': 0, 'parent': None,
            'status': 'pending', 'children': [], 'result': None, 'omega': None,
        }
        nodes.append(root)
        # BFS 展开
        queue = [root]
        counter = 0
        while queue:
            node = queue.pop(0)
            kids = self.children_of(node['goal'], node['depth'])
            if not kids:
                continue
            for sub in kids:
                counter += 1
                child = {
                    'id': f't{counter:03d}', 'goal': sub, 'depth': node['depth'] + 1,
                    'parent': node['id'], 'status': 'pending', 'children': [],
                    'result': None, 'omega': None,
                }
                node['children'].append(child['id'])
                nodes.append(child)
                queue.append(child)
        return nodes


def _leaves(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """返回叶子节点（无子节点），按深度降序（先深后浅）。"""
    return [n for n in nodes if not n['children']]


# ── 控制器 ──

class SelfDrive:
    """自驱控制器：拆解 → 执行 → Ω 强验证 → 失败递归。"""

    def __init__(self, goal: str, max_depth: int = 2,
                 worker: Optional[Callable[[Dict[str, Any]], Any]] = None,
                 spec_resolver: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None,
                 strong: Optional[bool] = None,
                 meta_dir: Optional[str] = None,
                 max_rounds: int = 3,
                 decomposer: Optional[Decomposer] = None):
        # goal 必须非空字符串：此前传 None 会一路把「None」当成目标文本写进
        # 子任务标题（实测 children_of(None) 产出「澄清「None」的验收标准…」）。
        self.goal = Decomposer._require_goal(goal)
        if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds < 1:
            raise ValueError(f"max_rounds 必须是 ≥1 的整数，得到 {max_rounds!r}")
        self.max_depth = max_depth
        self.worker = worker or self._echo_worker
        self.spec_resolver = spec_resolver
        self.strong = strong_enabled({'omega_strong': strong}) if strong is not None \
            else strong_enabled()
        self.meta_dir = meta_dir or _default_meta()
        self.max_rounds = max(1, max_rounds)
        self.decomposer = decomposer or Decomposer(max_depth=max_depth)
        self.run_id = _new_id()
        self.nodes: List[Dict[str, Any]] = []
        self.started_at = _now_iso()
        self.log: List[Dict[str, Any]] = []
        # FIST 对齐：语料驱动的执行前门禁（[omega:required] 节点须先过 omega_spec_review）。
        # 默认关闭——未打标记的节点直接放行，行为与既有语义完全一致。
        self.enforce_pre_gate = strong is True or (strong is None and self.strong)

    # ── 默认 worker：确定性 echo，便于自检/测试 ──
    @staticmethod
    def _echo_worker(node: Dict[str, Any]) -> Dict[str, Any]:
        return {'status': 'ok', 'goal': node['goal'], 'echo': True}

    # ── 持久化 ──
    def _runs_dir(self) -> str:
        return os.path.join(self.meta_dir, 'selfdrive')

    def snapshot(self) -> Dict[str, Any]:
        return {
            'run_id': self.run_id, 'goal': self.goal,
            'max_depth': self.max_depth, 'strong': self.strong,
            'started_at': self.started_at, 'updated_at': _now_iso(),
            'nodes': self.nodes, 'log': self.log,
            'summary': self.summary(),
        }

    def save(self) -> str:
        d = self._runs_dir()
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f'{self.run_id}.json')
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return path

    # ── 验证 ──
    def _resolve_spec(self, node: Dict[str, Any]) -> Optional[str]:
        if self.spec_resolver:
            return self.spec_resolver(node)
        return None

    def _verify(self, node: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """对节点结果执行 Ω-gate 验证，返回 gate 结论。"""
        spec_path = self._resolve_spec(node)
        if not spec_path:
            if self.strong:
                return {'passed': False, 'accuracy': 0.0,
                        'reason': 'omega_spec_missing'}
            return {'passed': True, 'accuracy': 100.0, 'reason': 'no_spec_soft'}
        try:
            report = _omega.verify_output(spec_path, result)
        except Exception as e:  # noqa: BLE001
            return {'passed': False, 'accuracy': 0.0,
                    'reason': f'omega_error: {type(e).__name__}: {e}'}
        gate = report.get('gate', {})
        return {'passed': bool(gate.get('passed', False)),
                'accuracy': gate.get('accuracy', 0.0),
                'reason': 'omega_gate', 'report': report}

    # ── 执行后门禁（FIST 对齐：验收前两道闸门）──
    def _post_execute_gates(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """节点执行完、判定 done 之前的两道门禁。

        1. `omega_strong.verify_gate`：带 `[omega:required]` 的节点必须有
           **已通过的成果复验**（omega_result_verify）；
        2. `omega_strong.check_gate`：带 `[gate:required]` 的节点必须有
           **新鲜且通过**的外部检查记录（omega_check_record）。

        审计修复：这两个门禁此前**从未被任何产品代码调用** —— 模块文档写着
        "产出对已审核语料复验 → 通过才放行验收（verify_gate）"、`[gate:required]`
        写着"须有新鲜且通过的 check 记录"，实际 `gate_enabled()` 只被 `check_gate`
        引用，而 `check_gate` 只被测试调用 → **[gate:required] 是个空标记**。
        现在在节点的验收点接线：默认（非 strong / enforce_pre_gate=False）零侵入
        直接放行；strong 模式且节点带标记、记录不满足 → 节点判 failed 并给出原因。
        门禁自身异常（账本损坏等）→ fail-closed（拒绝），绝不静默放行。
        """
        if not self.enforce_pre_gate:
            return None
        ledger = _omega_strong.get_ledger(
            node['id'], meta_dir=self.meta_dir, max_rounds=self.max_rounds)
        checks = (
            ('omega_verify_gate', ledger.verify_gate),
            ('omega_check_gate', ledger.check_gate),
        )
        for name, check in checks:
            try:
                if name == 'omega_check_gate':
                    ok, why = check(node, node.get('updated_at'))
                else:
                    ok, why = check(node)
            except Exception as exc:   # noqa: BLE001 —— 门禁异常必须 fail-closed
                ok, why = False, '%s: 门禁执行失败（%s: %s）' % (
                    name, type(exc).__name__, exc)
            if not ok:
                return {'passed': False, 'accuracy': 0.0,
                        'reason': name, 'detail': why}
        return None

    # ── 单节点执行 ──
    def _pre_execute_gate(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """FIST 对齐的执行前门禁：强验证模式下，带 [omega:required] 的节点
        必须先有「已通过审核」的语料（omega_spec_create → omega_spec_review）。

        - enforce_pre_gate=False（默认）→ 直接返回 None（放行，零侵入）。
        - 节点未打 [omega:required] → 放行（默认关闭即现状）。
        - 打了标记但语料未就绪 → 返回门禁结论（节点判 failed，不调用 worker）。
        """
        if not self.enforce_pre_gate:
            return None
        if not _omega_strong.omega_enabled(node):
            return None
        ledger = _omega_strong.get_ledger(
            node['id'], meta_dir=self.meta_dir,
            max_rounds=self.max_rounds)
        ok, why = ledger.execute_gate(node)
        if ok:
            return None
        return {'passed': False, 'accuracy': 0.0,
                'reason': 'omega_execute_gate', 'detail': why}

    def _run_node(self, node: Dict[str, Any]) -> None:
        t0 = time.perf_counter()
        pre = self._pre_execute_gate(node)
        if pre is not None:
            node['result'] = {'status': 'blocked', 'error': {
                'code': 'omega_execute_gate', 'message': pre['detail']}}
            node['omega'] = pre
            node['status'] = 'failed'
            node['reason'] = pre['reason']
            runtime_ms = int((time.perf_counter() - t0) * 1000)
            calllog.write_call_log(
                'selfdrive.node', params={'node': node['id'],
                                          'goal': node['goal']},
                result={'status': node['status'], 'omega': node['omega']},
                ok=False, runtime_ms=runtime_ms, caller='selfdrive',
                ns=self.run_id)
            self.log.append({'ts': _now_iso(), 'node': node['id'],
                             'status': node['status'],
                             'reason': node['reason'],
                             'runtime_ms': runtime_ms})
            return

        try:
            result = self.worker(node)
        except Exception as e:  # noqa: BLE001
            result = {'status': 'failed',
                      'error': {'code': 'worker_error', 'message': str(e)}}
        if not isinstance(result, dict):
            result = {'status': 'ok', 'value': result}

        gate = self._verify(node, result)
        node['result'] = result
        node['omega'] = {k: v for k, v in gate.items() if k != 'report'}
        if gate.get('report'):
            node['omega']['report'] = gate['report']

        # 验收前门禁：产出复验（verify_gate）+ 外部判据（check_gate）。
        # 审计修复：此前从未接线，[gate:required] 是空标记 —— 见 _post_execute_gates。
        post = self._post_execute_gates(node)
        if post is not None:
            node['omega'] = post
            node['status'] = 'failed'
            node['reason'] = post['reason']
            runtime_ms = int((time.perf_counter() - t0) * 1000)
            calllog.write_call_log(
                'selfdrive.node', params={'node': node['id'],
                                          'goal': node['goal']},
                result={'status': node['status'], 'omega': node['omega']},
                ok=False, runtime_ms=runtime_ms, caller='selfdrive',
                ns=self.run_id)
            self.log.append({'ts': _now_iso(), 'node': node['id'],
                             'status': node['status'],
                             'reason': node['reason'],
                             'runtime_ms': runtime_ms})
            return

        ok = result.get('status', 'ok') == 'ok' and gate['passed']
        node['status'] = 'done' if ok else 'failed'
        node['reason'] = gate.get('reason', '')

        runtime_ms = int((time.perf_counter() - t0) * 1000)
        calllog.write_call_log(
            'selfdrive.node', params={'node': node['id'], 'goal': node['goal']},
            result={'status': node['status'], 'omega': node['omega']},
            ok=ok, runtime_ms=runtime_ms, caller='selfdrive',
            ns=self.run_id)
        self.log.append({'ts': _now_iso(), 'node': node['id'],
                         'status': node['status'], 'reason': node['reason'],
                         'runtime_ms': runtime_ms})

    # ── 聚合：父节点由子节点上卷 ──
    def _rollup(self) -> None:
        by_id = {n['id']: n for n in self.nodes}
        for node in reversed(self.nodes):
            if not node['children']:
                continue
            kids = [by_id[c] for c in node['children'] if c in by_id]
            if kids and all(k['status'] == 'done' for k in kids):
                node['status'] = 'done'
                node['omega'] = {'passed': True, 'accuracy': 100.0,
                                 'reason': 'rollup'}
            elif any(k['status'] == 'failed' for k in kids):
                node['status'] = 'failed'
                node['reason'] = 'child_failed'
                node['omega'] = {'passed': False,
                                 'reason': 'child_failed'}

    def summary(self) -> Dict[str, Any]:
        done = sum(1 for n in self.nodes if n['status'] == 'done')
        failed = sum(1 for n in self.nodes if n['status'] == 'failed')
        leaves = _leaves(self.nodes)
        return {
            'total': len(self.nodes), 'done': done, 'failed': failed,
            'pending': len(self.nodes) - done - failed,
            'leaves': len(leaves),
            'all_done': bool(self.nodes) and done == len(self.nodes),
            'strong': self.strong,
        }

    # ── 失败驱动递归拆解 ──
    def _next_seq(self) -> int:
        """现有 tNNN 节点 id 的最大序号（供展开时续号，避免 id 冲突）。"""
        mx = 0
        for n in self.nodes:
            m = re.match(r'^t(\d+)$', str(n.get('id') or ''))
            if m:
                mx = max(mx, int(m.group(1)))
        return mx

    def _retry_children(self, node: Dict[str, Any]) -> List[str]:
        """失败叶的再拆策略：先问拆解器，planner 不肯给片时回退模板拆解。

        planner 通常按 goal/depth 判定「这一步已是原子片」，直接复用会永远得到
        空列表、回炉链随之失效；模板三段（澄清验收 / 实现主体 / 补测过 gate）
        是通用的再下钻切法。
        """
        kids = self.decomposer.children_of(node['goal'], node['depth'])
        if kids or not self.decomposer.planner:
            return kids
        return self.decomposer.template_children(node['goal'], node['depth'])

    def _expand_failed(self) -> int:
        """把「失败且未达最大深度」的叶再拆一层，返回实际展开的叶数。

        静态 BFS 只在启动时展开一次，浅叶（planner 提前返回 [] 或自定义模板
        截断）失败后若不在此处下钻，文件头宣称的「失败且未到最大深度 → 递归
        拆解为子任务 → 重复」就无人执行，max_rounds 也退化为死参数。
        """
        targets = [n for n in self.nodes
                   if not n['children'] and n['status'] == 'failed'
                   and n['depth'] < self.decomposer.max_depth]
        if not targets:
            return 0
        seq = self._next_seq()
        expanded = 0
        for node in targets:
            subs = self._retry_children(node)
            if not subs:
                continue
            node['status'] = 'pending'
            node['reason'] = ''
            node['result'] = None
            node['omega'] = None
            for sub in subs:
                seq += 1
                child = {'id': f't{seq:03d}', 'goal': sub,
                         'depth': node['depth'] + 1, 'parent': node['id'],
                         'status': 'pending', 'children': [],
                         'result': None, 'omega': None}
                node['children'].append(child['id'])
                self.nodes.append(child)
            self.log.append({'ts': _now_iso(), 'node': node['id'],
                             'status': 'expanded', 'reason': 'retry_deeper',
                             'children': list(node['children'])})
            expanded += 1
        return expanded

    # ── 主循环 ──
    def run(self) -> Dict[str, Any]:
        self.nodes = self.decomposer.decompose(self.goal, self.run_id)

        for rnd in range(self.max_rounds):
            pending_leaves = [n for n in _leaves(self.nodes)
                              if n['status'] == 'pending']
            if not pending_leaves:
                break
            for node in pending_leaves:
                self._run_node(node)
            self._rollup()
            self._expand_failed()
            self.save()
            if self.summary()['all_done']:
                break

        self._rollup()
        self.save()
        return self.snapshot()


# ── 模块级便捷函数 ──

def run(goal: str, **kw) -> Dict[str, Any]:
    return SelfDrive(goal, **kw).run()


def load_run(run_id: str, meta_dir: Optional[str] = None) -> Optional[Dict]:
    path = os.path.join(meta_dir or _default_meta(), 'selfdrive',
                        f'{run_id}.json')
    if not os.path.isfile(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def list_runs(meta_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    d = os.path.join(meta_dir or _default_meta(), 'selfdrive')
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if name.endswith('.json'):
            try:
                with open(os.path.join(d, name), 'r', encoding='utf-8') as f:
                    snap = json.load(f)
                out.append({'run_id': snap.get('run_id'),
                            'goal': snap.get('goal'),
                            'summary': snap.get('summary'),
                            'updated_at': snap.get('updated_at')})
            except Exception:  # noqa: BLE001
                continue
    return out
