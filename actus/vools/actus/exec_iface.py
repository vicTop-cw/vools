"""exec_iface.py —— 动作统一执行接口（docs/03 §3 协议统一章节）。

分层抽象（借鉴 WoT affordance + MCP capability negotiation + n8n Node SDK）：

    ┌─────────────────────────────────────────────┐
    │ 统一接口层：ActionExecutor 接口               │  ← 本模块
    │   execute(action, ctx) → ExecResult          │
    ├─────────────────────────────────────────────┤
    │ 协议绑定层：CLI / MCP / HTTP / Quicker 适配   │  ← adapter.py
    ├─────────────────────────────────────────────┤
    │ 实现层：runner / runtimes / scattered        │  ← 现有执行管线
    └─────────────────────────────────────────────┘

职责：
1. 定义 ExecutionContext / ExecResult / ActionExecutor 统一协议；
2. 出参归一化：所有执行路径返回 ExecResult（结构化，JSON 优先）；
3. 错误归一化：error_kind 闭集（auth/quota/unreachable/invalid/timeout/resource）；
4. 适配器接线：把现有 executor/adapter/scattered 三路执行适配到统一接口。

本模块不持有动作语义，只做协议定义与适配（薄壳）。
"""

__all__ = [
    'ExecutionContext', 'ExecResult', 'ActionExecutor', 'executor_for',
    'ERROR_KINDS', 'result_from_adapter', 'result_from_exception',
]

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import re
from vools.core.dataclass_compat import dataclass, field

# 错误归一化闭集（docs/03 §3.4）：
# - auth：认证失败
# - quota：配额/限流
# - unreachable：目标不可达（网络/路径）
# - invalid：入参/契约非法
# - timeout：超时
# - resource：资源不足（内存/进程数）
# - runtime：执行期异常（兜底）
ERROR_KINDS = ('auth', 'quota', 'unreachable', 'invalid',
               'timeout', 'resource', 'runtime')


@dataclass
class ExecutionContext:
    """执行上下文（借鉴 n8n helpers + MCP capability negotiation）。

    能力协商：capabilities 按请求声明（调用方声明自己支持什么），
    执行器据此决定可用通道（如 dry_run 预览、流式输出）。
    """
    params: Dict[str, Any] = field(default_factory=dict)   # 入参（JSON object）
    caller: str = ''                                        # 调用方身份（审计用）
    capabilities: Dict[str, Any] = field(default_factory=dict)  # 能力声明（按请求协商）
    env: Dict[str, str] = field(default_factory=dict)       # 环境变量注入
    timeout_ms: int = 0                                     # 0 = 不限
    dry_run: bool = False                                   # True 时只预览不执行


@dataclass
class ExecResult:
    """统一出参（结构化，JSON 优先）。

    所有执行路径（executor/adapter/scattered）返回此结构，
    消费方（CLI/MCP/workflow）只认这一个出参契约。

    artifacts 形状兼容双来源：
      - executor/scattered：dict 列表（{name,path,hash,block}，docs/03 §7.2）
      - adapter：字符串路径（adapter.AdapterResult.artifact_path）

    status 判据表（三条执行路径**统一**，审计第 13 轮定稿）：
      | status  | 含义                                                         |
      |---------|--------------------------------------------------------------|
      | ok      | 真的执行了、且成功                                            |
      | error   | 执行了但失败 / 没执行也无法确认（error_kind 区分类别）         |
      | skipped | **本次没有执行**（dry_run 预览、awaiting_confirmation 待确认） |

    `timeout_deferred=True` = 墙钟到点先返回、后台线程可能仍在跑（结果未知）。
    """
    status: str = 'ok'                # ok / error / skipped
    data: Any = None                  # JSON 出参（入口块 stdout 优先解析）
    error: str = ''                   # 错误信息（status=error 时非空）
    error_kind: str = ''              # ERROR_KINDS 闭集内取值
    duration_ms: int = 0              # 执行耗时
    artifacts: List[Any] = field(default_factory=list)  # dict 或 str 混合（见 docstring）
    # 墙钟闸门到点返回时为 True：**结果未知**，worker 可能仍在后台跑（线程杀不掉）。
    # 消费方看到它就不能把这次执行当成"成功/失败已定"。
    timeout_deferred: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'status': self.status,
            'data': self.data,
            'error': self.error,
            'error_kind': self.error_kind,
            'duration_ms': self.duration_ms,
            'artifacts': list(self.artifacts),
            'timeout_deferred': self.timeout_deferred,
        }

    @property
    def ok(self) -> bool:
        return self.status == 'ok'


@runtime_checkable
class ActionExecutor(Protocol):
    """统一动作执行接口——所有执行路径实现此协议。

    新增执行通道只需实现 execute()，不需改消费方（CLI/MCP/workflow）。
    """

    def execute(self, action, ctx: ExecutionContext) -> ExecResult:
        """执行动作，返回统一出参。"""
        ...


def _run_with_deadline(fn, timeout_ms: int):
    """按 `ctx.timeout_ms` 给执行加**墙钟闸门**，返回 (value, deferred)。

    审计第 13 轮（契约谎言）：`ExecutionContext.timeout_ms` 此前**从未被读取** ——
    传 300ms 跑 2s 的动作照样跑满（实测 3.50s）。现在真正生效，但必须诚实：
    Python 线程无法强杀，到点只能"先返回 + 标注 worker 可能仍在跑"。

    **不能用 `with ThreadPoolExecutor(...)`**：`__exit__` 是 shutdown(wait=True)，
    会把"到点返回"重新变回"等 worker 跑完"（executor / mcp_server 都踩过）。
    """
    if not timeout_ms or timeout_ms <= 0:
        return fn(), False
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='actus-iface')
    try:
        fut = pool.submit(fn)
        try:
            return fut.result(timeout=timeout_ms / 1000.0), False
        except FutureTimeout:
            return None, True
    finally:
        pool.shutdown(wait=False)


def _deferred_result(timeout_ms: int) -> ExecResult:
    """超时到点返回的统一回执：结果未知 + 明确标注 worker 可能仍在跑。"""
    return ExecResult(
        status='error',
        error=('执行超过 %sms 已返回：进程内线程无法强杀，worker 可能仍在后台运行'
               '（副作用可能继续发生），本次结果未知' % timeout_ms),
        error_kind='timeout',
        timeout_deferred=True,
    )


def result_from_adapter(adapter_result) -> ExecResult:
    """把 adapter.AdapterResult 适配为统一 ExecResult。

    AdapterResult 的字段形状：success/stdout/stderr/returncode/data/duration/artifact_path。

    data 兜底：output_type=text 的适配器（CLI/Quicker）不解析 stdout 到 data，
    统一接口层回退带 stdout 原文——否则消费方（CLI/MCP/workflow）拿到
    status=ok 但 data=None，"执行成功了但输出丢了"（docs/03 §5 出参契约）。
    """
    ok = bool(getattr(adapter_result, 'success', False))
    data = getattr(adapter_result, 'data', None)
    stderr = getattr(adapter_result, 'stderr', '') or ''
    stdout = getattr(adapter_result, 'stdout', '') or ''
    if ok and data is None and stdout:
        data = {'stdout': stdout}
    return ExecResult(
        status='ok' if ok else 'error',
        data=data if ok else None,
        error='' if ok else (stderr or stdout or 'adapter 执行失败'),
        error_kind='' if ok else _classify_error(stderr, getattr(adapter_result, 'returncode', 0)),
        duration_ms=int(getattr(adapter_result, 'duration', 0) * 1000),
        artifacts=[getattr(adapter_result, 'artifact_path', '')]
        if getattr(adapter_result, 'artifact_path', '') else [],
    )


def result_from_exception(exc: Exception) -> ExecResult:
    """把异常归一为错误 ExecResult（error_kind 闭集内取值）。"""
    kind = _classify_exception(exc)
    message = getattr(exc, 'message', None) or str(exc)
    return ExecResult(status='error', error=message, error_kind=kind)


# 只认「明确的 HTTP 状态行」里的 401/429 —— 单独出现的数字 401 可能只是业务数据
# （审计实测：`processed 401 records, then failed` 曾被判成 auth）。
_HTTP_STATUS_RE = re.compile(
    r'(?i)\b(?:http(?:/\d(?:\.\d)?)?(?:\s+status)?'
    r'|status(?:\s+code)?)\s*[:=]?\s*(401|429)\b')


def _classify_error(stderr: str, returncode: int) -> str:
    """从 stderr/returncode 推断 error_kind（兜底 runtime）。

    审计第 13 轮：改前是**裸子串匹配** —— `"connection to sqlite db closed"` 判成
    unreachable、`"processed 401 records"` 判成 auth，会把普通逻辑失败导流到
    "网络/认证"分支（消费方据此重试/告警全错）。现在只认进程级信号。
    """
    text = stderr or ''
    lower = text.lower()
    m = _HTTP_STATUS_RE.search(text)
    http_code = m.group(1) if m else ''
    if (returncode in (401, 403) or http_code == '401'
            or 'unauthorized' in lower or 'authentication failed' in lower):
        return 'auth'
    if (returncode == 429 or http_code == '429'
            or 'rate limit' in lower or 'quota exceeded' in lower):
        return 'quota'
    if 'timed out' in lower or 'timeout' in lower:
        return 'timeout'
    if ('connection refused' in lower or 'unreachable' in lower
            or 'no route to host' in lower or 'name or service not known' in lower
            or 'temporary failure in name resolution' in lower):
        return 'unreachable'
    if 'permission denied' in lower or 'access is denied' in lower:
        return 'resource'
    return 'runtime'


# executor.py 的 error.code → ERROR_KINDS 闭集映射（docs/03 §7.2 出参契约）。
# V-01（寻虫 2026-10-22）：映射真源对齐 errors.ERROR_CODES（docs/08 §5）+
# executor 实发码（internal/omega_*/entry_no_output/deps_*）。每个码要么有
# 非 runtime 归宿，要么是显式豁免（注释标注）——旧表拿虚构键凑覆盖率，
# 实发码反而全漏。未知 code 映射 runtime 兜底，原码写进 error 原文不丢。
_ERROR_CODE_MAP = {
    # auth：认证/信任/审批（docs/08 §5.2 trust_rejected/visibility_denied 属授权面；
    # trust_denied 为旧别名保留）
    'auth_required': 'auth', 'trust_rejected': 'auth', 'trust_denied': 'auth',
    'visibility_denied': 'auth', 'approval_required': 'auth',
    # quota：限流/并发上限（executor 并发闸门实发 concurrency_limit）
    'concurrency_limit': 'quota', 'quota_exceeded': 'quota',
    'rate_limited': 'quota',
    # invalid：入参/契约/动作不存在/定义错误
    'param_invalid': 'invalid', 'action_invalid': 'invalid',
    'action_not_found': 'invalid', 'args_invalid': 'invalid',
    'contract_invalid': 'invalid', 'schema_invalid': 'invalid',
    'entry_no_output': 'invalid',            # 入口块无输出=契约违约（docs/38 §1）
    'omega_spec_invalid': 'invalid',         # Ω 契约坏（金条八：spec_error）
    'dependency_cycle': 'invalid',           # 动作定义错误（环是写出来的）
    # timeout（executor 实发 confirmation_timeout：等人工确认超时）
    'timeout': 'timeout', 'exec_timeout': 'timeout',
    'confirmation_timeout': 'timeout',
    # unreachable：依赖/目标/语言不可达
    'path_not_found': 'unreachable', 'unreachable': 'unreachable',
    'dependency_missing': 'unreachable', 'dep_missing': 'unreachable',
    'deps_missing': 'unreachable',
    'language_unavailable': 'unreachable',
    # resource：权限/沙箱/资源
    'permission_denied': 'resource', 'sandbox_violation': 'resource',
    'resource_exhausted': 'resource',
    # 显式豁免：internal（executor 块失败兜底码）与 omega_gate_failed
    # （验证不过，语义随动作）保留 runtime——不假装知道根因。
}


def _map_error_code(code: str) -> str:
    """executor error.code → ERROR_KINDS 闭集（未知 → runtime 兜底）。"""
    return _ERROR_CODE_MAP.get(str(code or ''), '')


def _classify_exception(exc: Exception) -> str:
    """从异常类型推断 error_kind。

    V-02（寻虫 2026-10-22）：ActionError 一律先走 _map_error_code(code)——
    旧实现内置 6 码白名单，与 dict 路径结论相反（ActionError('timeout')
    异常路→runtime、dict 路→timeout），消费方按 error_kind 分流不可靠。
    映射未命中再落启发式/兜底。
    """
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    # 适配器不可用（命令没装 / URL 不通）属于"环境不可达"，不是 runtime 故障
    if 'adapterunavailable' in name or '适配器不可用' in msg:
        return 'unreachable'
    if 'actionerror' in name:
        code = getattr(exc, 'code', '') or ''
        mapped = _map_error_code(code)
        if mapped:
            return mapped
        return 'runtime'
    if 'timeout' in name or 'timeout' in msg:
        return 'timeout'
    if 'connection' in name or 'unreachable' in msg:
        return 'unreachable'
    if 'permission' in name or 'denied' in msg:
        return 'resource'
    return 'runtime'


def executor_for(source: str) -> ActionExecutor:
    """按执行来源取统一执行器（协议绑定层接线点）。

    Args:
        source: "executor"（默认引擎）/ "adapter"（四协议适配）/ "scattered"（零散动作）

    Returns:
        实现了 ActionExecutor 协议的适配器实例。

    Raises:
        ValueError: source 不在支持列表内。
    """
    if source == 'executor':
        return _ExecutorIface()
    if source == 'adapter':
        return _AdapterIface()
    if source == 'scattered':
        return _ScatteredIface()
    raise ValueError(f'未知执行来源: {source!r}（支持 executor/adapter/scattered）')


class _ExecutorIface:
    """默认引擎执行器（executor.execute 的统一接口适配，惰性导入防循环依赖）。"""

    def execute(self, action, ctx: 'ExecutionContext') -> ExecResult:
        try:
            from . import executor as _executor_mod
        except ImportError as exc:
            return ExecResult(status='error', error=f'executor 不可导入: {exc}',
                              error_kind='runtime')
        # V-04（寻虫 2026-10-22）：dry_run 承诺"只预览不执行"。executor 源
        # 走引擎 preview API（executor.preview = docs/06 §3 干跑：展示将执行
        # 的块/指令/依赖/trust，不执行任何代码）——此前 dry_run=True 照样真跑。
        if ctx.dry_run:
            try:
                prev = _executor_mod.preview(action.id, ctx.params or {})
            except Exception as exc:  # noqa: BLE001
                return result_from_exception(exc)
            if isinstance(prev, dict) and prev.get('status') not in (None, 'ok'):
                err = prev.get('error') or {}
                return ExecResult(
                    status='error', data=prev,
                    error=str(err.get('message') if isinstance(err, dict) else err) or 'preview 失败',
                    error_kind=_map_error_code(str(err.get('code') if isinstance(err, dict) else '')) or 'runtime')
            # 统一判据（见 ExecResult docstring）：dry_run = **本次没有执行** → skipped
            return ExecResult(status='skipped', data=prev)
        try:
            raw, deferred = _run_with_deadline(
                lambda: _executor_mod.execute(action.id, ctx.params or {}),
                ctx.timeout_ms)
        except Exception as exc:  # noqa: BLE001 —— 统一出参契约：异常归一
            return result_from_exception(exc)
        if deferred:
            return _deferred_result(ctx.timeout_ms)
        # 引擎原生 execute 返回 docs/03 §7.2 结构化出参：
        #   {'status': 'ok'|'failed'|'awaiting_confirmation'|'cancelled',
        #    'data': ..., 'error': None | {'code','message','details'}, 'artifacts': [...]}
        if isinstance(raw, dict):
            st = raw.get('status')
            # V-03（寻虫 2026-10-22）：awaiting_confirmation 是 audit 动作的
            # **正常业务态**（error=None、data 带 exec_id/hint），旧实现把
            # 非 ok 一律归成 status='error'+error=''——违反本类"status=error
            # 时 error 非空"契约，且 MCP/CLI 消费方会把"等人工确认"当 runtime
            # 故障去重试/告警。归为 skipped 态（待确认=本次未执行、需 skip）。
            if st == 'awaiting_confirmation':
                return ExecResult(status='skipped', data=raw.get('data'),
                                  error='', error_kind='',
                                  artifacts=list(raw.get('artifacts') or []))
            ok = st == 'ok'
            err = raw.get('error') or {}
            err_msg = (err.get('message') or err.get('code') or '') if isinstance(err, dict) else str(err)
            err_code = (err.get('code') or '') if isinstance(err, dict) else ''
            return ExecResult(
                status='ok' if ok else 'error',
                data=raw.get('data'),
                # 兜底文案：非 ok 且引擎没给 message（理论上不该发生）也要 error 非空
                error='' if ok else (err_msg or f'执行失败（status={st!r}）'),
                error_kind='' if ok else (_map_error_code(err_code) or 'runtime'),
                artifacts=list(raw.get('artifacts') or []),
            )
        # 非结构化返回（None/str/…）：无法确认"真的执行了"，绝不能记 ok
        return ExecResult(
            status='error', data=None,
            error=('executor 返回了非结构化结果（%s）：无法确认是否真的执行成功'
                   % type(raw).__name__),
            error_kind='invalid')


class _AdapterIface:
    """四协议适配器（adapter.py 的统一接口适配，惰性导入防循环依赖）。

    动作元数据两种引用形态（docs/03 §5）：
      1. `adapter: <id>` —— 引用 actions/adapters/ 下已注册的适配器；
      2. `adapter: {type: cli, command: ...}` —— 内联 spec（不经注册表）。
    两者都支持；缺引用时错误信息明确告知声明方式，
    适配器不存在时列出已注册适配器与放置目录（P2-6）。
    """

    def execute(self, action, ctx: 'ExecutionContext') -> ExecResult:
        try:
            from .adapter import (AdapterSpec, AdapterRegistry, run_adapter)
        except ImportError as exc:
            return ExecResult(status='error', error=f'adapter 不可导入: {exc}',
                              error_kind='runtime')

        # V-04（寻虫 2026-10-22）：dry_run 承诺"只预览不执行"。
        # adapter 通道旧实现完全无视 dry_run 真执行（实测）。
        # dry_run=True 时不解析 ref、不创建适配器、不 run——返回预览态。
        if ctx.dry_run:
            ref = action.meta.get('adapter')
            preview = {
                'dry_run': True,
                'action_id': action.meta.get('id'),
                'adapter_ref': ref if isinstance(ref, str) else 'inline-spec',
            }
            return ExecResult(status='skipped', data=preview,
                              error='', error_kind='')

        ref = action.meta.get('adapter')
        # 形态 2：内联 spec（dict）。AdapterSpec.from_dict 的既有契约是
        # {'id':..., 'name/output/params/trust': 顶层, 'adapter': {type,command,...}}。
        # 寻虫 V-05（2026-10-22）：旧实现把平铺 dict **整体**塞进 adapter 子对象，
        # from_dict 的顶层读取（output→output_type/output_path、params、name、trust）
        # 全部落空——动作声明 'output': {type: file} 时产物静默蒸发、data=None。
        # 按 from_dict 的字段归属拆分：顶层已知键留顶层，其余进 adapter 子对象。
        if isinstance(ref, dict):
            _TOP_KEYS = ('id', 'name', 'description', 'version', 'author',
                         'tags', 'params', 'output', 'trust')
            try:
                top = {k: v for k, v in ref.items() if k in _TOP_KEYS}
                adapter_block = {k: v for k, v in ref.items() if k not in _TOP_KEYS}
                spec = AdapterSpec.from_dict(
                    {**{'id': top.get('id') or action.meta.get('id') or 'inline'},
                     'adapter': adapter_block,
                     **top})
                registry = AdapterRegistry()
                adapter = registry.create_adapter(spec)
                # 审计（第 25 轮）：内联 spec 也要在执行前做可用性探测，
                # 否则命令没装要等运行期才炸、且不给安装提示。
                registry.ensure_available(spec.id, spec, adapter)
                raw, deferred = _run_with_deadline(
                    lambda: adapter.run(ctx.params or {}), ctx.timeout_ms)
                if deferred:
                    return _deferred_result(ctx.timeout_ms)
            except Exception as exc:  # noqa: BLE001 —— 统一出参契约：异常归一
                return result_from_exception(exc)
            return result_from_adapter(raw)

        # 形态 1：引用已注册适配器 id
        if isinstance(ref, str) and ref.strip():
            adapter_id = ref.strip()
        else:
            return ExecResult(
                status='error',
                error=(f'动作 {action.meta.get("id")!r} 未声明 adapter 引用'
                       '（adapter: <id> 或内联 {type: cli|quicker|mcp|http, ...}）'),
                error_kind='invalid')

        try:
            raw, deferred = _run_with_deadline(
                lambda: run_adapter(adapter_id, ctx.params or {}), ctx.timeout_ms)
        except Exception as exc:  # noqa: BLE001 —— 统一出参契约：异常归一
            return result_from_exception(exc)
        if deferred:
            return _deferred_result(ctx.timeout_ms)

        # 适配器不存在时，错误信息列出已注册适配器与放置目录（P2-6）
        if not getattr(raw, 'success', False) and '适配器不存在' in (getattr(raw, 'stderr', '') or ''):
            registry = AdapterRegistry()
            known = sorted(s.id for s in registry.discover())
            hint = (f'适配器不存在: {adapter_id}。已注册: {known or "(无)"}。'
                    '放置目录: actions/adapters/*.actus.md（含 #!cfg adapter 块）')
            return ExecResult(status='error', error=hint, error_kind='invalid')
        return result_from_adapter(raw)


class _ScatteredIface:
    """零散动作执行器（scattered.py 的统一接口适配，惰性导入防循环依赖）。

    scattered.run_scattered(path, params, confirmed) 是真源入口；
    confirmed=False 时只校验不执行（docs/41 §C2 的"只校验不执行"语义；CLI 入口是 `actus validate`，旧文档里的 `actus check` 子命令不存在），
    统一接口层映射 dry_run=True → confirmed=False。
    """

    def execute(self, action, ctx: 'ExecutionContext') -> ExecResult:
        try:
            from . import scattered as _scattered
        except ImportError as exc:
            return ExecResult(status='error', error=f'scattered 不可导入: {exc}',
                              error_kind='runtime')
        # V-04（寻虫 2026-10-22）：dry_run 承诺"只预览不执行"。
        # 旧实现 confirmed=not ctx.dry_run 只是把确认位置 False——
        # trusted 动作 confirmed=False 照样真跑落副作用（实测）。
        # dry_run=True 时不执行 run_scattered，改走 check_scattered
        # 返回预览态（含校验结果，不落任何副作用）。
        if ctx.dry_run:
            try:
                chk = _scattered.check_scattered(action.path)
                return ExecResult(
                    status='skipped',
                    data={'dry_run': True, 'action_id': action.id,
                          'path': action.path, 'check': chk},
                    error='', error_kind='')
            except Exception as exc:  # noqa: BLE001 —— 统一出参契约：异常归一
                return result_from_exception(exc)
        try:
            raw, deferred = _run_with_deadline(
                lambda: _scattered.run_scattered(action.path, ctx.params or {},
                                                 confirmed=not ctx.dry_run),
                ctx.timeout_ms)
        except Exception as exc:  # noqa: BLE001 —— 统一出参契约：异常归一
            return result_from_exception(exc)
        if deferred:
            return _deferred_result(ctx.timeout_ms)
        if isinstance(raw, dict):
            ok = raw.get('status') == 'ok'
            err = raw.get('error') or {}
            err_msg = (err.get('message') or err.get('code') or '') if isinstance(err, dict) else str(err)
            err_code = (err.get('code') or '') if isinstance(err, dict) else ''
            return ExecResult(
                status='ok' if ok else 'error',
                data=raw.get('data'),
                error='' if ok else err_msg,
                error_kind='' if ok else (_map_error_code(err_code) or 'runtime'),
                artifacts=list(raw.get('artifacts') or []),
            )
        return ExecResult(
            status='error', data=None,
            error=('scattered 返回了非结构化结果（%s）：无法确认是否真的执行成功'
                   % type(raw).__name__),
            error_kind='invalid')
