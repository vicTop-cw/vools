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
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .errors import ActionError
from .model import Action
from . import executor as _execute
from . import records as _records


class DAGScheduler:
    """DAG 拓扑排序与调度器。

    支持：
    - Kahn 算法拓扑排序
    - 并行执行（同一层节点可同时执行）
    - 串行执行（graph.parallel=false 时每层只执行一个节点）
    """

    def __init__(self, nodes: Union[List[Dict], Dict[str, Dict]]):
        """
        参数:
            nodes: 节点集合，接受两种形态 —— 缺陷③ 的根修法是「在消费点归一」：
                - List[Dict]：`Workflow.raw_nodes`（schema 原样，validate() 用这个）
                - Dict[str, Dict]：`Workflow.nodes`（`Workflow.__init__` 已按 id 归一，
                  run() 用这个）
                只在调用点 list() 会漏掉 validate() 那条 list 路径，故两种都在此喂饱。
        """
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        self.nodes = {n['id']: n for n in nodes}
        self._build_graph()

    def _build_graph(self):
        """构建邻接表和入度表。"""
        self.adj: Dict[str, Set[str]] = {nid: set() for nid in self.nodes}
        self.in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}

        for nid, node in self.nodes.items():
            for dep in (node.get('depends') or node.get('deps') or []):
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
        # graph.max_concurrency 是契约里显式声明的并行上限
        # （contracts/action.schema.json:150；data_pipeline=4、workflow_linear=2 都在用），
        # 而引擎此前根本不读它：动作写 2 也照 max_workers 跑，声明等于没写。
        # 语义取「上限」而非「覆盖」：调用方给的 max_workers 仍可下调。
        declared = (getattr(workflow, 'graph', None) or {}).get('max_concurrency')
        self.declared_concurrency = declared if isinstance(declared, int) and declared > 0 else None
        if self.declared_concurrency is not None:
            self.max_workers = min(self.max_workers, self.declared_concurrency)
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
        # 失败策略：引擎原生键 on_failure（abort/continue/fallback）优先；契约
        # （contracts/action.schema.json #/definitions/workflow_graph）与动作文件
        # 用的是 fail_fast。二者此前各写各的 → 动作声明 fail_fast=false（意图
        # 失败不中断）被引擎缺省 'abort' 静默掐断（缺陷⑨）。此处把契约键
        # fail_fast 解释为引擎语义：True→abort、False→continue；仅在 on_failure
        # 缺席时派生，两键都不写仍维持旧默认 'abort'（不改变既有工作流语义）。
        on_failure = graph_cfg.get('on_failure')
        if on_failure is None:
            if 'fail_fast' in graph_cfg:
                on_failure = 'abort' if graph_cfg.get('fail_fast') else 'continue'
            else:
                on_failure = 'abort'

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

        # 解析参数（支持跨节点引用）—— 收集器按节点新建，不挂 self（见 _resolve_params）
        unparsable: List[Dict] = []
        params = self._resolve_params(node.get('params', {}), unparsable)
        if unparsable:
            # 纯审计留痕：不带 status，不参与节点成败聚合，只保证「引用没解出来」这件事
            # 在 records 里看得见 —— 否则又是一个静默降级点。
            self._records.append({
                'node_id': node_id,
                'unparsable_refs': list(unparsable),
            })

        # per-node 超时
        timeout_s = node.get('timeout_s')

        last_error = None
        for attempt in range(max_attempts):
            try:
                if timeout_s:
                    import threading
                    result_holder = [None]
                    def _run():
                        result_holder[0] = _execute.execute(
                            action_id, params, confirmed=self.confirmed,
                            meta_dir=self.meta_dir)
                    t = threading.Thread(target=_run)
                    t.start()
                    t.join(timeout=timeout_s)
                    if t.is_alive():
                        # Python 没法强杀线程：动作可能仍在写盘、弹窗、发请求。
                        # 这里只如实留下「被放弃的线程还在跑」，不假装中断成功了。
                        # （真正的取消协议是引擎级设计，需 owner 决策。）
                        self._records.append({
                            'node_id': node_id,
                            'status': 'timeout',
                            'timeout_s': timeout_s,
                            'abandoned': True,
                            'abandoned_thread': t.name,
                            'message': f'节点执行超时 ({timeout_s}s)：线程 {t.name} 未被中断，'
                                       f'其副作用仍可能在继续产生',
                        })
                        raise TimeoutError(f'节点执行超时 ({timeout_s}s)')
                    result = result_holder[0]
                else:
                    result = _execute.execute(action_id, params,
                                              confirmed=self.confirmed,
                                              meta_dir=self.meta_dir)

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
                result = _execute.execute(fallback, params,
                                          confirmed=self.confirmed,
                                          meta_dir=self.meta_dir)
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

    # 跨节点引用：$node.field.sub / $node.list[0]
    _REF_RE = re.compile(r'\$([A-Za-z_]\w*(?:\.\w[\w\-\[\]]*)*)')
    # 「整串是不是引用」的形态判定：node_id 字符类与 _resolve_ref 的
    # `^\$([a-zA-Z0-9_-]+)\.` 逐字对齐（notes_C2 §4：两套解析器的字符类必须一致，
    # 否则同一条引用一处认一处不认，又是静默丢值）。
    _REF_SHAPED_RE = re.compile(r'^\$[A-Za-z0-9_-]+\.')

    def _resolve_params(self, params: Dict,
                        unparsable: Optional[List[Dict]] = None) -> Dict:
        """解析参数里的跨节点引用 $node.output.field。

        覆盖三类位置：顶层、嵌套 dict/list、字符串内嵌（"p/$n1.out/f"）。原先只认
        「顶层且整串以 $ 开头」，其余原样透传 —— 与刚在条件求值器上修掉的静默丢值
        同一形状。内嵌替换只认引用根是 workflow 里的真实节点，避免把 "$100" 这类
        字面美元文本吃掉。解不出的通过 out 参数 unparsable 回传，不静默留原样。
        结构不变量：返回值的 key 集合与嵌套形状与入参逐字相同。

        unparsable 由调用方按节点新建（每节点一份），不能挂 self：同层节点在
        ThreadPoolExecutor 里并行解析，共享收集器会让 A 清空/读到 B 的引用，
        把「哪个节点没解出来」记错 —— 留痕本身变成假账。传 None 的调用方
        （诊断探针）只拿解析结果，不取审计。
        """
        return self._resolve_value(params, '$params', unparsable)

    def _resolve_value(self, value: Any, where: str,
                       unparsable: Optional[List[Dict]]) -> Any:
        if isinstance(value, dict):
            return {k: self._resolve_value(v, f'{where}.{k}', unparsable)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(v, f'{where}[{i}]', unparsable)
                    for i, v in enumerate(value)]
        if isinstance(value, str):
            return self._resolve_string(value, where, unparsable)
        return value

    def _is_known_ref(self, token: str) -> bool:
        """引用根是否是绑定工作流里的真实节点。

        没有绑定 DAG 时（诊断探针用 object.__new__ 造空壳 executor，只塞
        _node_outputs/_node_status，见 repro_cond_02）无从判别根是否存在 ——
        此时不拦，交给 _resolve_ref 照常解析，保持空壳用法可读（修复前即如此）。
        """
        nodes = getattr(getattr(self, 'workflow', None), 'nodes', None)
        if not nodes:
            return True
        return token.lstrip('$').split('.')[0] in nodes

    def _resolve_string(self, value: str, where: str,
                        unparsable: Optional[List[Dict]]) -> Any:
        if value.startswith('$') and '$' not in value[1:]:
            # 只有引用形态（$node.field）才进解析；"$100"/"$"/"$.x" 这类字面美元
            # 文本原样保留且不记账 —— 否则真实价格串会被刷成一片 unparsable 噪声，
            # 把「引用写错了」这个可用信号埋掉。
            if not self._REF_SHAPED_RE.match(value):
                return value
            if not self._is_known_ref(value):
                self._note_unparsable(
                    unparsable, where, value, '引用根不是本工作流的节点')
                return value
            return self._dereference(value, where, unparsable)
        if '$' not in value:
            return value

        def sub(m):
            token = m.group(0)
            if not self._is_known_ref(token):
                return token          # 字面美元文本，不吃
            got = self._dereference(token, where, unparsable)
            if got is None:
                # 引用段落在散文里会被 _REF_RE 连字符续读（"$n1.result-post"），
                # 取不到值时整段替换会写成字面 "null" —— 那是假值。保留原 token
                # 并留痕，由审计面判，不把「没取到」伪装成「取到了 null」。
                self._note_unparsable(
                    unparsable, where, token,
                    '内嵌引用解析结果为 None（字段不存在或值为 null）')
                return token
            return got if isinstance(got, str) else json.dumps(got, ensure_ascii=False)

        return self._REF_RE.sub(sub, value)

    def _note_unparsable(self, unparsable: Optional[List[Dict]], where: str,
                         ref: str, reason: str) -> None:
        if unparsable is not None:
            unparsable.append({'path': where, 'ref': ref, 'reason': reason})

    def _dereference(self, ref: str, where: str,
                     unparsable: Optional[List[Dict]]) -> Any:
        try:
            return self._resolve_ref(ref)
        except Exception as e:                        # noqa: BLE001
            self._note_unparsable(
                unparsable, where, ref, f'{type(e).__name__}: {e}')
            return ref

    def _resolve_ref(self, ref: str) -> Any:
        """解析 $node_id.path.to.field 引用。

        存储形态：_node_outputs[node] = 该节点 exec 记录的 result.data
        （JSON 打印动作 = 其 stdout 解析出的 dict；纯文本动作 = {'output': <text>}）。

        $node.output 的两种真实语义（docs/10 §C.5/§C.6）：
          ① data 含 'output' 键（动作打印 {"output": {...}} / 纯文本包装）
             → 'output' 是真实字段，按字面 JSON 路径下钻；
          ② data 不含 'output' 键（动作直接打印结果 JSON，如 {"result": ...}）
             → 'output' 是 data 的别名（§C.5「从 result.data 取值」），剥掉前缀。
        裸 $node.output = 整个节点输出（data 整体）。"""
        # node_id 只含字母数字下划线连字符（不含点），避免贪婪匹配
        match = re.match(r'^\$([a-zA-Z0-9_-]+)\.(.+)$', ref)
        if not match:
            return ref
        node_id = match.group(1)
        field_path = match.group(2)
        data = self._node_outputs.get(node_id)

        # 裸 $node.output → 整个节点输出
        if field_path == 'output':
            return data

        # $node.output.field → 形态①按字面键、形态②按别名剥前缀
        if field_path.startswith('output.'):
            rest = field_path[len('output.'):]
            if isinstance(data, dict) and 'output' in data:
                root = data['output']      # 形态①：'output' 是真实字段
            else:
                root = data if isinstance(data, dict) else {}  # 形态②：别名
            return self._walk_path(root, rest)

        # 通用路径 $node.a.b（非 output 前缀）
        return self._walk_path(data if isinstance(data, dict) else {}, field_path)

    @staticmethod
    def _walk_path(root: Any, path: str) -> Any:
        """沿 a.b.c 路径在 dict 上下钻；遇非 dict 或缺键返回 None。"""
        val = root
        for p in path.split('.'):
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return None
        return val

    @staticmethod
    def _split_logical(expr: str, op: str) -> List[str]:
        """按**引号外**的逻辑运算符（and/or，大小写不敏感）切分表达式。

        引号内的 and/or 是字符串字面量的组成部分，不得当运算符 ——
        例如 `$a.msg == "cats and dogs"` 必须整体作为一个比较项，
        否则会被切成 `$a.msg == "cats` 与 `dogs"` 两段而误判。
        """
        target = op.lower()
        low = expr.lower()
        parts: List[str] = []
        buf: List[str] = []
        quote: Optional[str] = None
        i, n = 0, len(expr)
        while i < n:
            ch = expr[i]
            if quote:
                buf.append(ch)
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in ('"', "'"):
                quote = ch
                buf.append(ch)
                i += 1
                continue
            if low.startswith(target, i):
                before = expr[i - 1] if i > 0 else ' '
                j = i + len(target)
                after = expr[j] if j < n else ' '
                if not (before.isalnum() or before == '_') and \
                   not (after.isalnum() or after == '_'):
                    parts.append(''.join(buf).strip())
                    buf = []
                    i = j
                    continue
            buf.append(ch)
            i += 1
        parts.append(''.join(buf).strip())
        return [p for p in parts if p]

    def _note_condition_unparsable(self, condition: str) -> None:
        """记录一条无法解析的 condition（best-effort，不影响结果 False）。"""
        try:
            self._records.append({
                'node_id': None,
                'status': 'warning',
                'message': f'condition 无法解析（按 false 处理）: {condition}',
            })
        except Exception:  # noqa: BLE001
            pass

    def _eval_condition(self, condition: str) -> bool:
        """增强条件求值 —— 引用取值统一复用 _resolve_ref/_walk_path。

        支持:
        - `$node.status == 'ok'` / `node.status == 'ok'`（`$` 前缀可选，
          docs/10 §C.5 的裸写法与 `$` 写法同结果；`output.status` 亦按 status 取）
        - `$node.output.field == value / != value / >= <= > < / contains value`
          （field 允许点路径，由 _walk_path 下钻）
        - and / or 组合（大小写不敏感，or 优先级低于 and，按引号外边界切分）

        取不到值（节点不存在 / 路径不存在 / 值真的是 null）→ **一律 False**
        （docs/10 §C.5 末条「条件引用不存在的节点 → 视为 false」）。这里绝不能
        让 None 继续往下走：`str(None) != 'true'` 与 `'one' in str(None)` 都是
        True，会把本该 skipped 的节点误放行执行（反向后果）。
        """
        or_parts = self._split_logical(condition, 'or')
        if len(or_parts) > 1:
            return any(self._eval_condition(p) for p in or_parts)
        and_parts = self._split_logical(condition, 'and')
        if len(and_parts) > 1:
            return all(self._eval_condition(p) for p in and_parts)

        # 多操作符支持: == != >= <= > < contains
        # `$` 前缀可选（裸写法是 docs/10:413-415 与 schema 的写法，必须可用）；
        # node_id 字符类与 _resolve_ref 的 `^\$([a-zA-Z0-9_-]+)\.` 对齐（不含点）。
        match = re.match(
            r'^\$?([A-Za-z0-9_-]+)\.([A-Za-z0-9_.-]+?)'
            r'\s*(==|!=|>=|<=|>|<|contains)\s*(.+)$',
            condition
        )
        if not match:
            self._note_condition_unparsable(condition)
            return False

        node_id = match.group(1)
        field = match.group(2)
        op = match.group(3)
        value = match.group(4).strip().strip("'\"")

        # 取值统一复用 _resolve_ref/_walk_path —— 条件侧不得自建扁平 `.get`，
        # 否则 `$n.output.field` 的点路径与 output 别名都取不到值（同一引用
        # 在 _resolve_params 侧能取到、在 condition 侧取不到，条件恒 false）。
        if field in ('status', 'output.status'):
            actual = self._node_status.get(node_id)
        else:
            actual = self._resolve_ref(f'${node_id}.{field}')

        # 取不到值（节点不存在 / 路径不存在 / 真值确为 null）→ 一律 false
        # （docs/10 §C.5 末条：条件引用不存在的节点视为 false）。绝不能让 None
        # 以 `str(None)` 继续参与 ==/!=/contains 比较 —— `str(None) != 'true'`
        # 与 `'one' in str(None)` 都是 True，会把本该跳过的节点误放行（假阳性）。
        if actual is None:
            return False

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
            if 'depends' not in norm and 'deps' in norm:
                norm['depends'] = norm['deps']
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
            for dep in (node.get('depends') or node.get('deps') or []):
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
    from .indexer import load_index, _repo_root

    idx = load_index(meta_dir)
    if workflow_id not in idx['actions']:
        raise ActionError('workflow_not_found', f'工作流不存在: {workflow_id}')

    entry = idx['actions'][workflow_id]
    # 索引条目字段是 'path'（build_index 写入）；'file_path' 仅为历史别名。
    # _meta/actions.index.json 是 git 跟踪文件：仓库一旦搬家 / 克隆 / 改
    # ACTUS_REPO_ROOT，索引里烧死的绝对路径即失效。故一律相对**当前**仓库根
    # 重新锚定；锚不上就现扫 actions/ 重建真实路径，绝不照抄旧路径去 open。
    raw_path = entry.get('path') or entry.get('file_path') or ''
    repo_root = os.environ.get('ACTUS_REPO_ROOT') or _repo_root()

    def _candidates(p: str):
        out = []
        if not p:
            return out
        if os.path.isabs(p):
            out.append(p)
            # 旧绝对路径：截取 'actions/...' 尾巴按当前根重锚
            rel = p.replace('\\', '/')
            k = rel.find('/actions/')
            if k != -1:
                out.append(os.path.join(repo_root, rel[k + 1:].replace('/', os.sep)))
        else:
            out.append(os.path.join(repo_root, p.replace('/', os.sep)))
        return out

    action_path = next((c for c in _candidates(raw_path) if os.path.isfile(c)), '')
    if not action_path:
        # 现扫重建：以当前根的 actions/ 为准取真实文件路径（只读，不落缓存）
        try:
            from .indexer import scan_actions
            fresh = scan_actions(os.path.join(repo_root, 'actions'),
                                 validate=False, use_cache=False).get(workflow_id)
            fresh_path = getattr(fresh, 'path', '') if fresh is not None else ''
            if fresh_path and os.path.isfile(fresh_path):
                action_path = fresh_path
        except Exception:  # noqa: BLE001
            action_path = ''
    if not action_path or not os.path.isfile(action_path):
        raise ActionError('workflow_source_missing',
                          f'工作流源文件不存在: {workflow_id} -> {raw_path!r}')
    action = parse_cfg_from_file(action_path)
    wf = Workflow(action)

    errors = wf.validate()
    if errors:
        raise ActionError('workflow_invalid', f'工作流校验失败: {"; ".join(errors)}')

    return wf.execute(meta_dir, max_workers, confirmed)
