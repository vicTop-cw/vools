# -*- coding: utf-8 -*-
"""第 11 轮补丁批：cost 读端 / selfdrive CLI 入口 / workflow 路由 / panel 标注 / P3 死代码删除。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)


def patch(path, old, new, count=1):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    assert old in s, '%s: 未匹配\n%s' % (path, old[:200])
    s = s.replace(old, new, count)
    io.open(p, 'w', encoding='utf-8').write(s)
    print('patched:', path)


# ── 1) cost.py：新增 by_model 聚合（lead 要求"按模型分组"）──────────────
patch('vools/actus/cost.py',
"""            if provider not in by_provider:
                by_provider[provider] = {'usd': 0, 'calls': 0, 'calls_unknown_cost': 0}
            by_provider[provider]['usd'] += cost
            by_provider[provider]['calls'] += 1
            if unknown_cost:
                by_provider[provider]['calls_unknown_cost'] += 1
""",
"""            if provider not in by_provider:
                by_provider[provider] = {'usd': 0, 'calls': 0, 'calls_unknown_cost': 0}
            by_provider[provider]['usd'] += cost
            by_provider[provider]['calls'] += 1
            if unknown_cost:
                by_provider[provider]['calls_unknown_cost'] += 1

            # 第 11 轮：按**模型**分组（此前只有 by_provider；CLI cost 要展示模型级
            # 花费，否则"按模型分组"只能靠人肉再算一遍）。
            model = entry.get('model') or 'unknown'
            if not isinstance(model, str):
                model = 'unknown'
            if model not in by_model:
                by_model[model] = {'usd': 0, 'calls': 0}
            by_model[model]['usd'] += cost
            by_model[model]['calls'] += 1
""")
patch('vools/actus/cost.py',
"""    by_provider = {}
    tokens_total = 0""",
"""    by_provider = {}
    by_model = {}
    tokens_total = 0""")
patch('vools/actus/cost.py',
"""        'by_provider': by_provider,
        'tokens_total': tokens_total,""",
"""        'by_provider': by_provider,
        'by_model': by_model,
        'tokens_total': tokens_total,""")

# ── 2) cli.py：cost + selfdrive 子命令 ─────────────────────────────
patch('vools/actus/cli.py',
"""    # sync 子命令
    p_sync = sub.add_parser('sync', help='同步已安装的动作仓库')""",
"""    # cost 子命令（第 11 轮接线：record_cost 只写不读，读端此前零入口）
    p_cost = sub.add_parser('cost', help='查看 AI 成本记账（本月 spend / calls / 按 provider、模型）')
    p_cost.add_argument('--month', default=None,
                        help='月份 YYYY-MM（缺省当月）')

    # selfdrive 子命令（第 11 轮接线：此前只有库内 API，文档却声称 CLI 已接通）
    p_selfdrive = sub.add_parser('selfdrive',
                                 help='自驱式编程（递归拆解 → 执行 → Ω 强验证）')
    p_selfdrive.add_argument('selfdrive_action', choices=['run', 'status'],
                             nargs='?', default='run',
                             help='run=运行目标（默认）/ status=查看历史运行快照')
    p_selfdrive.add_argument('goal', nargs='?', default='', help='目标文本（run 必填）')
    p_selfdrive.add_argument('run_id', nargs='?', default='',
                             help='status 用：指定 run_id（缺省列出最近运行）')
    p_selfdrive.add_argument('--plan', default=None,
                             help='动作计划 JSON 字符串（[{"action_id":...,"params":{}}] 或 ["动作id"]）')
    p_selfdrive.add_argument('--plan-file', default=None, dest='plan_file',
                             help='动作计划 JSON 文件路径')
    p_selfdrive.add_argument('--worker', choices=['echo', 'action'], default='echo',
                             help='echo=确定性空跑（默认，不执行真实动作）/ action=真实执行计划动作')
    p_selfdrive.add_argument('--max-depth', type=int, default=2, dest='max_depth',
                             help='递归拆解最大深度（默认 2）')
    p_selfdrive.add_argument('--max-rounds', type=int, default=3, dest='max_rounds',
                             help='失败回炉轮次预算（默认 3）')
    p_selfdrive.add_argument('--strong', action='store_true',
                             help='强验证模式（缺 Ω spec 视为失败）')

    # sync 子命令
    p_sync = sub.add_parser('sync', help='同步已安装的动作仓库')""")

patch('vools/actus/cli.py',
"""    if args.command == 'health':
        return _cmd_health(args)
""",
"""    if args.command == 'health':
        return _cmd_health(args)

    if args.command == 'cost':
        return _cmd_cost(args)

    if args.command == 'selfdrive':
        return _cmd_selfdrive(args)
""")

patch('vools/actus/cli.py',
"""def _cmd_health(args) -> int:""",
"""def _cmd_cost(args) -> int:
    \"\"\"cost 子命令：AI 成本记账汇总。

    第 11 轮接线：`record_cost()` 早已在 AI 调用路径写入账本，但**没有任何命令
    能读**（原 `get_cost_summary`/`check_budget` 全仓零消费）→ 记账只写不读、
    预算告警不可见。无记账数据时如实说"暂无记账"，不显示 $0 让人误以为免费。
    \"\"\"
    from vools.actus.cost import check_budget, get_cost_summary

    month = getattr(args, 'month', None)
    summary = get_cost_summary(month)
    recorded = bool(summary.get('calls'))
    data = {
        'month': summary.get('month'),
        'recorded': recorded,
        'spend_usd': summary.get('total_usd'),
        'calls': summary.get('calls'),
        'tokens_total': summary.get('tokens_total'),
        'by_provider': summary.get('by_provider') or {},
        'by_model': summary.get('by_model') or {},
        'ledger_complete': summary.get('ledger_complete'),
        'incomplete_reasons': summary.get('incomplete_reasons') or {},
    }
    if not recorded:
        data['message'] = '暂无记账数据（本月没有 AI 调用或未启用记账）'
    if month is None:
        data['budget'] = check_budget()
    return _out_result({'status': 'ok', 'data': data})


def _cmd_selfdrive(args) -> int:
    \"\"\"selfdrive 子命令：自驱式编程（run / status）。

    第 11 轮接线：此前 selfdrive / selfdrive_worker **只有库内 API**，而 docstring
    却声称 CLI/MCP 入口已接通（实测 grep 均 0 命中，属文档造假）。现在补 CLI：
      * `--worker echo`（默认）：确定性空跑，只跑通拆解/验证流程，不执行真实动作；
      * `--worker action`：用 `selfdrive_worker.ActionWorker.from_plan` 真实执行计划；
      * `status [run_id]`：读取 `_meta/selfdrive/*.json` 快照。
    \"\"\"
    from vools.actus import selfdrive as sd
    from vools.actus.paths import meta_dir as _mdir

    meta_dir = _mdir()
    action = getattr(args, 'selfdrive_action', 'run')

    if action == 'status':
        runs_dir = os.path.join(meta_dir, 'selfdrive')
        rid = (getattr(args, 'run_id', '') or '').strip()
        if rid:
            path = os.path.join(runs_dir, rid + '.json')
            if not os.path.isfile(path):
                return _out_result({'status': 'failed', 'error': {
                    'code': 'not_found', 'message': '运行快照不存在: %s' % rid}})
            with open(path, 'r', encoding='utf-8') as f:
                snap = json.load(f)
            return _out_result({'status': 'ok', 'data': snap})
        if not os.path.isdir(runs_dir):
            return _out_result({'status': 'ok', 'data': {
                'runs': [], 'count': 0, 'message': '暂无 selfdrive 运行记录'}})
        rows = []
        for fn in sorted(os.listdir(runs_dir)):
            if not fn.endswith('.json'):
                continue
            try:
                with open(os.path.join(runs_dir, fn), 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            rows.append({
                'run_id': data.get('run_id') or fn[:-5],
                'goal': data.get('goal'),
                'strong': data.get('strong'),
                'updated_at': data.get('updated_at'),
                'summary': data.get('summary'),
            })
        rows.sort(key=lambda r: r.get('updated_at') or '', reverse=True)
        return _out_result({'status': 'ok', 'data': {
            'runs': rows[:20], 'count': len(rows)}})

    goal = (getattr(args, 'goal', '') or '').strip()
    if not goal:
        return _out_result({'status': 'failed', 'error': {
            'code': 'param_invalid',
            'message': ('用法: actus selfdrive run <goal> [--plan JSON] '
                        '[--plan-file FILE] [--worker echo|action]')}})

    plan_raw = None
    plan_file = getattr(args, 'plan_file', None)
    if plan_file:
        try:
            with open(plan_file, 'r', encoding='utf-8') as f:
                plan_raw = f.read()
        except OSError as exc:
            return _out_result({'status': 'failed', 'error': {
                'code': 'param_invalid', 'message': '读取 --plan-file 失败: %s' % exc}})
    elif getattr(args, 'plan', None):
        plan_raw = args.plan

    worker = None
    spec_resolver = None
    worker_kind = 'echo'
    if getattr(args, 'worker', 'echo') == 'action':
        if not plan_raw:
            return _out_result({'status': 'failed', 'error': {
                'code': 'param_invalid',
                'message': '--worker action 需要 --plan/--plan-file（动作计划）'}})
        from vools.actus.paths import repo_root as _rroot
        from vools.actus.selfdrive_worker import ActionWorker
        try:
            aw = ActionWorker.from_plan(
                plan_raw, actions_dir=os.path.join(_rroot(), 'actions'),
                meta_dir=meta_dir)
        except ValueError as exc:
            return _out_result({'status': 'failed', 'error': {
                'code': 'param_invalid', 'message': str(exc)}})
        worker = aw.worker
        spec_resolver = aw.spec_resolver
        worker_kind = 'action'

    max_depth = getattr(args, 'max_depth', 2)
    max_rounds = getattr(args, 'max_rounds', 3)
    run = sd.SelfDrive(goal, max_depth=max(0, int(max_depth)),
                       max_rounds=max(1, int(max_rounds)),
                       worker=worker, spec_resolver=spec_resolver,
                       strong=True if getattr(args, 'strong', False) else None,
                       meta_dir=meta_dir)
    snap = dict(run.run())
    snap['worker_kind'] = worker_kind
    snap.setdefault('status', 'ok')
    return _out_result(snap)


def _cmd_health(args) -> int:""")

# ── 3) intent.py：route() 增加 workflow 分支 ─────────────────────
patch('vools/actus/intent.py',
"""        # 2. 标签匹配
        best_match = None
        best_score = 0
        best_reason = ""
""",
"""        # 2. 工作流匹配（第 11 轮接线：此前 `_workflows` 注册后 route() 从不读 ——
        # `register_workflow` 注册了永远不触发。工作流按 tags/description/id 匹配，
        # 命中返回 match='workflow' + workflow_id；action_id 置 None，避免调用方
        # 误把工作流当动作执行）。
        best_wf = None
        best_wf_score = 0
        best_wf_reason = ''
        for wf in self._workflows:
            score = 0
            for tag in wf.get('tags') or []:
                if str(tag).lower() in query_lower:
                    score += 0.4
            wf_desc = str(wf.get('description') or '').lower()
            if wf_desc and wf_desc in query_lower:
                score += 0.3
            elif wf_desc and any(w in wf_desc for w in query_lower.split() if len(w) > 2):
                score += 0.15
            wf_id = str(wf.get('id') or '').lower()
            if wf_id and wf_id in query_lower:
                score += 0.2
            if score > best_wf_score:
                best_wf_score = score
                best_wf = wf['id']
                best_wf_reason = '工作流匹配: %s' % wf['id']
        if best_wf and best_wf_score > 0.15:
            return {'match': 'workflow', 'workflow_id': best_wf,
                    'action_id': None,
                    'confidence': min(best_wf_score, 1.0),
                    'reason': best_wf_reason}

        # 3. 标签匹配
        best_match = None
        best_score = 0
        best_reason = ""
""")

# ── 4) panel.py：顶部加"未接线"警告 ────────────────────────────
patch('vools/actus/panel.py',
'''"""Quicker 风格快捷面板（docs/02 架构中的「薄壳」层）。
''',
'''"""Quicker 风格快捷面板（docs/02 架构中的「薄壳」层）。

⚠️ 第 11 轮审计：**当前未接线，能力尚不可用** —— 全仓 `grep "import panel"`
零命中，CLI / MCP / desktop 都没有调用 `run_panel` / `PanelApp`；本文件引用的
`docs/02` 在仓库 `docs/` 下也不存在。`panel_init.py` 只是历史遗留桩。
在真正接线（CLI 或 desktop 启动入口 + 热键注册）之前，**不要**在任何文档/答复里
宣称"已支持快捷面板/全局热键"。
''')

# ── 5) P3 死代码删除 ────────────────────────────────────────
# 5a dependency.py: doctor() + print_doctor_report()（零引用，且无 actus doctor 命令）
p = os.path.join(ROOT, 'vools/actus/dependency.py')
s = io.open(p, encoding='utf-8').read()
start = s.index('def doctor() -> dict:')
end = s.index('def print_doctor_report():')
# 找到 print_doctor_report 的结尾：下一个顶层 def 或文件尾
after = s.find('\ndef ', end + 10)
tail = after + 1 if after != -1 else len(s)
block_end = s.find('\ndef ', end + len('def print_doctor_report():'))
if block_end == -1:
    block_end = len(s)
    repl = ''
else:
    repl = s[block_end:]
s2 = s[:start] + repl.lstrip('\n')
# 同步文档头：删掉 "启动自检：actus doctor" 的假声明
s2 = s2.replace('- 启动自检：actus doctor\n', '')
io.open(p, 'w', encoding='utf-8').write(s2)
print('deleted: dependency.doctor + print_doctor_report')


def delete_func(path, header, name):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    idx = s.index(header)
    nxt = s.find('\ndef ', idx + 10)
    if nxt == -1:
        nxt = s.find('\nclass ', idx + 10)
    if nxt == -1:
        nxt = len(s)
    s = s[:idx] + s[nxt + 1:]
    io.open(p, 'w', encoding='utf-8').write(s)
    print('deleted:', name)


delete_func('vools/actus/importsys.py', '    def clear_cache(self):', 'ImportResolver.clear_cache')
delete_func('vools/actus/runtimes.py', '    def reset_registry(self):', 'RuntimeRegistry.reset_registry')
delete_func('vools/actus/vault.py', 'def reset_vault_singleton():', 'reset_vault_singleton')
delete_func('vools/actus/vault2.py', 'def reset_singleton():', 'vault2.reset_singleton')
delete_func('vools/actus/sigma.py', '    def register_builtin(self, name: str, fn: Callable) -> None:',
            'SigmaEngine.register_builtin')
delete_func('vools/actus/calllog.py', 'def reset_store():', 'calllog.reset_store')


def delete_method(path, header, name):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    idx = s.index(header)
    nxt = s.find('\n    def ', idx + 10)
    if nxt == -1:
        nxt = len(s)
    s = s[:idx] + s[nxt + 1:]
    io.open(p, 'w', encoding='utf-8').write(s)
    print('deleted:', name)


delete_method('vools/actus/calllog.py', '    def count(self) -> int:', 'CallLogStore.count')

# 删除 __all__ 中对应项
for path, names in (
        ('vools/actus/calllog.py', ["'reset_store'", "'CallLogStore.count'"]),
        ('vools/actus/vault.py', ["'reset_vault_singleton'"]),
        ('vools/actus/vault2.py', ["'reset_singleton'"])):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    for n in names:
        s = s.replace(', ' + n, '').replace(n + ', ', '')
    io.open(p, 'w', encoding='utf-8').write(s)
    print('__all__ cleaned:', path)

print('done')
