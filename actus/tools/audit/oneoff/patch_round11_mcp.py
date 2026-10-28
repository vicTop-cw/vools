# -*- coding: utf-8 -*-
"""第 11 轮：MCP 增加 actus_cost + workflow 路由注册/回传。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
P = os.path.join(ROOT, 'vools/actus/mcp_server.py')
s = io.open(P, encoding='utf-8').read()

# 1) tool 定义：插在 actus_status 之后
anchor = """            {'name': 'actus_status',
             'description': ('查询执行状态：可传 exec_id（执行留痕）或 task_id'
                             '（慢工具转后台后的任务句柄，返回 running/ok/failed/timeout）。'
                             '缺省 = 最近汇总。任务表在进程内存中，server 重启后失效。'),
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'exec_id': {'type': 'string'},
                                 'task_id': {'type': 'string',
                                             'description': '异步任务 id（tools/call 返回的 running 句柄里）'}}}},
"""
assert anchor in s
cost_tool = anchor + """            {'name': 'actus_cost',
             'description': ('AI 成本记账汇总（本月 spend/calls，按 provider 与模型分组）。'
                             '第 11 轮接线：record_cost 早已写入账本，但此前没有任何'
                             '命令/工具能读（get_cost_summary 全仓零消费）→ 记账只写不读、'
                             '预算告警不可见。无记账时如实返回 recorded=false。'),
             'inputSchema': {'type': 'object',
                             'properties': {
                                 'month': {'type': 'string',
                                           'description': '月份 YYYY-MM（缺省当月）'}}}},
"""
s = s.replace(anchor, cost_tool, 1)

# 2) handler：插在 actus_status 处理之后（收尾 return 之前）
status_end = """            data = rec.load_status(None)
            try:
                from vools.actus.eventbus import get_event_bus
                data['event_subscribers'] = get_event_bus().subscriber_count()
            except Exception:  # noqa: BLE001 —— 诊断字段，缺失不影响状态查询
                data['event_subscribers'] = None
            return text_result({'status': 'ok', 'data': data})
"""
assert status_end in s
cost_handler = status_end + """
        if name == 'actus_cost':
            from vools.actus.cost import check_budget, get_cost_summary
            month = args.get('month') or None
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
                # 如实说明"暂无记账"，不返回 0 让人以为免费
                data['message'] = '暂无记账数据（本月没有 AI 调用或未启用记账）'
            if month is None:
                data['budget'] = check_budget()
            return text_result({'status': 'ok', 'data': data})
"""
s = s.replace(status_end, cost_handler, 1)

# 3) recommend：把 bundle/workflow 类动作注册为 workflow（route 现在会读）
reg_anchor = """            for aid, a in actions.items():
                tags = a.meta.get('tags', [])
                desc = a.meta.get('description', '')
                usage = a.meta.get('usage', '')
                router.register_action(aid, desc, usage, tags)
"""
assert reg_anchor in s
reg_new = """            for aid, a in actions.items():
                tags = a.meta.get('tags', [])
                desc = a.meta.get('description', '')
                usage = a.meta.get('usage', '')
                router.register_action(aid, desc, usage, tags)
                # 第 11 轮接线：register_workflow 此前注册了没人读（route 无分支），
                # 现在把 bundle/workflow 类动作同时登记为工作流，route 可返回
                # match='workflow'。此处按动作 kind 登记，属最小真实来源。
                if str(a.meta.get('kind') or 'exec').lower() in ('bundle', 'workflow'):
                    router.register_workflow(aid, desc, tags)
"""
s = s.replace(reg_anchor, reg_new, 1)

# 4) recommend 结果：回传 workflow（若命中）
route_anchor = """            result = router.route(description)
            
            recommendations = []
            if result.get('action_id'):"""
assert route_anchor in s
route_new = """            result = router.route(description)

            workflow = None
            if result.get('workflow_id'):
                workflow = {'id': result['workflow_id'],
                            'reason': result.get('reason', '')}

            recommendations = []
            if result.get('action_id'):"""
s = s.replace(route_anchor, route_new, 1)

ret_anchor = """            return text_result({'status': 'ok', 'data': {'recommendations': recommendations, 'total': len(recommendations)}})"""
assert ret_anchor in s
ret_new = """            data = {'recommendations': recommendations,
                    'total': len(recommendations)}
            if workflow is not None:
                data['workflow'] = workflow
            return text_result({'status': 'ok', 'data': data})"""
s = s.replace(ret_anchor, ret_new, 1)

io.open(P, 'w', encoding='utf-8').write(s)
print('mcp_server patched: actus_cost + workflow route')
