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
from datetime import datetime, timezone, timedelta

from .errors import ActionError
from .model import Action
from .validate import load_and_validate, validate_graph
from .trust import decide
from . import records
from .indexer import scan_actions
from .omega import verify_output, compute_output_fingerprint, _find_omega_spec
from .concurrency import get_manager
from .dependency import get_resolver, DependencyResolver

_TZ = timezone(timedelta(hours=8))

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


def execute(action_id: str, params: dict = None,
            confirmed: bool = False, meta_dir: str = None,
            actions_dir: str = None, force: bool = False,
            artifacts_dir: str = None) -> dict:
    """执行一个动作，返回 docs/03 §7.2 结构化出参。

    confirmed=True 表示人类已通过确认通道放行（audit 级需要）。
    meta_dir/artifacts_dir 可覆盖留痕与产物落点（临时仓库隔离）。
    全程留痕：_meta/runs/<exec_id>.json + status.json + 追加式日志。
    """
    params = params if params is not None else {}
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
            all_ok, dep_msgs = resolver.resolve(action_obj.dependencies, auto_install=False)
            dep_check = {"satisfied": all_ok, "messages": dep_msgs}
            if not all_ok and not force:
                result = {
                    "status": "failed",
                    "error": {"code": "deps_missing", "message": "依赖未满足，可使用 force=True 强制执行"},
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
                if not omega_report.get('gate', {}).get('passed', True):
                    result['status'] = 'failed'
                    result['error'] = {
                        'code': 'omega_gate_failed',
                        'message': f"Ω-gate 验证失败，准确率 {omega_report['gate'].get('accuracy', 0)}% < 100%",
                        'details': omega_report
                    }
            except Exception:
                pass  # spec 缺失或格式错误不阻塞执行
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


def _run_blocks(action: Action, params: dict, exec_id: str,
                artifacts_dir: str, force: bool = False,
                sandboxed: bool = False, meta_dir: str = None) -> dict:
    """经 vools.bridge.md 逐块执行动作正文，汇总为结构化出参。"""
    from vools.bridge.md import run_md
    from . import sandbox as sbx
    from . import vault as vault_mod
    from .indexer import _repo_root

    # 参数注入：写入临时环境文件，vools config env 携带 ACTUS_PARAMS
    os.environ['ACTUS_PARAMS'] = json.dumps(params, ensure_ascii=False)
    os.environ['ACTUS_EXEC_ID'] = exec_id
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

    blocks = []
    all_ok = True
    for b in report.get('blocks', []):
        blocks.append({
            'index': b['index'],
            'language': b['language'],
            'tag': b['tag'],
            'status': b['status'],
            'duration_ms': b['duration_ms'],
            'exit_code': b.get('exit_code'),
            'stdout': (b.get('stdout') or '')[-4000:],
            'stderr': (b.get('stderr') or '')[-2000:],
        })
        if b['status'] in ('failed', 'error', 'timeout'):
            all_ok = False

    # 出参 data：入口块 stdout 优先尝试解析为 JSON（docs/03 §7.3.7）
    data = None
    entry_block = next((b for b in blocks if action.entry in (b['tag'] or [])), None)
    if entry_block and entry_block['stdout']:
        try:
            data = json.loads(entry_block['stdout'])
        except (json.JSONDecodeError, ValueError):
            data = {'output': entry_block['stdout'].strip()}

    if not all_ok:
        err_blocks = [b for b in blocks if b['status'] in ('failed', 'error', 'timeout')]
        return {'status': 'failed', 'data': data, 'error': {
            'code': 'internal',
            'message': f"块执行失败: block[{err_blocks[0]['index']}] {err_blocks[0]['status']}",
            'details': {'blocks': err_blocks},
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
