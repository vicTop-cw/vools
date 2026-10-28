"""selfdrive_worker.py — 把 selfdrive 的节点接到**真实 Actus 引擎**上执行。

`selfdrive.py` 的默认 worker 是确定性 echo（便于单测）；本模块补上"真实执行器"，
使自驱式递归拆解不只是分类器/空转，而是真正调用 `actuscore.execute` 跑动作，
并用 `omega` 的 spec 做 Ω-gate 强验证。

两个角色
--------
- **worker(node) -> dict**：按 `assign` 把节点映射到一个真实动作（id + params），
  经 `actuscore.execute` 执行，返回引擎的结构化出参（status/result/error/...）。
- **spec_resolver(node) -> path|None**：给出该节点对应动作的 Ω spec 路径，
  供 `SelfDrive` 做强验证。未显式指定时按动作 id 自动查找。

映射策略
--------
`assign` 是一个 `Callable[[node], Optional[NodeAction]]`。内置三种便捷构造：
- `static_assign(mapping, default=None)`：按节点 goal 的子串匹配。
- `leaf_assign(nodes, actions)`：把动作按**叶子顺序**依次绑定（调用方已持有节点表）。
- `order_assign(actions)`：按**执行先后**依次绑定，无需预知节点表——`ActionWorker.from_plan(plan)`
  即走这条。

现状（第 11 轮审计修正后的事实）
---------------------------------
- **有什么**：真实执行链路已实现并被 CLI 接线 ——
  `actus selfdrive run <goal> [--plan JSON] [--plan-file FILE] [--worker action]`
  走 `ActionWorker.from_plan(...)`（`--worker action`），`--worker echo`（默认）
  仍是不触碰引擎的确定性空跑；`actus selfdrive status [run_id]` 读快照。
- **没有什么**：**MCP 仍无 selfdrive 入口**（`grep actus_selfdrive mcp_server.py`
  0 命中）；旧 docstring 曾把"MCP 接入点"写成既成事实，属不实描述（已修正）。
- **计划中（未实现）**：MCP `actus_selfdrive_run{plan}`。

用法
----
    from . import selfdrive, selfdrive_worker as sdw

    plan = sdw.leaf_assign(nodes, [
        sdw.NodeAction('actus.text.encode_convert', {'mode': 'b64_encode', 'text': 'hi'}),
        sdw.NodeAction('actus.system.checksum', {'text': 'hi', 'algo': 'md5'}),
    ])
    ew = sdw.ActionWorker(plan, actions_dir=..., meta_dir=...)
    run = selfdrive.SelfDrive('编码并校验', max_depth=0,
                              worker=ew.worker, spec_resolver=ew.spec_resolver,
                              strong=True)
    snap = run.run()
"""


import json
from vools.core.dataclass_compat import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from . import omega as _omega

__all__ = ['NodeAction', 'ActionWorker', 'static_assign', 'leaf_assign',
           'plan_from_json', 'order_assign']


@dataclass
class NodeAction:
    """一个节点要执行的真实动作。"""
    action_id: str
    params: Dict[str, Any] = field(default_factory=dict)
    spec_path: Optional[str] = None


def _leaves(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [n for n in nodes if not n.get('children')]


def leaf_assign(nodes: List[Dict[str, Any]],
                actions: List[NodeAction]) -> Callable[[Dict[str, Any]], Optional[NodeAction]]:
    """把 actions 按叶子顺序依次绑定；叶子多于动作时，末尾复用最后一个。"""
    leaves = _leaves(nodes)

    def assign(node: Dict[str, Any]) -> Optional[NodeAction]:
        try:
            idx = next(i for i, n in enumerate(leaves) if n['id'] == node['id'])
        except StopIteration:
            return None
        if not actions:
            return None
        return actions[min(idx, len(actions) - 1)]

    return assign


def static_assign(mapping: Dict[str, NodeAction],
                  default: Optional[NodeAction] = None
                  ) -> Callable[[Dict[str, Any]], Optional[NodeAction]]:
    """按 goal 子串匹配（首个命中），未命中时回退 default。"""

    def assign(node: Dict[str, Any]) -> Optional[NodeAction]:
        goal = node.get('goal', '')
        for needle, act in mapping.items():
            if needle in goal:
                return act
        return default

    return assign


def plan_from_json(plan: Union[str, list, tuple]) -> List[NodeAction]:
    """把外部计划（JSON 字符串 / 数组）转为 NodeAction 列表。

    项形态：`"action.id"` 或 `{"action"|"action_id": str, "params": {},
    "spec_path": str}`。出错抛 ValueError 并带上出错下标，供调用方转成
    param_invalid 而不是把异常抛进控制器。
    """
    raw = plan
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f'plan 不是合法 JSON: {e}') from None
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f'plan 必须是数组，收到 {type(raw).__name__}')
    out: List[NodeAction] = []
    for i, item in enumerate(raw):
        if isinstance(item, str):
            if not item.strip():
                raise ValueError(f'plan[{i}] 动作 id 不能为空')
            out.append(NodeAction(item.strip()))
            continue
        if isinstance(item, dict):
            aid = item.get('action') or item.get('action_id')
            if not isinstance(aid, str) or not aid.strip():
                raise ValueError(f'plan[{i}] 缺少 action/action_id 字符串键')
            params = item.get('params')
            if params is None:
                params = {}
            if not isinstance(params, dict):
                raise ValueError(f'plan[{i}].params 必须是对象，'
                                 f'收到 {type(params).__name__}')
            spec = item.get('spec_path')
            if spec is not None and not isinstance(spec, str):
                raise ValueError(f'plan[{i}].spec_path 必须是字符串，'
                                 f'收到 {type(spec).__name__}')
            out.append(NodeAction(aid.strip(), params,
                                  (spec.strip() or None) if spec else None))
            continue
        raise ValueError(f'plan[{i}] 只能是字符串或对象，收到 {type(item).__name__}')
    return out


def order_assign(actions: List[NodeAction]) -> Callable[[Dict[str, Any]], Optional[NodeAction]]:
    """按节点出现顺序绑定动作；耗尽后复用最后一项。

    与 `leaf_assign` 的区别：不需要预先拿到节点表——公共入口（CLI/MCP）在
    拆解发生前只有计划，节点是运行时才产生的。

    必须**按节点 id 幂等**：控制器对同一节点会先 `worker()` 后 `spec_resolver()`，
    纯计数绑定会让同一节点两次拿到不同动作（执行 A、却按 B 的 spec 验证）。
    """
    acts = list(actions)
    cache: Dict[Any, NodeAction] = {}
    state = {'i': 0}

    def assign(node: Dict[str, Any]) -> Optional[NodeAction]:
        if not acts:
            return None
        key = node.get('id') if isinstance(node, dict) else None
        if key is not None and key in cache:
            return cache[key]
        act = acts[min(state['i'], len(acts) - 1)]
        state['i'] += 1
        if key is not None:
            cache[key] = act
        return act

    return assign


class ActionWorker:
    """把 selfdrive 节点映射到真实 Actus 动作并执行。"""

    def __init__(self,
                 assign: Callable[[Dict[str, Any]], Optional[NodeAction]],
                 actions_dir: Optional[str] = None,
                 meta_dir: Optional[str] = None,
                 artifacts_dir: Optional[str] = None,
                 force: bool = False,
                 confirmed: bool = False,
                 execute_fn: Optional[Callable[..., dict]] = None,
                 auto_spec: bool = True):
        self.assign = assign
        self.actions_dir = actions_dir
        self.meta_dir = meta_dir
        self.artifacts_dir = artifacts_dir
        self.force = force
        self.confirmed = confirmed
        self.auto_spec = auto_spec
        self._execute = execute_fn  # 可注入（测试/替身）；None 时惰性取 actuscore.execute

    @classmethod
    def from_plan(cls, plan: Union[str, list, tuple], **kw) -> 'ActionWorker':
        """由外部计划构造 worker：按执行顺序绑定动作（CLI/MCP 公共入口用）。"""
        return cls(order_assign(plan_from_json(plan)), **kw)

    # ── engine 调用（惰性导入，便于隔离测试）──
    def _execute_fn(self) -> Callable[..., dict]:
        if self._execute is not None:
            return self._execute
        from . import execute  # actuscore.execute
        return execute

    def _node_action(self, node: Dict[str, Any]) -> Optional[NodeAction]:
        act = self.assign(node)
        if isinstance(act, NodeAction):
            return act
        if isinstance(act, str):  # 允许直接给 action_id
            return NodeAction(act)
        if isinstance(act, dict):  # 允许 {action_id, params, spec_path}
            return NodeAction(act.get('action_id') or act.get('action'),
                              act.get('params') or {}, act.get('spec_path'))
        return None

    # ── worker ──
    def worker(self, node: Dict[str, Any]) -> Dict[str, Any]:
        act = self._node_action(node)
        if act is None:
            return {'status': 'failed',
                    'error': {'code': 'no_action_assigned',
                              'message': f'节点 {node.get("id")} 未映射到任何动作'}}
        try:
            result = self._execute_fn()(
                act.action_id, act.params,
                confirmed=self.confirmed,
                actions_dir=self.actions_dir,
                meta_dir=self.meta_dir,
                artifacts_dir=self.artifacts_dir,
                force=self.force)
        except Exception as e:  # noqa: BLE001
            return {'status': 'failed',
                    'error': {'code': 'executor_error',
                              'message': f'{type(e).__name__}: {e}'}}
        if not isinstance(result, dict):
            result = {'status': 'ok', 'value': result}
        # 标注来源动作，便于追溯
        result.setdefault('action', act.action_id)
        return result

    # ── spec resolver ──
    def spec_resolver(self, node: Dict[str, Any]) -> Optional[str]:
        act = self._node_action(node)
        if act is None:
            return None
        if act.spec_path:
            return act.spec_path
        if not self.auto_spec:
            return None
        try:
            return _omega._find_omega_spec(act.action_id, self.actions_dir)
        except Exception:  # noqa: BLE001
            return None
