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
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone, timedelta

from .errors import ActionError
from .model import Action
from .process_state import PROCESS_STATE_LOCK
from .validate import load_and_validate, validate_graph
from .indexer import scan_actions
from .trust import decide
from . import records
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
    from .paths import meta_dir as _paths_meta_dir
    root = _repo_root()
    # 审计修（`_meta` 手写 → paths.meta_dir()）：默认 meta 目录跟随
    # ACTUS_META_DIR > repo_root()/_meta；显式传 meta_dir 时仍然以参数为准。
    meta = meta_dir or _paths_meta_dir()
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


_forward_ctx = threading.local()
_demo_ctx = threading.local()


def _execute_template_kind(action, action_id, params, **kw):
    """阶段3：template 动作——按声明调用 scaffold 生成动作文件（计划 §3.3）。"""
    from .scaffold import scaffold_action
    desc = action.meta.get('template') or action.meta.get('description') or ''
    if isinstance(desc, dict):
        desc = desc.get('description') or desc.get('text') or ''
    if not str(desc).strip():
        return {
            'status': 'failed', 'data': None,
            'error': {'code': 'param_invalid',
                      'message': f"kind=template 的动作 {action_id} 缺少模板描述"
                                 f"（meta['template'] 或 description）"},
        }
    try:
        result = scaffold_action(description=str(desc),
                                 action_id=action.meta.get('target') or None,
                                 trust=action.meta.get('trust') or 'audit')
    except Exception as exc:
        return {
            'status': 'failed', 'data': None,
            'error': {'code': 'runtime',
                      'message': f"template 动作 {action_id} 生成失败: {exc}"},
        }
    return {'status': 'ok', 'data': {'scaffold': result,
                                     'template_params': params or {}}}


def _execute_bundle_kind(action, action_id, params, **kw):
    """阶段3：bundle 动作——列出成员动作 id 列表（计划 §3.3）。

    空成员必须报错：`kind=bundle` 却一个成员都没有属于**声明错误**，此前
    返回 `status=ok, members=[], count=0` —— 空操作却报成功，与 link/alias
    缺 target 时抛 param_invalid 的行为不一致。
    """
    members = action.meta.get('members') or []
    if isinstance(members, str):
        members = [m.strip() for m in members.split(',') if m.strip()]
    if not members:
        target = action.meta.get('target')
        members = [target] if target else []
    if not members:
        return {
            'status': 'failed', 'data': None,
            'error': {'code': 'param_invalid',
                      'message': f"kind=bundle 的动作 {action_id} 缺少成员"
                                 f"（meta['members'] 或 target）"},
        }
    return {'status': 'ok', 'data': {'members': list(members),
                                     'count': len(members)}}


def _execute_doc_kind(action, action_id, params, **kw):
    """阶段3：doc 动作——仅渲染，不执行任何代码（计划 §3.3）。"""
    body = getattr(action, 'body', '') or ''
    return {'status': 'ok',
            'data': {'rendered': True,
                     'description': action.meta.get('description') or '',
                     'body': body,
                     'entry': action.meta.get('entry') or None}}


def _attach_demo_expansion(result, action):
    """阶段3：demo 演示模式——把全部代码块源码按 only-code 展开附在出参里。

    计划 §3.4：「demo 动作的全部块默认视为 only-code 展开」。
    """
    expanded = []
    for block in action.blocks:
        src = block.get('source') or block.get('content') or ''
        if src:
            expanded.append({
                'language': block.get('language'),
                'tags': block.get('tags') or [],
                'only_code': True,
                'source': src,
            })
    data = result.get('data')
    if isinstance(data, dict):
        data['demo'] = {'expanded': expanded,
                        'block_count': len(expanded)}
    return result


def _deep_merge_params(base: dict, override: dict) -> dict:
    """递归合并：dict 逐层合并、其它类型（含 list）整体替换，override 叶子优先。

    计划 §六.4 的深合并规则：
      - 两侧都是 dict → 递归合并
      - 任一侧不是 dict（含 list/标量）→ override 整体替换
      - override 里没有的键保留 base 的值
    """
    out = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_params(out[key], value)
        else:
            out[key] = value
    return out


def _merge_link_params(action, params):
    """阶段3/§六.4：link 的参数合并——args 作基底、调用方入参覆盖同名键。

    合并模式由动作 `meta['merge']` 决定：
      - `shallow`（默认）：顶层键覆盖，嵌套 dict 整体替换（零回归）
      - `deep`：递归合并嵌套 dict；list/标量整体替换；调用方叶子优先
    抽成纯函数便于单测（不依赖 execute 递归，避免打桩模块全局的脆弱性）。
    """
    forwarded = dict(params or {})
    link_args = action.meta.get('args') or {}
    if not isinstance(link_args, dict):
        return forwarded
    mode = str(action.meta.get('merge') or 'shallow').strip().lower()
    if mode == 'deep':
        return _deep_merge_params(link_args, forwarded)
    merged = dict(link_args)
    merged.update(forwarded)
    return merged


def _execute_forwarding_kind(action, action_id, params, kind, **kw):
    """阶段3：alias 直接转发；link 做参数浅合并后转发（ACTUS_REFACTOR_PLAN §3.3）。

    转发通过 execute 递归完成（走完整的门禁链），并用线程局部深度计数防环（上限 5）。
    """
    target = str(getattr(action, 'target', '') or '').strip()
    if not target:
        return {
            'status': 'failed', 'data': None,
            'error': {'code': 'param_invalid',
                      'message': f"kind={kind} 的动作 {action_id} 缺少 target 字段"},
        }
    forwarded = _merge_link_params(action, params) if kind == 'link' else dict(params or {})
    depth = getattr(_forward_ctx, 'depth', 0)
    chain = list(getattr(_forward_ctx, 'chain', None) or [])
    # 真环：目标已经在这条转发链上（或指向自己）。此前只数深度，把「深链」
    # 和「成环」报成同一个 param_invalid「疑似环」——直线链 a1→a8 其实不是环。
    if target in chain or target == action_id:
        full = chain + [action_id, target]
        return {
            'status': 'failed', 'data': None,
            'error': {'code': 'action_ref_cycle',
                      'message': f"link/alias 转发成环：{' → '.join(full)}",
                      'details': {'chain': full}},
        }
    if depth >= 5:
        return {
            'status': 'failed', 'data': None,
            'error': {'code': 'param_invalid',
                      'message': f"link/alias 转发层级 ≥5（{action_id} → {target}）："
                                 f"链上无重复节点，属**深度超限**而非成环；"
                                 f"如确需更深转发请拆分动作",
                      'details': {'chain': chain + [action_id]}},
        }
    _forward_ctx.depth = depth + 1
    _forward_ctx.chain = chain + [action_id]
    try:
        return execute(target, forwarded,
                       confirmed=kw.get('confirmed', False),
                       meta_dir=kw.get('meta_dir'),
                       actions_dir=kw.get('actions_dir'),
                       force=kw.get('force', False),
                       artifacts_dir=kw.get('artifacts_dir'))
    finally:
        _forward_ctx.depth = depth
        _forward_ctx.chain = chain


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
    _t_start = time.time()  # 使用量指标计时起点（docs/03 §4.1）

    # 产物目录写入前先过安全策略（接线 check_file_access，此前零调用）
    _check_artifacts_access(artifacts_dir)

    # ── 依赖检查（执行前）──
    action_obj = None
    dep_check = None
    try:
        from .indexer import get_action
        # 零散动作（scattered path）不在索引里，若给了 preparsed_action 就跳过查找，
        # 否则会先抛 action_not_found、走不到后面的 preparsed 分支。
        action_obj = preparsed_action if preparsed_action is not None \
            else load_and_validate(get_action(action_id, actions_dir).path)

        # ── 阶段3：非 exec kind 的执行语义（ACTUS_REFACTOR_PLAN §3.3）──
        # 此前执行器完全不感知 kind：link/alias 会被当成普通 exec 动作执行
        # （无 entry 的报 entry_no_output、有 entry 的会跑错代码），阶段3 的
        # 出口条件『link 合并参数执行』因此不达标。
        kind = str(getattr(action_obj, 'kind', '') or 'exec').lower()
        if kind == 'demo' and not getattr(_demo_ctx, 'active', False):
            # 阶段3：demo 演示模式 = 执行入口块 + 把全部代码块按 only-code 展开输出。
            # 用线程局部标志避免 execute 递归回来再次进入演示分支。
            _demo_ctx.active = True
            try:
                result = execute(action_id, params, confirmed=confirmed,
                                 meta_dir=meta_dir, actions_dir=actions_dir,
                                 force=force, artifacts_dir=artifacts_dir)
            finally:
                _demo_ctx.active = False
            return _attach_demo_expansion(result, action_obj)
        if kind == 'template':
            return _execute_template_kind(action_obj, action_id, params)
        if kind == 'bundle':
            return _execute_bundle_kind(action_obj, action_id, params)
        if kind == 'doc':
            return _execute_doc_kind(action_obj, action_id, params)
        if kind in ('alias', 'link'):
            return _execute_forwarding_kind(
                action_obj, action_id, params, kind,
                confirmed=confirmed, meta_dir=meta_dir, actions_dir=actions_dir,
                force=force, artifacts_dir=artifacts_dir)
        # 演示模式递归回来时（_demo_ctx.active=True），demo 应按 exec 执行，
        # 不能落到下面的 kind_unsupported 分支——否则 demo 递归把自己否掉。
        _demo_inner = kind == 'demo' and getattr(_demo_ctx, 'active', False)
        if kind != 'exec' and not _demo_inner:
            return {
                'status': 'failed',
                'data': None,
                'error': {
                    'code': 'kind_unsupported',
                    'message': f"kind={kind!r} 的执行语义尚未落地（阶段3 目前只实现 "
                               f"alias/link 转发）；动作 id={action_id}",
                    'details': {'kind': kind, 'action_id': action_id},
                },
            }

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
        # docs/46 #5/#6/#7：回执带 mode / env_prefix / resources 摘要
        # （action 在异常路径可能未解析成功，用局部判断兜住）
        try:
            result['mode'] = action.exec_mode
            result['env_prefix'] = action.env_prefix
            if record.get('resources'):
                result['resources'] = record['resources']
        except (NameError, AttributeError):
            result['mode'] = 'sync'
            result['env_prefix'] = 'ACTUS_'
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

        # ── 使用量指标埋点（docs/03 §4.1：执行计数区分「安装了」vs「真正在用」）──
        # best-effort：写指标失败绝不影响执行结果（与 calllog 设计一致）。
        # 落点与 call_log 同库（_meta/call_log.db 的 action_metrics 表），
        # popular_actions / trending_actions / quality_scale 全部消费此数据。
        # V-20（寻虫 2026-10-22）：awaiting_confirmation 是「还没执行」的正常业务态，
        # 不是执行结局——写成 ok=False 会把"面板每刷新一次待确认队列"记成一次假失败，
        # success_rate 被不可逆污染（3 预览+1 真成功 → 0.25），quality 直接掉 bronze。
        # 只有真实执行结局（ok/partial/failed/timeout/cancelled）才落指标。
        # caller 记调用来源：confirmed=True 的人工放行 vs False 的 MCP/CLI 自动调用，
        # 让 unique_callers 聚合能区分"哪个通道在用"（docs/03 §4.1）。
        if result['status'] in ('ok', 'partial', 'failed', 'timeout', 'cancelled'):
            try:
                from .calllog import write_action_metric
                write_action_metric(
                    action_id,
                    ok=(result['status'] in ('ok', 'partial')),
                    runtime_ms=int((time.time() - _t_start) * 1000),
                    caller='confirmed' if confirmed else 'executor',
                    meta_dir=meta_dir,
                )
            except Exception:
                pass  # best-effort：指标缺失不改变回执

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

        # docs/46 #5/#6/#7：mode / context / resources 契约消费
        record['mode'] = action.exec_mode
        record['env_prefix'] = action.env_prefix
        record['resources'] = {
            'timeout_ms': action.timeout_ms,
            'max_memory_mb': action.max_memory_mb,
            'max_processes': action.max_processes,
            'net_connect': action.net_connect,
            'net_listen': action.net_listen,
        } if (action.timeout_ms or action.max_memory_mb or action.max_processes
              or action.net_connect or action.net_listen) else {}

        _validate_params(action, params)

        # 依赖图校验（含本动作的 deps）
        all_actions = scan_actions(actions_dir, validate=False)
        sub = {aid: a for aid, a in all_actions.items()
               if aid == action_id or aid in (action.meta.get('deps') or [])}
        validate_graph(sub)

        # ── 可见性门禁（docs/41 §B1）：只判新增的 internal / gated 两级 ──
        _visibility_gate(action, action_id, exec_id)

        # ── 安全策略门禁（第 10 轮接线：Scanner/SandboxEnhancer 此前产品零调用）──
        # 低信任动作命中策略/危险内容 → permission_denied；其余只留痕，不拦截。
        record['security'] = _security_gate(action, action_id)

        # ── trust 判定 ──
        # ACTUS_DEBUG 开发模式（true/1/yes/on）：audit 级动作自动放行，
        # 免去每次人工确认（git.ops 等 audit 动作在开发仓联调时不再卡 awaiting）。
        # 使用模式（false/缺省）：audit 仍须人工确认，行为不变。
        _dev = os.environ.get('ACTUS_DEBUG', '').strip().lower() in ('1', 'true', 'yes', 'on')
        if _dev and action.trust == 'audit':
            confirmed = True
            record['dev_auto_confirm'] = True
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
        # docs/46 #7：resources.max_processes 作为并发上限的补充声明（
        # max_instances 优先；两者都设时取较小值）
        max_inst = action.max_instances
        max_proc = action.max_processes
        if max_inst > 0 and max_proc > 0:
            max_inst = min(max_inst, max_proc)
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


def _security_gate(action: Action, action_id: str) -> dict:
    """执行前安全策略检查（第 10 轮接线）。

    背景：`security.SecurityScanner.scan_action`（权限策略 + 敏感信息正则 +
    危险命令模式）此前**产品零调用** —— 引擎执行路径从不做安全检查，
    安全检查模块形同虚设。现在在执行前调用，并按 lead 裁决**按 trust 分级**：

    - 低信任（`trust` ∈ sandbox / community）：命中即 `ActionError(permission_denied)`
      拒绝执行（这两个信任级的用途就是被强校验）；
    - audit / trusted：只把结论记进执行记录（`record['security']`），不拦截
      —— 避免现有动作因为历史文本里的"疑似敏感信息"突然全红。

    扫描器自身异常 → 记录 `scanned=False`，不因扫描器故障阻塞执行。
    """
    try:
        from .security import get_security_scanner
        scanner = get_security_scanner()
        result = scanner.scan_action(action_id, action.meta,
                                     action.raw or action.body or '')
    except Exception as exc:  # noqa: BLE001 —— 安全模块故障不应让所有动作不可执行
        return {'scanned': False, 'reason': '%s: %s' % (type(exc).__name__, exc)}

    issues = [str(m) for m in (result.get('issues') or [])]
    findings = result.get('sensitive_findings') or []
    trust = str(action.meta.get('trust') or 'audit').strip().lower()
    info = {'scanned': True, 'safe': bool(result.get('safe')),
            'issues': issues[:5], 'sensitive_findings': len(findings)}
    if trust in ('sandbox', 'community') and (issues or findings):
        raise ActionError(
            'permission_denied',
            '安全策略拒绝执行 %s：%s' % (
                action_id,
                '; '.join((issues or ['检测到疑似敏感信息'])[:3])),
            {'action_id': action_id, 'trust': trust,
             'issues': issues[:5], 'sensitive_findings': len(findings)})
    return info


def _check_artifacts_access(artifacts_dir: str) -> None:
    """产物目录写入前的策略检查（接线 `SandboxEnhancer.check_file_access`）。

    审计修复：`check_file_access` 此前零调用 —— 策略里的 blocked_paths /
    allowed_paths 从未影响任何写入。现在执行前先验产物目录。
    """
    try:
        from .security import get_security_scanner
        ok, issues = get_security_scanner().sandbox.check_file_access(
            artifacts_dir, 'write')
    except Exception:  # noqa: BLE001 —— 策略模块故障不阻塞（执行路径已有其他防护）
        return
    if not ok:
        raise ActionError(
            'permission_denied',
            '产物目录不在安全策略允许范围：%s' % '; '.join(str(m) for m in issues[:3]),
            {'path': artifacts_dir, 'issues': [str(m) for m in issues[:5]]})


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


def _apply_env_injections(action, params, exec_id, artifacts_dir,
                          sandboxed, meta_dir):
    """在**当前线程已持 PROCESS_STATE_LOCK** 的前提下，把执行期 env 注入父进程环境，
    返回 build_dir。调用方负责 `_env_restore()`（原样回写）。

    拆出来是为了让两条路径共用同一份注入逻辑（单一真源）：
      * 同步直调：注入 → run_md → 还原，都在本进程；
      * 子进程隔离：注入 → **拷贝 env** → 立刻还原 → 交给 Popen(env=...)，
        父进程环境一个键都不留。
    """
    from . import sandbox as sbx
    from . import vault as vault_mod
    from .indexer import _repo_root

    _sanitize_path_env()
    prefix = action.env_prefix
    os.environ[f'{prefix}PARAMS'] = json.dumps(params, ensure_ascii=False)
    os.environ[f'{prefix}EXEC_ID'] = exec_id
    os.environ[f'{prefix}ACTION_PATH'] = action.path
    os.environ[f'{prefix}REPO_ROOT'] = _repo_root()
    # 同 `_meta_dirs`：默认 meta dir 跟随 ACTUS_META_DIR（显式参数优先）
    from .paths import meta_dir as _paths_meta_dir
    os.environ[f'{prefix}META_DIR'] = meta_dir or _paths_meta_dir()

    secrets_config = action.meta.get('secrets') or []
    if secrets_config:
        try:
            resolved_secrets = vault_mod.resolve_secrets(secrets_config, meta_dir=meta_dir or '')
            for env_name, env_value in resolved_secrets.items():
                if env_value:
                    os.environ[env_name] = env_value
        except Exception:
            pass

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
        pass

    if sandboxed:
        build_dir = sbx.prepare(artifacts_dir, exec_id)
        os.environ.update(sbx.sandbox_env(build_dir))
    else:
        build_dir = os.path.join(artifacts_dir, action.id,
                                 action.meta.get('version', '0.0.0'), exec_id)
    return build_dir


def _run_md_in_env(action: 'Action', params: dict, exec_id: str,
                   artifacts_dir: str, force: bool, sandboxed: bool, meta_dir):
    """同步路径（未配置 resources.timeout_ms）：本进程内 注入 → run_md → 还原。

    **零行为变化**：与改前的执行方式逐字一致，一个子进程都不起。
    """
    from vools.bridge.md import run_md

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
        build_dir = _apply_env_injections(action, params, exec_id, artifacts_dir,
                                          sandboxed, meta_dir)
        report = run_md(
            action.path,
            only=[action.entry] if action.entry else None,
            # E4：md 层缓存**刻意恒绕过**（force or True）。动作执行承诺"每次真跑"，
            # 让块缓存命中会把上一轮的 stdout/产物当成这次结果返回（与假成功同族）。
            # 这个参数因此恒为 True；execute(force=...) 的 force 只用于"忽略缺依赖"。
            force=force or True,
            build_dir=build_dir,
        )
    finally:
        # 还原必须在放锁之前：并行节点各自的注入不能互相看见，也不能看见中间态。
        _env_restore(env_before)
        PROCESS_STATE_LOCK.release()
    return report, build_dir


# 子进程引导脚本：只 import 桥接层（**不 import executor**，避免父包副作用），
# 读 task.json → run_md → 把结果子集写 result.json。参数全部走文件，不经 shell。
_CHILD_BOOTSTRAP = r"""
import json, os, sys
with open(sys.argv[1], "r", encoding="utf-8") as _fh:
    _task = json.load(_fh)
from vools.bridge.md import run_md
_report = run_md(_task["path"], only=_task.get("only") or None,
                 force=True, build_dir=_task["build_dir"])
_keep = ("index", "language", "tag", "status", "duration_ms", "exit_code",
         "stdout", "stderr", "artifacts", "output_file")
with open(_task["result"], "w", encoding="utf-8") as _fh:
    json.dump({"blocks": [{k: b.get(k) for k in _keep}
                          for b in _report.get("blocks", [])],
               "child_pid": os.getpid()}, _fh, ensure_ascii=False, default=str)
"""


def _build_child_env(action, params, exec_id, artifacts_dir, sandboxed, meta_dir):
    """构造**子进程专用**的 env 副本 + build_dir；父进程环境全程不被污染。

    做法：持锁 → 按现有逻辑注入 → `dict(os.environ)` 拷贝 → 立刻 `_env_restore`
    回写父环境 → 释放锁。拷贝出的副本交给 `Popen(env=...)`，于是"注入"这件事
    只发生在子进程身上，父进程（以及同进程的其它线程）看不到任何中间态。
    """
    PROCESS_STATE_LOCK.acquire()
    env_before = _env_snapshot()
    try:
        build_dir = _apply_env_injections(action, params, exec_id, artifacts_dir,
                                          sandboxed, meta_dir)
        child_env = dict(os.environ)
    finally:
        _env_restore(env_before)
        PROCESS_STATE_LOCK.release()
    return child_env, build_dir


def _run_md_in_child(action, params, exec_id, artifacts_dir, force, sandboxed, meta_dir):
    """把 run_md 放进**独立子进程**执行；超时 → `kill_tree` 杀整棵树 → 立刻返回。

    返回 (report, build_dir, deferred)；deferred 恒为 False —— 这次是**真杀**：
    子进程整个没了，env / 全局锁 / stdout 天然干净，不存在"回执说超时、后台还在跑"。
    """
    from ._proc import kill_tree

    timeout_ms = action.timeout_ms
    child_env, build_dir = _build_child_env(action, params, exec_id, artifacts_dir,
                                            sandboxed, meta_dir)
    work_dir = tempfile.mkdtemp(prefix='actus-exec-')
    task_path = os.path.join(work_dir, 'task.json')
    result_path = os.path.join(work_dir, 'result.json')
    with open(task_path, 'w', encoding='utf-8') as fh:
        json.dump({
            'path': action.path,
            'only': [action.entry] if action.entry else None,
            'build_dir': build_dir,
            'result': result_path,
        }, fh, ensure_ascii=False)

    proc = subprocess.Popen(
        [sys.executable, '-c', _CHILD_BOOTSTRAP, task_path],
        cwd=os.getcwd(),          # 子进程沿用同一 cwd：动作里的相对路径语义不变
        env=child_env,            # 注入只作用于子进程，父进程零污染
    )
    timed_out = False
    try:
        proc.wait(timeout=timeout_ms / 1000.0)
    except subprocess.TimeoutExpired:
        timed_out = True
        # 真上限：杀整棵进程树（psutil 递归 kill，含孙进程），不是只杀直接子进程
        kill_tree(proc)
        try:
            proc.wait(timeout=10)
        except Exception:
            pass

    if timed_out:
        report = {'status': 'timeout', 'blocks': [{
            'index': 0, 'language': 'python', 'tag': [action.entry],
            'status': 'timeout', 'duration_ms': timeout_ms,
            'exit_code': proc.returncode, 'stdout': '',
            'stderr': (f'execution exceeded {timeout_ms}ms (resources.timeout_ms)；'
                       f'已杀整棵进程树（pid={proc.pid}, rc={proc.returncode}）'),
        }]}
    else:
        payload = None
        if os.path.exists(result_path):
            try:
                with open(result_path, 'r', encoding='utf-8') as fh:
                    payload = json.load(fh)
            except Exception:
                payload = None
        if not isinstance(payload, dict) or not isinstance(payload.get('blocks'), list):
            # 子进程崩溃（段错误 / OOM / 被外部杀掉）→ 没有结果文件。
            # 归类 block_failed（不是 internal：这不是引擎写错，是执行体崩了）。
            report = {'status': 'failed', 'blocks': [{
                'index': 0, 'language': 'python', 'tag': [action.entry],
                'status': 'failed', 'duration_ms': None,
                'exit_code': proc.returncode, 'stdout': '',
                'stderr': f'child_crashed: 子进程未回传结果（exit={proc.returncode}）',
            }]}
        else:
            report = {'blocks': payload['blocks']}

    shutil.rmtree(work_dir, ignore_errors=True)
    return report, build_dir, False


def _run_blocks(action: Action, params: dict, exec_id: str,
                artifacts_dir: str, force: bool = False,
                sandboxed: bool = False, meta_dir: str = None) -> dict:
    """经 vools.bridge.md 逐块执行动作正文，汇总为结构化出参。"""
    from . import sandbox as sbx        # 沙箱清理仍在**本函数**里做（注入在子进程/本进程内）

    timeout_ms = action.timeout_ms
    deferred = False
    if not timeout_ms or timeout_ms <= 0:
        # 未配置超时：**同步直调，零行为变化**（不起子进程、不加启动开销）
        report, build_dir = _run_md_in_env(action, params, exec_id, artifacts_dir,
                                           force, sandboxed, meta_dir)
    else:
        # 配置了 resources.timeout_ms：**放进独立子进程**跑，超时 kill_tree 杀整棵树。
        # 这样超时是**真上限**：父进程立刻返回，且 env / 全局锁 / stdout 天然干净
        # （子进程有自己的环境与 fd）。deferred 恒为 False —— 不存在后台残留。
        report, build_dir, deferred = _run_md_in_child(
            action, params, exec_id, artifacts_dir, force, sandboxed, meta_dir)

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
        block_entry = {
            'index': b['index'],
            'language': b['language'],
            'tag': b['tag'],
            'status': b['status'],
            'duration_ms': b['duration_ms'],
            'exit_code': b.get('exit_code'),
            'stdout': raw_stdout[-_STDOUT_KEEP:],
            'stderr': (b.get('stderr') or '')[-2000:],
        }
        if b['status'] in ('failed', 'error', 'timeout'):
            all_ok = False
            # E2：失败块额外带 error（短尾 stderr），回执里"为什么失败"一览即得
            block_entry['error'] = (b.get('stderr') or '').strip()[-500:] or b['status']
        blocks.append(block_entry)

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
        # 子进程方案下超时是**真上限**（进程已被 kill_tree 杀掉），所以这里显式给
        # timeout_deferred=False：字段保留（消费方可能读它），含义从"后台仍在跑"
        # 变成"确认已经停掉"。只有线程方案才会有 True 的情形，本路径不再出现。
        killed = any(b['status'] == 'timeout' for b in err_blocks)
        if sandboxed:
            # docs/07 §5 的「执行完即回收」原本只挂在成功分支，于是反复失败的动作按次
            # 累积 jail 目录（BUG-0012）。owner 裁决默认删：失败现场已经随下面的
            # error.details.blocks 带出 stderr 尾段，排障不依赖目录是否还在。
            sbx.cleanup(artifacts_dir, exec_id, keep=False)
        # E2：details.blocks 给出**全部已执行块**（含成功）——"失败后继续跑"本身不是
        # 缺陷，但"调用方看不到它跑了"是（副作用可能已发生，重试会重复）。
        # failed_blocks 保留失败子集，兼容只读该字段的既有消费方。
        details = {'blocks': blocks, 'failed_blocks': err_blocks}
        if killed:
            details['timeout_deferred'] = False
            details['child_killed'] = True
        failed = {'status': 'failed', 'data': data, 'error': {
            # E3：用户代码失败用 block_failed（details 带 exit_code/status），
            # `internal` 只留给引擎自身异常（execute() 末尾的兜底分支）。
            'code': 'block_failed',
            'message': f"块执行失败: block[{err_blocks[0]['index']}] {err_blocks[0]['status']}",
            'details': details,
        }}
        if killed:
            failed['timeout_deferred'] = False
            failed['child_killed'] = True
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
