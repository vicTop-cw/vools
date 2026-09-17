"""workflow.py —— DAG 工作流编排引擎（docs/10 §B）。

职责：
1. `Workflow` —— 解析 .actus.md 中的 workflow 元数据，构建 DAG
2. `Executor` —— 驱动 DAG 执行：拓扑排序、并行/串行、节点重试、条件分支
3. 跨节点数据流转：$node.output.field 引用上游输出
4. 工作流级留痕：_meta/workflows/<workflow_id>.json

设计原则：
- 零外部依赖（自实现拓扑排序和调度）
- 节点动作通过 actuscore.execute 执行
- 失败策略：on_failure=abort/continue/fallback
- 重试策略：retry.max_attempts、backoff_ms、backoff_multiplier
"""

__all__ = ['Workflow', 'WorkflowExecutor', 'DAGScheduler']

import json
import os
import re
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Dict, List, Optional, Set, Tuple

from .errors import ActionError
from .model import Action
from . import execute as _execute
from . import records as _records


class DAGScheduler:
    """DAG 拓扑排序与调度器。

    支持：
    - Kahn 算法拓扑排序
    - 并行执行（同一层节点可同时执行）
    - 串行执行（graph.parallel=false 时每层只执行一个节点）
    """

    def __init__(self, nodes: List[Dict]):
        """
        参数:
            nodes: workflow.nodes 列表，每项至少含 id、action_id、depends（可选）。
        """
        self.nodes = {n['id']: n for n in nodes}
        self._build_graph()

    def _build_graph(self):
        """构建邻接表和入度表。"""
        self.adj: Dict[str, Set[str]] = {nid: set() for nid in self.nodes}
        self.in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}

        for nid, node in self.nodes.items():
            for dep in node.get('depends', []) or []:
                if dep in self.nodes:
                    self.adj[dep].add(nid)
                    self.in_degree[nid] += 1

    def topological_sort(self) -> List[List[str]]:
        """Kahn 算法分层拓扑排序。

        返回:
            List[List[str]]: 每层可并行执行的节点 id 列表。
        """
        in_deg = dict(self.in_degree)
        layers: List[List[str]] = []
        queue = deque([nid for nid, deg in in_deg.items() if deg == 0])

        while queue:
            layer = list(queue)
            layers.append(layer)
            next_queue = deque()
            for nid in layer:
                for neighbor in self.adj[nid]:
                    in_deg[neighbor] -= 1
                    if in_deg[neighbor] == 0:
                        next_queue.append(neighbor)
            queue = next_queue

        # 检查环
        visited = sum(len(l) for l in layers)
        if visited != len(self.nodes):
            unresolved = [nid for nid, deg in in_deg.items() if deg > 0]
            raise ActionError('dag_cycle',
                              f'DAG 存在环或未解析依赖: {unresolved}')

        return layers

    def get_dependents(self, node_id: str) -> Set[str]:
        """获取直接下游节点。"""
        return self.adj.get(node_id, set())


class WorkflowExecutor:
    """DAG 工作流执行器。

    驱动拓扑排序后的节点执行，支持：
    - 条件分支（condition 字段 + and/or/==/!=/ok/failed/contains/>/<）
    - 并行执行（ThreadPoolExecutor）
    - 错误恢复（重试 + 退避 + fallback 节点 + on_failure 策略）
    - 跨节点数据流转（$node.field 引用）
    - per-node 超时控制
    """

    def __init__(self, workflow: 'Workflow', meta_dir: str,
                 max_workers: int = 4, confirmed: bool = True):
        """
        参数:
            workflow: 工作流定义。
            meta_dir: 留痕目录（工作流级留痕存储在 _meta/workflows/）。
            max_workers: 并行执行线程数。
            confirmed: 是否跳过人类确认。
        """
        self.workflow = workflow
        self.meta_dir = meta_dir
        self.max_workers = max_workers
        self.confirmed = confirmed
        self._node_outputs: Dict[str, Dict] = {}
        self._node_status: Dict[str, str] = {}  # node_id -> ok/failed/skipped
        self._records: List[Dict] = []
        self._start_time = 0.0

    def run(self) -> Dict:
        """执行整个工作流。

        返回:
            Dict: {
                'workflow_id': 工作流 id,
                'status': 'ok' | 'failed' | 'partial',
                'node_status': {node_id: status},
                'outputs': {node_id: output},
                'records': [执行记录],
                'duration_ms': 总耗时,
            }
        """
        self._start_time = time.time()
        self._node_outputs.clear()
        self._node_status.clear()
        self._records.clear()

        scheduler = DAGScheduler(self.workflow.nodes)
        layers = scheduler.topological_sort()
        graph_cfg = self.workflow.graph or {}
        parallel = graph_cfg.get('parallel', True)
        on_failure = graph_cfg.get('on_failure', 'abort')

        for layer in layers:
            if parallel:
                self._execute_parallel(layer, scheduler, on_failure)
            else:
                self._execute_serial(layer, scheduler, on_failure)

            # 检查是否需要中断
            if on_failure == 'abort' and any(
                    s == 'failed' for s in self._node_status.values()):
                break

        duration_ms = round((time.time() - self._start_time) * 1000, 1)
        status = self._compute_status()

        result = {
            'workflow_id': self.workflow.workflow_id,
            'status': status,
            'node_status': dict(self._node_status),
            'outputs': dict(self._node_outputs),
            'records': self._records,
            'duration_ms': duration_ms,
        }

        # 留痕
        self._persist(result)
        return result

    def _compute_status(self) -> str:
        statuses = list(self._node_status.values())
        if all(s == 'ok' for s in statuses):
            return 'ok'
        if all(s == 'failed' for s in statuses):
            return 'failed'
        return 'partial'

    def _execute_parallel(self, layer: List[str], scheduler: DAGScheduler,
                          on_failure: str):
        """并行执行一层节点。"""
        futures: Dict[str, Future] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            for nid in layer:
                futures[nid] = pool.submit(self._execute_node, nid)

        for nid, future in futures.items():
            try:
                future.result(timeout=300)  # 5 分钟超时
            except Exception as e:
                self._node_status[nid] = 'failed'
                self._records.append({
                    'node_id': nid,
                    'status': 'failed',
                    'error': str(e),
                })

    def _execute_serial(self, layer: List[str], scheduler: DAGScheduler,
                        on_failure: str):
        """串行执行一层节点。"""
        for nid in layer:
            try:
                self._execute_node(nid)
            except Exception as e:
                self._node_status[nid] = 'failed'
                self._records.append({
                    'node_id': nid,
                    'status': 'failed',
                    'error': str(e),
                })
                if on_failure == 'abort':
                    break

    def _execute_node(self, node_id: str):
        """执行单个节点（含重试、fallback 和 per-node 超时）。"""
        node = self.workflow.nodes[node_id]
        action_id = node.get('action_id', '')
        retry_cfg = node.get('retry', {})
        max_attempts = retry_cfg.get('max_attempts', 1)
        backoff_ms = retry_cfg.get('backoff_ms', 0)
        backoff_multiplier = retry_cfg.get('backoff_multiplier', 1.0)

        # 条件分支：检查 condition
        condition = node.get('condition')
        if condition and not self._eval_condition(condition):
            self._node_status[node_id] = 'skipped'
            self._records.append({
                'node_id': node_id,
                'status': 'skipped',
                'message': f'条件不满足: {condition}',
            })
            return

        # 解析参数（支持跨节点引用）
        params = self._resolve_params(node.get('params', {}))

        # per-node 超时
        timeout_s = node.get('timeout_s')

        last_error = None
        for attempt in range(max_attempts):
            try:
                if timeout_s:
                    import threading
                    result_holder = [None]
                    def _run():
                        result_holder[0] = _execute.execute(action_id, params, confirmed=self.confirmed)
                    t = threading.Thread(target=_run)
                    t.start()
                    t.join(timeout=timeout_s)
                    if t.is_alive():
                        raise TimeoutError(f'节点执行超时 ({timeout_s}s)')
                    result = result_holder[0]
                else:
                    result = _execute.execute(action_id, params, confirmed=self.confirmed)

                if result.get('status') == 'ok':
                    self._node_outputs[node_id] = result.get('data', {})
                    self._node_status[node_id] = 'ok'
                    self._records.append({
                        'node_id': node_id,
                        'status': 'ok',
                        'attempt': attempt + 1,
                    })
                    return
                else:
                    last_error = result.get('error', {}).get('message', 'unknown')
            except Exception as e:
                last_error = str(e)

            # 退避
            if attempt < max_attempts - 1 and backoff_ms > 0:
                sleep_ms = backoff_ms * (backoff_multiplier ** attempt)
                time.sleep(sleep_ms / 1000.0)

        # 重试耗尽 → 尝试 fallback
        fallback = node.get('fallback')
        if fallback:
            try:
                result = _execute.execute(fallback, params, confirmed=self.confirmed)
                if result.get('status') == 'ok':
                    self._node_outputs[node_id] = result.get('data', {})
                    self._node_status[node_id] = 'ok'
                    self._records.append({
                        'node_id': node_id,
                        'status': 'ok',
                        'fallback': fallback,
                        'message': f'fallback {fallback} 替代',
                    })
                    return
            except Exception:
                pass

        self._node_status[node_id] = 'failed'
        self._records.append({
            'node_id': node_id,
            'status': 'failed',
            'error': f'重试 {max_attempts} 次后仍失败: {last_error}',
            'attempts': max_attempts,
        })

    def _resolve_params(self, params: Dict) -> Dict:
        """解析参数中的跨节点引用 $node.output.field。"""
        resolved = {}
        for k, v in params.items():
            if isinstance(v, str) and v.startswith('$'):
                resolved[k] = self._resolve_ref(v)
            else:
                resolved[k] = v
        return resolved

    def _resolve_ref(self, ref: str) -> Any:
        """解析 $node_id.path.to.field 引用。"""
        # 格式: $node_id.field 或 $node_id.nested.field；
        # 兼容 schema 文档（docs/10 §C.6）的 $node_id.output.field 写法 ——
        # output 只是节点输出 data 的别名，统一剥掉前缀。
        # node_id 只含字母数字下划线连字符（不含点），避免贪婪匹配
        match = re.match(r'^\$([a-zA-Z0-9_-]+)\.(.+)$', ref)
        if not match:
            return ref
        field_path = match.group(2)
        if field_path.startswith('output.') or field_path == 'output':
            field_path = field_path[len('output.'):] if field_path != 'output' else ''
            if not field_path:
                return self._node_outputs.get(match.group(1))

        node_id = match.group(1)

        output = self._node_outputs.get(node_id, {})
        parts = field_path.split('.')
        val = output
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return None
        return val

    def _eval_condition(self, condition: str) -> bool:
        """增强条件求值。

        支持:
        - $node.status == 'ok' / 'failed'
        - $node.output.field == value / != value
        - $node.output.field > value / < value (数值比较)
        - $node.output.field contains value (字符串包含)
        - 简单的 and / or 组合
        """
        if ' and ' in condition:
            return all(self._eval_condition(c.strip()) for c in condition.split(' and '))
        if ' or ' in condition:
            return any(self._eval_condition(c.strip()) for c in condition.split(' or '))

        # 多操作符支持: == != >= <= > < contains
        match = re.match(
            r'^\$([a-zA-Z0-9_.-]+)\.([a-zA-Z0-9_.-]+)\s*(==|!=|>=|<=|>|<|contains)\s*(.+)$',
            condition
        )
        if not match:
            return False

        node_id = match.group(1)
        field = match.group(2)
        op = match.group(3)
        value = match.group(4).strip().strip("'\"")

        actual = None
        if field == 'status':
            actual = self._node_status.get(node_id)
        else:
            output = self._node_outputs.get(node_id, {})
            actual = output.get(field)

        # 状态快捷算子
        if op == '==' and value == 'ok':
            return actual == 'ok'
        if op == '==' and value == 'failed':
            return actual == 'failed'

        # contains 算子（字符串包含）
        if op == 'contains':
            return str(value) in str(actual)

        # 数值比较（>= <= > <）
        if op in ('>=', '<=', '>', '<'):
            try:
                a, v = float(actual), float(value)
                if op == '>=': return a >= v
                if op == '<=': return a <= v
                if op == '>': return a > v
                if op == '<': return a < v
            except (ValueError, TypeError):
                return False

        # 布尔归一（docs/10 §C.5 示例：test.output.passed == true）
        if op in ('==', '!=') and value.lower() in ('true', 'false'):
            expected = value.lower() == 'true'
            if isinstance(actual, bool):
                return (actual == expected) if op == '==' else (actual != expected)
            if isinstance(actual, str) and actual.lower() in ('true', 'false'):
                matched = actual.lower() == 'true'
                return matched if op == '==' else (not matched)

        # 字符串相等
        if op == '==':
            return str(actual) == value
        if op == '!=':
            return str(actual) != value
        return False

    def _persist(self, result: Dict):
        """工作流级留痕。"""
        wf_dir = os.path.join(self.meta_dir, 'workflows')
        os.makedirs(wf_dir, exist_ok=True)
        path = os.path.join(wf_dir, f'{self.workflow.workflow_id}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)


class Workflow:
    """工作流定义（从动作文件 workflow 元数据解析）。"""

    def __init__(self, action: Action):
        self.action = action
        self.workflow_id = action.meta.get('id', '')
        wf_meta = action.meta.get('workflow', {})
        self.raw_nodes: List[Dict] = wf_meta.get('nodes', [])
        self.graph: Optional[Dict] = wf_meta.get('graph')

        # 标准化节点：schema（docs/10 §C.1 / action.schema.json #/definitions/node）
        # 的键是 action/args，引擎内部用 action_id/params —— 在这里做一次归一，
        # 两种写法均可（action_id 优先）。
        self.nodes: Dict[str, Dict] = {}
        for node in self.raw_nodes:
            nid = node.get('id', '')
            if not nid:
                continue
            norm = dict(node)
            if not norm.get('action_id'):
                norm['action_id'] = node.get('action', '')
            if 'params' not in norm and 'args' in norm:
                norm['params'] = norm['args']
            self.nodes[nid] = norm

    def validate(self) -> List[str]:
        """校验工作流定义合法性。

        返回:
            错误列表（空表示合法）。
        """
        errors = []
        if not self.raw_nodes:
            errors.append('workflow.nodes 为空')
            return errors

        # 检查节点 id 唯一
        ids = [n.get('id', '') for n in self.raw_nodes]
        if len(ids) != len(set(ids)):
            errors.append('workflow.nodes 中存在重复 id')

        # 检查依赖存在性
        for node in self.raw_nodes:
            nid = node.get('id', '')
            for dep in node.get('depends', []) or []:
                if dep not in ids:
                    errors.append(f'节点 {nid} 依赖不存在: {dep}')

        # 检查 DAG 无环
        try:
            scheduler = DAGScheduler(self.raw_nodes)
            scheduler.topological_sort()
        except ActionError as e:
            errors.append(str(e))

        return errors

    def execute(self, meta_dir: str, max_workers: int = 4,
                confirmed: bool = True) -> Dict:
        """执行工作流。"""
        executor = WorkflowExecutor(self, meta_dir, max_workers, confirmed)
        return executor.run()


def run_workflow(workflow_id: str, meta_dir: str,
                  max_workers: int = 4, confirmed: bool = True) -> Dict:
    """便捷入口：从动作 id 加载并执行工作流。"""
    from .model import parse_cfg_from_file
    from .indexer import load_index

    idx = load_index(meta_dir)
    if workflow_id not in idx['actions']:
        raise ActionError('workflow_not_found', f'工作流不存在: {workflow_id}')

    action_path = idx['actions'][workflow_id].get('file_path', '')
    action = parse_cfg_from_file(action_path)
    wf = Workflow(action)

    errors = wf.validate()
    if errors:
        raise ActionError('workflow_invalid', f'工作流校验失败: {"; ".join(errors)}')

    return wf.execute(meta_dir, max_workers, confirmed)
