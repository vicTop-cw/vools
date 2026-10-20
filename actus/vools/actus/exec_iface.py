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
    """
    status: str = 'ok'                # ok / error / skipped
    data: Any = None                  # JSON 出参（入口块 stdout 优先解析）
    error: str = ''                   # 错误信息（status=error 时非空）
    error_kind: str = ''              # ERROR_KINDS 闭集内取值
    duration_ms: int = 0              # 执行耗时
    artifacts: List[Any] = field(default_factory=list)  # dict 或 str 混合（见 docstring）

    def to_dict(self) -> Dict[str, Any]:
        return {
            'status': self.status,
            'data': self.data,
            'error': self.error,
            'error_kind': self.error_kind,
            'duration_ms': self.duration_ms,
            'artifacts': list(self.artifacts),
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


def _classify_error(stderr: str, returncode: int) -> str:
    """从 stderr/returncode 推断 error_kind（兜底 runtime）。"""
    s = (stderr or '').lower()
    if 'auth' in s or 'unauthorized' in s or '401' in s or returncode == 401:
        return 'auth'
    if 'quota' in s or 'rate limit' in s or '429' in s or returncode == 429:
        return 'quota'
    if 'timeout' in s or 'timed out' in s:
        return 'timeout'
    if 'unreachable' in s or 'connection' in s or 'refused' in s:
        return 'unreachable'
    if 'permission' in s or 'denied' in s:
        return 'resource'
    return 'runtime'


# executor.py 的 error.code → ERROR_KINDS 闭集映射（docs/03 §7.2 出参契约）。
# 未知 code 映射 runtime（闭集内兜底），绝不丢弃原 code（写进 ExecResult.error 原文）。
_ERROR_CODE_MAP = {
    # auth：认证/信任/审批
    'auth_required': 'auth', 'auth': 'auth', 'trust_denied': 'auth',
    'approval_required': 'auth',
    # quota：限流/并发上限
    'quota_exceeded': 'quota', 'rate_limited': 'quota',
    'max_instances': 'quota',
    # invalid：入参/契约/动作不存在
    'param_invalid': 'invalid', 'action_invalid': 'invalid',
    'action_not_found': 'invalid', 'args_invalid': 'invalid',
    'contract_invalid': 'invalid', 'schema_invalid': 'invalid',
    # timeout
    'timeout': 'timeout', 'exec_timeout': 'timeout',
    # unreachable：路径/网络不可达
    'path_not_found': 'unreachable', 'unreachable': 'unreachable',
    'dep_missing': 'unreachable',
    # resource：资源/权限/沙箱
    'permission_denied': 'resource', 'sandbox_violation': 'resource',
    'resource_exhausted': 'resource',
}


def _map_error_code(code: str) -> str:
    """executor error.code → ERROR_KINDS 闭集（未知 → runtime 兜底）。"""
    return _ERROR_CODE_MAP.get(str(code or ''), '')


def _classify_exception(exc: Exception) -> str:
    """从异常类型推断 error_kind。"""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if 'actionerror' in name:
        code = getattr(exc, 'code', '') or ''
        if code in ('auth_required', 'auth'):
            return 'auth'
        if code in ('action_invalid', 'action_not_found', 'invalid'):
            return 'invalid'
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
        try:
            raw = _executor_mod.execute(action.id, ctx.params or {})
        except Exception as exc:  # noqa: BLE001 —— 统一出参契约：异常归一
            return result_from_exception(exc)
        # 引擎原生 execute 返回 docs/03 §7.2 结构化出参：
        #   {'status': 'ok'|'failed', 'data': ..., 'error': None | {'code','message','details'}, 'artifacts': [...]}
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
        return ExecResult(status='ok', data=raw)


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

        ref = action.meta.get('adapter')
        # 形态 2：内联 spec（dict）。AdapterSpec.from_dict 的既有契约是
        # {'id':..., 'adapter': {type, command, ...}}（command 在 adapter 子对象里），
        # 平铺写法（{'type': 'cli', 'command': 'echo'}）会被丢弃 command——
        # 这里把平铺键收进 adapter 子对象再构造，两种写法都支持。
        if isinstance(ref, dict):
            try:
                adapter_block = dict(ref)
                aid = adapter_block.pop('id', '') or action.meta.get('id') or 'inline'
                spec = AdapterSpec.from_dict({'id': aid, 'adapter': adapter_block})
                registry = AdapterRegistry()
                adapter = registry.create_adapter(spec)
                raw = adapter.run(ctx.params or {})
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
            raw = run_adapter(adapter_id, ctx.params or {})
        except Exception as exc:  # noqa: BLE001 —— 统一出参契约：异常归一
            return result_from_exception(exc)

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
    confirmed=False 时只校验不执行（docs/41 §C2 的 actus check 语义），
    统一接口层映射 dry_run=True → confirmed=False。
    """

    def execute(self, action, ctx: 'ExecutionContext') -> ExecResult:
        try:
            from . import scattered as _scattered
        except ImportError as exc:
            return ExecResult(status='error', error=f'scattered 不可导入: {exc}',
                              error_kind='runtime')
        try:
            raw = _scattered.run_scattered(action.path, ctx.params or {},
                                           confirmed=not ctx.dry_run)
        except Exception as exc:  # noqa: BLE001 —— 统一出参契约：异常归一
            return result_from_exception(exc)
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
        return ExecResult(status='ok', data=raw)
