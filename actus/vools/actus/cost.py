"""cost.py — 成本账本（阶段 4）。

追踪每次云端 API 调用的成本，支持预算告警。
预算告警复用 notify 模块（docs/31 阶段 4：成本账本落 _meta/costs/，
复用 notify 模块做预算告警，先做最小版）。
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

__all__ = ['record_cost', 'get_cost_summary', 'check_budget',
           'alert_budget_if_over', 'COSTS_DIR']

# 成本账本目录。优先走 ACTUS_REPO_ROOT 环境变量（Actus 仓库根，run_tests.ps1 与
# 主程序都设它）；回退到相对本文件推导 —— 那个回退分支只在**vools 独立用**、
# 没有 Actus 主仓时兜底。
# 2026-10-13（docs/45 S2 shim 化）：本模块实现落在 vools，但 _meta/costs/ 是
# **宿主仓库**的运行时数据，不能跟着实现文件走。若靠 __file__ 推导，shim 后
# 会写成 `vools/.../_meta/costs/`，账本记到仓库外去了。
_ACTUS_ROOT = os.environ.get('ACTUS_REPO_ROOT')
if _ACTUS_ROOT:
    COSTS_DIR = os.path.join(_ACTUS_ROOT, '_meta', 'costs')
else:
    COSTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), '_meta', 'costs')


def _ensure_dir():
    os.makedirs(COSTS_DIR, exist_ok=True)


def record_cost(action_id: str, provider: str, cost_usd: float,
                tokens: int = 0, model: str = "", extra: dict = None):
    """记录一次成本调用。"""
    _ensure_dir()
    today = datetime.now().strftime('%Y-%m')
    filepath = os.path.join(COSTS_DIR, f'{today}.jsonl')
    entry = {
        'timestamp': datetime.now().isoformat(),
        'action_id': action_id,
        'provider': provider,
        'cost_usd': cost_usd,
        'tokens': tokens,
        'model': model,
    }
    if extra:
        entry.update(extra)
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def get_cost_summary(month: str = None) -> dict:
    """获取月度成本汇总。"""
    _ensure_dir()
    if month is None:
        month = datetime.now().strftime('%Y-%m')
    filepath = os.path.join(COSTS_DIR, f'{month}.jsonl')
    total = 0.0
    calls = 0
    by_provider = {}
    if not os.path.exists(filepath):
        return {'month': month, 'total_usd': 0, 'calls': 0, 'by_provider': {}}
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                cost = entry.get('cost_usd', 0)
                total += cost
                calls += 1
                provider = entry.get('provider', 'unknown')
                if provider not in by_provider:
                    by_provider[provider] = {'usd': 0, 'calls': 0}
                by_provider[provider]['usd'] += cost
                by_provider[provider]['calls'] += 1
            except Exception:
                continue
    return {'month': month, 'total_usd': round(total, 6), 'calls': calls, 'by_provider': by_provider}


def check_budget(month_limit_usd: float = 10.0) -> dict:
    """检查是否超出预算，返回状态。"""
    summary = get_cost_summary()
    total = summary['total_usd']
    over = total > month_limit_usd
    return {
        'budget_usd': month_limit_usd,
        'spent_usd': total,
        'remaining_usd': round(max(0, month_limit_usd - total), 6),
        'over_budget': over,
        'usage_pct': round(total / month_limit_usd * 100, 2) if month_limit_usd > 0 else 0,
    }


def alert_budget_if_over(month_limit_usd: float = 10.0, notify: bool = True) -> dict:
    """预算告警最小版（docs/31 阶段 4）：超支时经 notify 模块发告警。

    返回 check_budget 的状态 + alerted 标志；告警失败不影响判定结果。
    """
    status = check_budget(month_limit_usd)
    status['alerted'] = False
    if not status['over_budget'] or not notify:
        return status
    try:
        from .notify import NotifyLevel, get_notification_manager
        mgr = get_notification_manager()
        mgr.notify(
            title='Actus 预算告警',
            body=(f"本月云端成本 ${status['spent_usd']} 已超预算 "
                  f"${status['budget_usd']}（{status['usage_pct']}%）"),
            level=NotifyLevel.WARNING,
            metadata={'kind': 'budget', **status},
        )
        status['alerted'] = True
    except Exception:
        pass  # 告警通道失败不影响预算判定本身
    return status
