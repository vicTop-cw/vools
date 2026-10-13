"""动作执行（docs/02 §4 数据流、docs/03 §7 出参契约、docs/08 §4 生命周期）。

执行链路：
  exec_id 分配 → pending → validating（契约/依赖/入参）
  → awaiting_confirmation（audit 未确认时）→ running（vools 逐块执行）
  → succeeded / failed / cancelled

出参统一为 {status, data, error}（docs/03 §7.2）：
  status ∈ ok / failed / cancelled / awaiting_confirmation
stdout/stderr/exit_code 为旁路信息，仅入执行记录。
"""

__all__ = ['execute', 'preview', 'new_exec_id']

import json
import os
import secrets
import threading
from datetime import datetime, timezone, timedelta

from .errors import ActionError
from .model import Action
from .process_state import PROCESS_STATE_LOCK
from .validate import load_and_validate, validate_graph
from .indexer import scan_actions
from .trust import decide
from . import records
from .indexer import scan_actions
from .omega import verify_output, compute_output_fingerprint, _find_omega_spec
from .concurrency import get_manager
from .dependency import get_resolver, DependencyResolver

_TZ = timezone(timedelta(hours=8))

# 并发保护：ACTUS_PARAMS / ACTUS_EXEC_ID 等运行时上下文经进程级 os.environ
# 传给 vools 子进程；工作流可并行提交同层节点（ThreadPoolExecutor）。不加锁时
# 并发注入会互相覆盖（实测：data_pipeline 的 encode_a/encode_b 双双拿到同一份
# params）。_run_blocks 在「注入 → run_md 启动子进程」期间持有本锁。
# 锁本体在 process_state 里，与 runtimes.PythonRuntime 共用同一把（BUG-0023）——
# 两条路径改的是同一份 os.environ，各持一把本地锁等于没锁。

# 记录/回传里每块 stdout 的保留长度。**只**用于截断留痕，不参与出参解析
# （解析用原文，见 _run_blocks）—— 两者共用一个字面量正是 BUG-0016 的形状。
_STDOUT_KEEP = 4000

# 入参嵌套深度上限（BUG-0017）。实测口径：仓库 23 份 Ω spec 的 74 组入参里，
# 最深只有 2 层（tests/ 里的 params 字面量同样最深 2 层）—— 64 层是 32 倍余量，
# 既挡得住「5000 层嵌套把 RecursionError 抛出入口」，又不会拒掉任何真实动作入参。
# 只限深度不限节点数：爆栈只取决于嵌套深度，加节点上限等于凭白拒掉合法的大 payload。
_MAX_PARAM_DEPTH = 64

_STATUS_MAP = {
    'succeeded': 'ok',
    'failed': 'failed',
    'cancelled': 'cancelled',
    'awaiting_confirmation': 'awaiting_confirmation',
}


def new_exec_id() -> str:
    """docs/08 §4：YYYYMMDD-<6位随机hex>。"""
    today = datetime.now(_TZ).strftime('%Y%m%d')
    return f'{today}-{secrets.token_hex(3)}'


def _meta_dirs(meta_dir=None, artifacts_dir=None):
    """解析 _meta 与 artifacts 目录。

    传入 meta_dir 而未传 artifacts_dir 时，artifacts 取 meta_dir 的同级
    artifacts（临时仓库隔离的关键：测试写 tmp_path 不落真实仓库）。
    """
    from .indexer import _repo_root
    root = _repo_root()
    meta = meta_dir or os.path.join(root, '_meta')
    if artifacts_dir is None:
        if meta_dir is not None:
            artifacts = os.path.join(os.path.dirname(os.path.abspath(meta_dir)), 'artifacts')
        else:
            artifacts = os.path.join(root, 'artifacts')
    else:
        artifacts = artifacts_dir
    return meta, artifacts


def _validate_params(action: Action, params: dict) -> None:
    """按 args JSON Schema 校验入参（docs/03 §7.1），非法抛 param_invalid。"""
    schema = action.args_schema
    if schema is None:
        return
    try:
        import jsonschema
        jsonschema.validate(instance=params, schema=schema)
    except Exception as e:
        msg = getattr(e, 'message', str(e))
        raise ActionError('param_invalid', f'入参校验失败: {msg}',
                          {'schema': schema}) from e


def _inject_params_into_body(action: Action, params: dict) -> str:
    """把入参以 __actus_params 注入执行环境。

    vools 的 python 块经 exec 执行，这里在正文最前追加一段引导代码：
    定义 __actus_params 变量与 __actus_result 输出通道，供动作代码读写。
    """
    bootstrap = (
        '\n\n```python #!run tag=__actus_bootstrap skip\n'
        '# Actus 注入：参数与结果通道（本块不单独执行）\n'
        '```\n'
    )
    # 注入通过环境变量传递更稳妥：ACTUS_PARAMS (JSON) —— vools _execute_python
    # 的 exec_env 来自 config['env']，这里直接在 md 顶部加一个 python 配置块不可行，
    # 故采用 wrapper：入口块执行前由 executor 将参数写入全局 config env。
    return action.body + bootstrap


def _payload_depth(obj) -> int:
    """求嵌套深度。**刻意用迭代而不是递归**：量深参的尺子如果自己也递归，
    它就是第一个被同一份入参炸掉的东西（BUG-0017 的现场正是 json.dumps 递归爆栈）。
    """
    maxd = 0
    stack = [(obj, 1)]
    while stack:
        cur, d = stack.pop()
        if d > maxd:
            maxd = d
        if isinstance(cur, dict):
            stack.extend((v, d + 1) for v in cur.values())
        elif isinstance(cur, (list, tuple)):
            stack.extend((v, d + 1) for v in cur)
    return maxd


def execute(action_id: str, params: dict = None,
            confirmed: bool = False, meta_dir: str = None,
            actions_dir: str = None, force: bool = False,
            artifacts_dir: str = None, preparsed_action: 'Action' = None) -> dict:
    """执行一个动作，返回 docs/03 §7.2 结构化出参。

    confirmed=True 表示人类已通过确认通道放行（audit 级需要）。
    meta_dir/artifacts_dir 可覆盖留痕与产物落点（临时仓库隔离）。
    preparsed_action：已解析好的 Action（零散动作专用，docs/41 §5 主题 C）。
      零散动作在**任意路径**，且缺省字段（trust=audit / visibility=private，
      docs/41 §C1）是在解析后补上的；execute 若再从磁盘 re-parse，补上的缺省值
      当场丢失 → 校验报 trust 缺失。传进来即用同一份对象，缺省值不再被抹掉。
      仍然走完整的 validating/trust/sandbox/Ω 门禁 —— 只是"对象从哪来"变了。
      **名字不能叫 action_obj**：下面依赖预检那段有同名本地变量 `action_obj = None`，
      参数会被当场覆盖（实测踩到过）。
    全程留痕：_meta/runs/<exec_id>.json + status.json + 追加式日志。
    """
    params = params if params is not None else {}

    # 入参深度闸门（BUG-0017）：位置必须在建 record 之前 —— record['params']、
    # _validate_params 与 _run_blocks 里的 json.dumps(params) 都会把这份入参整个递归
    # 走一遍，5000 层嵌套能让 RecursionError 从 PROCESS_STATE_LOCK 临界区里穿出出入口，
    # 而引擎对外承诺的是 docs/03 §7.2 的结构化回执（CLI/MCP 拿到 traceback 就没法分流）。
    depth = _payload_depth(params)
    if depth > _MAX_PARAM_DEPTH:
        return {
            'status': 'failed',
            'data': None,
            'error': {
                'code': 'param_invalid',
                'message': f'入参嵌套过深（深度 {depth} > 上限 {_MAX_PARAM_DEPTH}），已按契约拒绝',
                'details': {'depth': depth, 'max_depth': _MAX_PARAM_DEPTH},
            },
        }

    meta_dir, artifacts_dir = _meta_dirs(meta_dir, artifacts_dir)
    exec_id = new_exec_id()

    # ── 依赖检查（执行前）──
    action_obj = None
    dep_check = None
    try:
        from .indexer import get_action
        action_obj = load_and_validate(get_action(action_id, actions_dir).path)
        if action_obj.dependencies:
            resolver = DependencyResolver(actions_root=actions_dir)
            dep_states = []
            lazy_hints = []
            hard_missing = []
            for dep in action_obj.dependencies:
                chk = resolver.check_dep(dep)
                dep_type = getattr(getattr(dep, 'type', ''), 'value', getattr(dep, 'type', ''))
                strategy = getattr(getattr(dep, 'strategy', None), 'value', None)
                ephemeral_cmd = getattr(chk, 'ephemeral_cmd', '')
                dep_states.append({
                    'name': dep.name,
                    'type': dep_type,
                    'strategy': strategy,
                    'required': dep.required,
                    'satisfied': chk.satisfied,
                    'message': chk.message,
                    'fix_command': chk.fix_command,
                    'ephemeral_cmd': ephemeral_cmd,
                })
                if chk.satisfied:
                    continue
                # D3 懒加载：hint/ephemeral/download 策略不硬失败，仅附提示
                actionable = bool(
                    chk.fix_command or ephemeral_cmd
                    or getattr(chk, 'download_url', '')
                )
                if strategy is not None:
                    lazy = strategy != 'fail'
                else:
                    lazy = actionable or dep_type in (
                        'system', 'python', 'npm', 'lang', 'mcp')
                if lazy:
                    lazy_hints.append({
                        'name': chk.name,
                        'type': dep_type,
                        'strategy': strategy,
                        'message': chk.message,
                        'fix_command': chk.fix_command,
                        'ephemeral_cmd': ephemeral_cmd,
                    })
                elif dep.required:
                    hard_missing.append({'name': chk.name, 'message': chk.message})
            dep_check = {
                'satisfied': not hard_missing,
                'deps': dep_states,
                'lazy': lazy_hints,
                'missing': hard_missing,
            }
            if hard_missing and not force:
                result = {
                    "status": "failed",
                    "error": {
                        "code": "deps_missing",
                        "message": "必需依赖缺失，可使用 force=True 强制执行",
                        "details": {"missing": hard_missing},
                    },
                    "deps": dep_check
                }
                return result
    except Exception:
        # 依赖预检为尽力而为：解析失败不在此处定论，交由主流程 validating 阶段给结构化错误
        action_obj = None
        dep_check = None
        pass

    record = {
        'exec_id': exec_id,
        'action': action_id,
        'params': params,
        'confirmed': bool(confirmed),
        'state_transitions': [],
        'blocks': [],
        'artifacts': [],
        'sandboxed': False,
    }

    def transit(state: str):
        record['state_transitions'].append(
            {'state': state, 'at': datetime.now(_TZ).isoformat(timespec='seconds')})

    def finish(result: dict) -> dict:
        # 先补全 exec_id 再落盘，保证记录里的 result 自含标识
        result['exec_id'] = exec_id
        # D3：懒加载策略缺失的依赖不阻断执行，以提示形式随结果返回
        if dep_check and dep_check.get('lazy'):
            result['deps_hints'] = dep_check['lazy']
        record['result'] = result
        # ── 释放并发槽位 ──
        if record.get('concurrency', {}).get('max', 0) > 0:
            mgr_release = get_manager()
            mgr_release.release_slot(action_id, exec_id)
            result['concurrency'] = {
                'max': record['concurrency']['max'],
                'released': True,
                'remaining': mgr_release.get_running_count(action_id)
            }
        # ── Ω-gate 验证（金条八：任何产出必须过 Ω-gate）──
        spec_path = _find_omega_spec(action_id, actions_dir)
        if spec_path and result.get('status') in ('ok', 'partial'):
            try:
                omega_report = verify_output(spec_path, result)
                result['omega'] = omega_report
                if omega_report.get('status') == 'spec_error':
                    # 「无法评估」不是「过了门禁」（BUG-0015）。spec 不合格时 verify_output
                    # 回的是 {'status':'spec_error','errors':[...]}，**没有 gate 键**，
                    # 原先 `get('gate', {}).get('passed', True)` 的缺省 True 正好把它读成通过
                    # —— 契约坏掉时金条八静默放行，比判错更糟因为它不留痕。
                    errs = omega_report.get('errors') or []
                    result['status'] = 'failed'
                    result['error'] = {
                        'code': 'omega_spec_invalid',
                        'message': f"Ω 契约不可评估（spec 不合格）：{'; '.join(str(e) for e in errs[:3])}",
                        'details': omega_report,
                    }
                elif not omega_report.get('gate', {}).get('passed', False):
                    # 缺省值取 False：走到这里 gate 必然存在（pass/fail 两条都带），
                    # 但万一将来新增第三种回包形状，宁可判不过也不放行。
                    result['status'] = 'failed'
                    result['error'] = {
                        'code': 'omega_gate_failed',
                        'message': f"Ω-gate 验证失败，准确率 {omega_report['gate'].get('accuracy', 0)}% < 100%",
                        'details': omega_report
                    }
            except Exception as e:
                # 原本 `except Exception: pass` 把坏 spec 抹平成「这个动作没配 spec」——
                # 两种情况的回执完全同形，调用方无从分辨。现在既留痕也判不过。
                result['omega'] = {
                    'status': 'spec_error',
                    'errors': [f'{type(e).__name__}: {e}'],
                    'spec_path': spec_path.replace(os.sep, '/'),
                }
                result['status'] = 'failed'
                result['error'] = {
                    'code': 'omega_spec_invalid',
                    'message': f'Ω spec 加载失败：{type(e).__name__}: {e}',
                    'details': result['omega'],
                }
        record_path = records.write_run_record(meta_dir, record)
        result['record'] = record_path.replace(os.sep, '/')
        records.update_status(meta_dir, exec_id, action_id,
                              result['status'],
                              (result.get('error') or {}).get('message'))
        records.append_log(meta_dir, f"{exec_id} {action_id} -> {result['status']}")

        # ── 事件总线通知 (Phase G5) ──
        try:
            from .eventbus import EventType, get_event_bus
            bus = get_event_bus()
            if result['status'] == 'ok':
                bus.publish(EventType.ACTION_COMPLETED, {
                    'action_id': action_id,
                    'exec_id': exec_id,
                    'params': params,
                    'result': result.get('data'),
                }, source='executor')
            elif result['status'] == 'failed':
                bus.publish(EventType.ACTION_FAILED, {
                    'action_id': action_id,
                    'exec_id': exec_id,
                    'params': params,
                    'error': result.get('error'),
                }, source='executor')
        except Exception:
            pass  # 事件总线异常不阻塞执行

        return result

    try:
        # ── pending ──
        transit('pending')

        # ── validating ──
        transit('validating')
        if preparsed_action is not None:
            action = preparsed_action
        else:
            action = load_and_validate(
                _resolve_path(action_id, actions_dir)) if actions_dir else None
            if action is None:
                action = _get_validated(action_id)

        _validate_params(action, params)

        # 依赖图校验（含本动作的 deps）
        all_actions = scan_actions(actions_dir, validate=False)
        sub = {aid: a for aid, a in all_actions.items()
               if aid == action_id or aid in (action.meta.get('deps') or [])}
        validate_graph(sub)

        # ── 可见性门禁（docs/41 §B1）：只判新增的 internal / gated 两级 ──
        _visibility_gate(action, action_id, exec_id)

        # ── trust 判定 ──
        strategy = decide(action.trust, confirmed=confirmed)
        record['trust'] = action.trust
        record['strategy'] = strategy

        if strategy == 'need_confirm':
            # docs/07 §2：改动型动作等人类确认，展示完整待执行明细
            transit('awaiting_confirmation')
            record['pending_ops'] = _pending_ops(action, params)
            return finish({
                'status': 'awaiting_confirmation',
                'data': {
                    'exec_id': exec_id,
                    'action': action_id,
                    'trust': action.trust,
                    'pending_ops': record['pending_ops'],
                    'hint': '该动作为 audit 级，需人类确认后执行：actus run --confirm 或 MCP 确认通道',
                },
                'error': None,
            })

        # ── 并发控制：获取执行槽位 ──
        mgr = get_manager()
        max_inst = action.max_instances
        if max_inst > 0:
            # 注册动作并发配置
            mgr.register_action(action_id, max_inst)
            # 尝试获取槽位（等待 30 秒）
            acquired, reason = mgr.acquire_slot(action_id, exec_id, params, timeout=30.0)
            if not acquired:
                transit('failed')
                return finish({
                    'status': 'failed',
                    'data': None,
                    'error': {
                        'code': 'concurrency_limit',
                        'message': f'动作 {action_id} 并发限制: {reason}',
                        'details': {
                            'max_instances': max_inst,
                            'running': mgr.get_running_count(action_id),
                            'waiting': mgr.get_waiting_count(action_id),
                        }
                    }
                })
            record['concurrency'] = {'max': max_inst, 'acquired': True}
        else:
            record['concurrency'] = {'max': 0, 'acquired': True, 'note': '无上限'}

        # ── 幂等检查（docs/08 §4）：idempotency_key_from 指向入参字段 ──
        replay = _idempotent_replay(meta_dir, action, params)
        if replay is not None:
            transit('running')
            transit('succeeded')
            record['idempotent_replay_of'] = replay.get('exec_id')
            data = dict(replay.get('data') or {})
            data['idempotent_replay'] = True
            data['replay_of'] = replay.get('exec_id')
            return finish({
                'status': 'ok',
                'data': data,
                'error': None,
            })

        # ── running ──
        transit('running')
        result = _run_blocks(action, params, exec_id,
                             artifacts_dir, force=force,
                             sandboxed=(strategy == 'sandbox'),
                             meta_dir=meta_dir)
        record['sandboxed'] = strategy == 'sandbox'
        # 产物登记（docs/04 §3）与幂等缓存（docs/08 §4）
        if result.get('status') == 'ok':
            _register_artifacts(meta_dir, action, exec_id,
                                result.get('artifacts') or [])
            _idempotent_store(meta_dir, action, params, exec_id, result)
        return finish(result)

    except ActionError as e:
        transit('failed')
        return finish({'status': 'failed', 'data': None, 'error': e.to_payload()})
    except Exception as e:  # noqa: BLE001 —— 收敛为 internal，不静默
        transit('failed')
        return finish({'status': 'failed', 'data': None,
                       'error': {'code': 'internal', 'message': str(e),
                                 'details': {'type': type(e).__name__}}})


def _resolve_path(action_id: str, actions_dir: str = None) -> str:
    """actions_dir 模式下按 id 匹配文件；否则交由索引解析。"""
    from .indexer import get_action
    return get_action(action_id, actions_dir).path


# ── 幂等键（docs/08 §4）─────────────────────────────────

_IDEMPOTENT_TTL_SECONDS = 300  # 默认 5 分钟内同键直接复用上次结果


def _idempotency_file(meta_dir: str) -> str:
    return os.path.join(meta_dir, 'idempotency.json')


def _idempotency_load(meta_dir: str) -> dict:
    path = _idempotency_file(meta_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _idempotent_key(action: Action, params: dict):
    """返回 (action_id, key_value) 或 None（动作未声明幂等键/入参缺字段）。"""
    field = action.meta.get('idempotency_key_from')
    if not field or not isinstance(params, dict):
        return None
    value = params.get(field)
    if value is None:
        return None
    return (action.id, str(value))


def _idempotent_replay(meta_dir: str, action: Action, params: dict):
    """同幂等键且未过 TTL → 返回上次成功结果；否则 None。"""
    from datetime import datetime as _dt
    kv = _idempotent_key(action, params)
    if kv is None:
        return None
    store = _idempotency_load(meta_dir)
    entry = store.get(f'{kv[0]}::{kv[1]}')
    if not entry:
        return None
    try:
        created = _dt.fromisoformat(entry['at'])
        age = (datetime.now(_TZ) - created).total_seconds()
    except (KeyError, ValueError):
        return None
    if age > _IDEMPOTENT_TTL_SECONDS:
        return None
    record = records.load_run_record(meta_dir, entry['exec_id'])
    if record is None or record.get('result', {}).get('status') != 'ok':
        return None
    return record['result']


def _idempotent_store(meta_dir: str, action: Action, params: dict,
                      exec_id: str, result: dict) -> None:
    kv = _idempotent_key(action, params)
    if kv is None:
        return
    store = _idempotency_load(meta_dir)
    store[f'{kv[0]}::{kv[1]}'] = {
        'exec_id': exec_id, 'at': datetime.now(_TZ).isoformat(timespec='seconds')}
    path = _idempotency_file(meta_dir)
    os.makedirs(meta_dir, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def _get_validated(action_id: str) -> Action:
    from .validate import load_and_validate
    from .indexer import get_action
    return load_and_validate(get_action(action_id).path)


def _visibility_gate(action: Action, action_id: str, exec_id: str,
                     gated_key: str = None, gated_store=None) -> None:
    """执行前的可见性门禁（docs/41 §B1）。

    **只判新增的 internal / gated 两级，既有四级（public/unlisted/private/team）
    一律原样放行。** 这不是偷懒，是兼容性判据：实测这四级在现行执行链上从来没有
    被门禁过（executor 早前根本不 import visibility），若在这里给它们补上判据，
    `visibility: private` 的既有动机会当场开始报 `Private action not found`
    （私有索引里根本没有它们的记录），属于凭空造回归。新级别的收紧与旧级别的行为
    不变是两件事，分开做才看得见。

    internal 的放行判据是**物理落位**（`actions/system/_internal/`，docs/41 §B1）：
    落在该目录下才算引擎内部路由；把任意动作标成 `visibility: internal` 想借此
    绕过市场/签名链路的，这里当场拒掉 —— 落位是权威，声明只是意图。

    gated 的放行判据是密钥：显式参数 → `ACTUS_GATED_KEY` 环境变量 → vault，
    三者都取不到或校验不过 → `auth_required`（docs/41 §B2.3）。密钥明文只在这里
    过一遍，不进 record、不进日志。
    """
    visibility = (action.meta.get('visibility') or '').strip().lower()

    if visibility == 'internal':
        from .visibility import is_internal_path
        if not is_internal_path(action.path):
            record_gate(action_id, visibility, exec_id, granted=False)
            raise ActionError(
                'visibility_denied',
                f"internal 动作 '{action_id}' 未落在 _internal/ 目录，"
                f"拒绝按内部路由执行（当前路径：{action.path}）",
                {'visibility': visibility, 'path': action.path})
        record_gate(action_id, visibility, exec_id, granted=True)
        return

    if visibility == 'gated':
        from .visibility import AUTH_REQUIRED, GatedKeyStore
        key = gated_key or os.environ.get('ACTUS_GATED_KEY', '')
        if not key:
            try:
                from .vault import get_key
                key = get_key('gated_key',
                              meta_dir=os.environ.get('ACTUS_META_DIR', '')) or ''
            except Exception:       # noqa: BLE001 —— vault 不可用等同"没有密钥"
                key = ''
        if not key:
            record_gate(action_id, visibility, exec_id, granted=False)
            raise ActionError(
                'auth_required',
                f"动作 '{action_id}' 为 gated 可见性，执行需授权密钥"
                f"（--key / ACTUS_GATED_KEY / vault gated_key 三者之一）",
                {'visibility': visibility})
        repo = action.meta.get('repo') or ''
        # 仓储可注入：默认落 ~/.actus/gated_keys.json（与 VisibilityEngine 同根）。
        # 取不到仓储（文件损坏等）一律按"未授权"拒 —— fail-closed，不静默放行。
        try:
            store = gated_store if gated_store is not None else GatedKeyStore()
        except RuntimeError as exc:
            record_gate(action_id, visibility, exec_id, granted=False)
            raise ActionError('auth_required', str(exc), {'visibility': visibility})
        if not store.verify(key, action_id=action_id, repo=repo):
            record_gate(action_id, visibility, exec_id, granted=False)
            raise ActionError(
                'auth_required',
                f"动作 '{action_id}' 的授权密钥无效或已被轮换撤销",
                {'visibility': visibility, 'reason': AUTH_REQUIRED})
        record_gate(action_id, visibility, exec_id, granted=True)
        return

    # 既有四级（public/unlisted/private/team）在现行执行链上没有任何门禁，这里也
    # **不做判定也不写审计** —— 若在此写一条 granted=True，审计记录会谎称"做过
    # 可见性校验并通过"，而事实是一个字节都没查。只记录真实发生的判定。


def record_gate(action_id: str, visibility: str, exec_id: str,
                granted: bool) -> None:
    """可见性判定留痕（不含任何密钥值）。写失败不影响判定结果。"""
    try:
        from .visibility import SecretAuditor
        SecretAuditor().record_visibility(
            action_id=action_id, visibility=visibility,
            exec_id=exec_id, granted=granted)
    except Exception:               # noqa: BLE001 —— 审计是旁路，不反向决定授权
        pass


def _pending_ops(action: Action, params: dict) -> list:
    """从动作声明推断待执行操作明细（docs/07 §2 确认通道展示用）。"""
    ops = []
    perms = action.meta.get('permissions') or []
    perm_desc = {
        'files:write': {'op': 'write', 'impact': '写入文件'},
        'files:delete': {'op': 'delete', 'impact': '删除文件'},
        'files:read': {'op': 'read', 'impact': '读取文件'},
        'net:connect': {'op': 'net', 'impact': '对外网络连接'},
        'net:listen': {'op': 'listen', 'impact': '监听端口'},
        'process:spawn': {'op': 'process', 'impact': '启动子进程'},
        'ui:notify': {'op': 'notify', 'impact': '弹出通知'},
        'ui:control': {'op': 'ui_control', 'impact': '控制键鼠/剪贴板（UI 自动化）'},
        'sys:settings': {'op': 'settings', 'impact': '修改系统设置'},
    }
    for p in perms:
        d = dict(perm_desc.get(p, {'op': p, 'impact': '未知影响'}))
        d['permission'] = p
        ops.append(d)
    if not ops:
        ops = [{'op': 'run', 'impact': '执行动作代码块（无声明权限）'}]
    return ops


def _sanitize_path_env() -> None:
    """PATH 去重瘦身 + System32 前置（执行环境保障）。

    背景：vools import 链会向 PATH 大量 prepend 编译器路径，把 PATH 撑过
    cmd.exe 约 8191 字符的搜索缓冲，System32 被挤出搜索范围，动作里的
    os.popen/subprocess 按相对名调用系统命令（如 wsl.exe）会报
    "not recognized"。此处只做保序去重与前移，不删除任何已有目录。
    """
    path = os.environ.get('PATH', '')
    if not path or len(path) <= 8000:
        return
    sys32 = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
    seen, cleaned = set(), []
    for it in path.split(';'):
        k = it.strip().lower().rstrip('\\')
        if k and k not in seen:
            seen.add(k)
            cleaned.append(it)
    cleaned = [p for p in cleaned if p.strip().lower().rstrip('\\') != sys32.lower()]
    cleaned.insert(0, sys32)
    os.environ['PATH'] = ';'.join(cleaned)


def _env_snapshot() -> dict:
    return dict(os.environ)


def _env_restore(snap: dict) -> None:
    """把进程环境逐字回写到快照那一刻（先删新增，再复原改动/缺失）。"""
    for key in [k for k in os.environ if k not in snap]:
        del os.environ[key]
    for key, value in snap.items():
        if os.environ.get(key) != value:
            os.environ[key] = value


def _run_blocks(action: Action, params: dict, exec_id: str,
                artifacts_dir: str, force: bool = False,
                sandboxed: bool = False, meta_dir: str = None) -> dict:
    """经 vools.bridge.md 逐块执行动作正文，汇总为结构化出参。"""
    from vools.bridge.md import run_md
    from . import sandbox as sbx
    from . import vault as vault_mod
    from .indexer import _repo_root

    # 见模块顶部 PROCESS_STATE_LOCK：持锁完成「注入 → 子进程启动」，避免并行节点互相覆盖。
    PROCESS_STATE_LOCK.acquire()
    # 整份快照 + 逐字回写，而不是「记下我改过的那几个键」：执行期往进程环境写的东西
    # 不止本函数列得出的那几个 —— 实测一次沙箱执行后残留 ACTUS_PARAMS / ACTUS_EXEC_ID /
    # 动作 secrets / TMP 一组 / 被 _sanitize_path_env 改写的 PATH，逐键列举必然漏项。
    # 快照点选在上面那些懒加载 import **之后**：vools 的 manager 首次加载时自己配置
    # PATH 与自带工具链变量（FBC/FBC32/FBC_DIR），那是库级一次性初始化，每次执行都
    # 回滚它会让下一次执行拿到半初始化环境（实测第二次起就不再出现，正说明它是一次性的）。
    # owner 于 2026-09-26 授权改本文件（AGENTS.md §2 禁改区），回归锁见
    # tests/test_env_isolation.py 与 Find_BUG/actus_2026q3/repro_env_01.py。
    env_before = _env_snapshot()
    try:
        _sanitize_path_env()
        # 参数注入：写入临时环境文件，vools config env 携带 ACTUS_PARAMS
        os.environ['ACTUS_PARAMS'] = json.dumps(params, ensure_ascii=False)
        os.environ['ACTUS_EXEC_ID'] = exec_id
        # 动作自身路径：docs/41 §A1 的内嵌 Sigma 规约块要读回**同一份文件**才能复跑
        # 规约门禁。没有它，动作只能把规约正文再抄一份进 python 块，抄的那份与
        # ```sigma 块会各自漂移，"校验过规约"就变成了"校验过副本"。
        os.environ['ACTUS_ACTION_PATH'] = action.path
        # 引擎定位环境：动作代码（如 loop_prompt 的会话留痕）经此解析引擎状态目录，
        # 测试经 meta_dir 覆盖即可整体隔离，不污染真实仓库。
        os.environ['ACTUS_REPO_ROOT'] = _repo_root()
        os.environ['ACTUS_META_DIR'] = meta_dir or os.path.join(_repo_root(), '_meta')

        # secrets 自动注入（docs/10 §D2）：解析动作的 secrets 字段，注入环境变量
        secrets_config = action.meta.get('secrets') or []
        if secrets_config:
            try:
                resolved_secrets = vault_mod.resolve_secrets(secrets_config, meta_dir=meta_dir or '')
                for env_name, env_value in resolved_secrets.items():
                    if env_value:  # 只注入非空值，避免覆盖已有环境变量
                        os.environ[env_name] = env_value
            except Exception:
                # secrets 注入失败不阻断执行，动作代码自行处理缺失密钥
                pass

        # Phase 4：vault:// 前缀自动解析（docs/10 §D3）。密钥值形如
        # `vault://<key>` 时，经 vault2 认证后用 resolve_vault_refs 换回明文。
        # 与 secrets 注入同源：失败不阻断执行，动作代码自行处理缺失密钥。
        try:
            vault_refs = [
                s for s in secrets_config
                if str(s.get('key', s.get('env', ''))).startswith('vault://')
            ]
            if vault_refs:
                from . import vault2 as vault2_mod
                identity_id = os.environ.get('VAULT_IDENTITY_ID')
                machine_id = os.environ.get('VAULT_MACHINE_ID')
                pin = os.environ.get('VAULT_PIN')
                if identity_id and machine_id and pin:
                    auth_result = vault2_mod.auth(identity_id, machine_id, pin)
                    if auth_result.get('status') == 'ok':
                        token = auth_result['session_token']
                        resolve_result = vault2_mod.resolve_vault_refs(token, vault_refs)
                        if resolve_result.get('status') == 'ok':
                            for env_name, env_value in resolve_result.get('resolved', {}).items():
                                if env_value:
                                    os.environ[env_name] = env_value
        except Exception:
            # vault:// 解析失败不阻断执行
            pass

        if sandboxed:
            # docs/07 §5：沙箱动作强制落入 jail 根，环境变量指示边界
            build_dir = sbx.prepare(artifacts_dir, exec_id)
            os.environ.update(sbx.sandbox_env(build_dir))
        else:
            # build_dir 落 artifacts/<action_id>/<version>/<exec_id>/（docs/08 §6）。
            # 每个 exec 独立目录：避免并发同动作时 vools manifest 原子 rename
            # 在 Windows 上互踩（PermissionError 竞态），同时满足 docs/08 §4 并发语义。
            build_dir = os.path.join(artifacts_dir, action.id,
                                     action.meta.get('version', '0.0.0'), exec_id)

        report = run_md(
            action.path,
            only=[action.entry] if action.entry else None,
            force=force or True,  # 动作语义：每次执行都是新 exec，不做块级缓存复用
            build_dir=build_dir,
        )
    finally:
        # 还原必须在放锁之前：并行节点各自的注入不能互相看见，也不能看见中间态。
        _env_restore(env_before)
        PROCESS_STATE_LOCK.release()

    blocks = []
    all_ok = True
    # 出参解析必须用**未截断**的入口块原文：先截尾再 json.loads，等于让长度策略改写出参
    # 契约 —— 合法 JSON 被劈成尾巴后必然解不动，落进降级分支换成 {'output': 尾巴}，
    # 声明过的出参键整个消失且不留痕迹（BUG-0016）。截断只留给记录与回传的那份。
    entry_stdout_raw = ''
    for b in report.get('blocks', []):
        raw_stdout = b.get('stdout') or ''
        if action.entry in (b.get('tag') or []):
            entry_stdout_raw = raw_stdout
        blocks.append({
            'index': b['index'],
            'language': b['language'],
            'tag': b['tag'],
            'status': b['status'],
            'duration_ms': b['duration_ms'],
            'exit_code': b.get('exit_code'),
            'stdout': raw_stdout[-_STDOUT_KEEP:],
            'stderr': (b.get('stderr') or '')[-2000:],
        })
        if b['status'] in ('failed', 'error', 'timeout'):
            all_ok = False

    # 出参 data：入口块 stdout 优先尝试解析为 JSON（docs/03 §7.3.7）
    data = None
    stdout_truncated = False
    if entry_stdout_raw:
        stdout_truncated = len(entry_stdout_raw) > _STDOUT_KEEP
        try:
            data = json.loads(entry_stdout_raw)
        except (json.JSONDecodeError, ValueError):
            data = {'output': entry_stdout_raw[-_STDOUT_KEEP:].strip()}

    if not all_ok:
        err_blocks = [b for b in blocks if b['status'] in ('failed', 'error', 'timeout')]
        if sandboxed:
            # docs/07 §5 的「执行完即回收」原本只挂在成功分支，于是反复失败的动作按次
            # 累积 jail 目录（BUG-0012）。owner 裁决默认删：失败现场已经随下面的
            # error.details.blocks 带出 stderr 尾段，排障不依赖目录是否还在。
            sbx.cleanup(artifacts_dir, exec_id, keep=False)
        failed = {'status': 'failed', 'data': data, 'error': {
            'code': 'internal',
            'message': f"块执行失败: block[{err_blocks[0]['index']}] {err_blocks[0]['status']}",
            'details': {'blocks': err_blocks},
        }}
        if stdout_truncated:
            failed['stdout_truncated'] = True
        return failed

    # entry_no_output 契约（docs/38 §1）：入口块没抛异常、也没打印 ⇒ 不能记 ok。
    # 否则"调用被关在 `if __name__ == \"__main__\":` 里"这族动作每次执行都报成功、
    # 不留痕迹 —— 引擎 exec 时 __name__='__md_block__'，守卫内的调用永不执行。
    # 判据认"空 stdout"，不认 data 为 null（main 合法返回 None 时 data=None 但 stdout 非空）。
    if not entry_stdout_raw.strip():
        return {'status': 'failed', 'data': None, 'error': {
            'code': 'entry_no_output',
            'message': (f"入口块 {action.entry} 无 stdout：{action.id} 的调用被关在守卫里，"
                        f"或 main() 未打印。引擎 exec 时 __name__ != '__main__'，"
                        f"`if __name__ == \"__main__\":` 内的调用永不执行。"),
            'details': {
                'entry_block': action.entry,
                'hint': ('ENTRY_DRIVER：把调用从守卫移到模块级 —— '
                         '读 ACTUS_PARAMS → main(params) → print(json.dumps(...))'),
            },
        }}

    # 产物收集：vools 报告中的 export 产物 + 块级 output 文件（docs/04 §3）
    arts = []
    for b in report.get('blocks', []):
        for a in (b.get('artifacts') or []):
            arts.append({'name': a.get('name'), 'path': a.get('path'),
                         'hash': a.get('hash'), 'block': b['index']})
        if b.get('output_file'):
            arts.append({'name': os.path.basename(b['output_file']),
                         'path': b['output_file'], 'hash': None, 'block': b['index']})

    result = {'status': 'ok', 'data': data, 'error': None, 'artifacts': arts}
    if stdout_truncated:
        # 出参形状保住了，但回传的记录侧 stdout 是截过的 —— 让调用方分得清
        # 「动作真吐了 output 键」与「被长度策略截过」（BUG-0016）。
        result['stdout_truncated'] = True
    if sandboxed:
        result['sandboxed'] = True
        result['sandbox_root'] = build_dir.replace(os.sep, '/')
        # docs/07 §5：沙箱结果与产物同样留痕但根目录临时，执行完即回收
        sbx.cleanup(artifacts_dir, exec_id, keep=False)
    return result


def _register_artifacts(meta_dir: str, action: Action, exec_id: str,
                        artifacts: list) -> None:
    """产物登记 _meta/artifacts.json（docs/04 §3：名称/路径/哈希/来源动作/版本）。"""
    if not artifacts:
        return
    path = os.path.join(meta_dir, 'artifacts.json')
    reg = {'actions': {}}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reg = json.load(f)
        except (json.JSONDecodeError, OSError):
            reg = {'actions': {}}

    import hashlib
    actions_reg = reg.setdefault('actions', {})
    ver_reg = actions_reg.setdefault(action.id, {}).setdefault(
        action.meta.get('version', '0.0.0'), {'artifacts': {}})
    table = ver_reg.setdefault('artifacts', {})
    for a in artifacts:
        p = a.get('path')
        sha = a.get('hash')
        if p and os.path.exists(p) and not sha:
            with open(p, 'rb') as f:
                sha = hashlib.sha256(f.read()).hexdigest()
        table[a.get('name') or f'block_{a.get("block")}'] = {
            'path': (p or '').replace(os.sep, '/'),
            'sha256': sha,
            'source_exec': exec_id,
            'block': a.get('block'),
        }
    os.makedirs(meta_dir, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def preview(action_id: str, params: dict = None, actions_dir: str = None) -> dict:
    """干跑（docs/06 §3）：展示将执行的块/指令/依赖/trust，不执行任何代码。"""
    from .indexer import get_action
    params = params or {}
    action = (_get_validated(action_id) if not actions_dir
              else load_and_validate(get_action(action_id, actions_dir).path))
    _validate_params(action, params)
    strategy = decide(action.trust, confirmed=False)
    return {
        'action': action.brief(),
        'blocks': [{'index': b['index'], 'language': b['language'],
                    'tag': b['tag'], 'directives': b['directives']}
                   for b in action.blocks],
        'deps': action.meta.get('deps') or [],
        'strategy': strategy,
        'pending_ops': _pending_ops(action, params),
    }
