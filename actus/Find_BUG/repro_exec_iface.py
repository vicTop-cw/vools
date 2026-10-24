# -*- coding: utf-8 -*-
"""复现 exec_iface.py 三处缺陷：
BUG-1: _ERROR_CODE_MAP 的死键（dep_missing/trust_denied/max_instances 等）与
       executor/ActionError 实际 code（deps_missing/dependency_missing/trust_rejected/
       concurrency_limit/entry_no_output）不对齐 → 本该 unreachable/auth/quota 的错全被归成 runtime。
BUG-2: _classify_exception 对 ActionError('timeout') / ActionError('permission_denied')
       返回 runtime —— 与 dict 路径 _map_error_code 的同一 code 不一致（契约漂移）。
BUG-3: _ExecutorIface 把 status='awaiting_confirmation'（正常待确认态，error=None）
       映射成 ExecResult(status='error', error='')——违反“status=error 时 error 非空”自述契约。
"""
import sys, types
sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')

from vools.actus.exec_iface import (_map_error_code, _classify_exception,
                                    executor_for, ExecutionContext, ExecResult)
from vools.actus.errors import ActionError

print('== BUG-1: 实际 error.code 与映射表对齐情况 ==')
# 全仓实际存在的 code（executor.py + errors.py ERROR_CODES + validate ActionError）
real_codes = ['param_invalid', 'deps_missing', 'dependency_missing', 'dependency_cycle',
              'trust_rejected', 'concurrency_limit', 'omega_spec_invalid',
              'omega_gate_failed', 'internal', 'entry_no_output', 'visibility_denied',
              'confirmation_timeout', 'timeout', 'language_unavailable',
              'auth_required', 'action_not_found', 'action_invalid', 'permission_denied']
for c in real_codes:
    print(f'  {c:24s} -> {_map_error_code(c) or "(空→runtime 兜底)"}')
dead = [k for k in ('dep_missing', 'trust_denied', 'max_instances', 'action_invalid')
        if k in ('dep_missing', 'trust_denied', 'max_instances')]
print('  映射表死键（无任何调用面发出）:', {k: _map_error_code(k) for k in dead})
assert _map_error_code('dependency_missing') == ''   # 期望 unreachable，实际落 runtime
assert _map_error_code('deps_missing') == ''
assert _map_error_code('trust_rejected') == ''
assert _map_error_code('concurrency_limit') == ''
print('  → dependency_*/deps_missing/trust_rejected/concurrency_limit 全落 runtime，确认')

print()
print('== BUG-2: _classify_exception 与 _map_error_code 对同一 code 结论不一致 ==')
e_to = ActionError('timeout', '执行超时')
e_pd = ActionError('permission_denied', '越权')
print('  ActionError(timeout)            _classify_exception ->', _classify_exception(e_to),
      ' / _map_error_code ->', _map_error_code('timeout'))
print('  ActionError(permission_denied)  _classify_exception ->', _classify_exception(e_pd),
      ' / _map_error_code ->', _map_error_code('permission_denied'))
assert _classify_exception(e_to) == 'runtime' and _map_error_code('timeout') == 'timeout'
assert _classify_exception(e_pd) == 'runtime' and _map_error_code('permission_denied') == 'resource'
print('  → 确认：异常路径把 timeout/permission 全归 runtime，dict 路径正确；两条路同错不同 kind')

print()
print('== BUG-3: awaiting_confirmation 被归一为空 error ==')
# 桩 executor：模拟引擎真实回执（audit 动作待人工确认，docs/03 §7.2）
fake = types.ModuleType('vools.actus.executor')
def fake_execute(action_id, params):
    return {'status': 'awaiting_confirmation',
            'data': {'exec_id': 'x1', 'action': action_id, 'trust': 'audit',
                     'hint': '需人类确认'},
            'error': None}
fake.execute = fake_execute
sys.modules['vools.actus.executor'] = fake

class DummyAction:
    id = 'foo.bar'
    meta = {'id': 'foo.bar'}

res = executor_for('executor').execute(DummyAction(), ExecutionContext(params={}))
print('  ExecResult:', res)
assert res.status == 'error', res.status
assert res.error == '', repr(res.error)      # 契约：status=error 时 error 非空
assert res.error_kind == 'runtime'
print('  → 确认：正常“待人工确认”被归一为 status=error + 空错误消息 + error_kind=runtime')
print('    （ExecResult 自述契约“error: 错误信息（status=error 时非空）”被违反，'
      '消费方按 error_kind 分流会把正常流程当故障）')
print('ALL EXEC_IFACE REPROS OK')
